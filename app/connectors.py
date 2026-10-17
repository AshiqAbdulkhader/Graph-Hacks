"""GitHub OAuth and repository sync through GitHub's REST API."""
from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
import time
import subprocess
from pathlib import PurePosixPath
from urllib.parse import quote, urlencode

import httpx

from app.control import Control, now, uid
from app.ingestion import Ingestor
from app.knowledge import digest


def github_cli_identity():
    """Read an explicitly authorized local gh session; never emit the credential."""
    try:
        result = subprocess.run(["gh", "auth", "token", "--hostname", "github.com"],
                                capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("GitHub CLI is unavailable. Install gh and run gh auth login first.") from exc
    token = result.stdout.strip()
    if result.returncode or not token:
        raise ValueError("No github.com CLI session found. Run gh auth login first.")
    with httpx.Client(timeout=15) as client:
        response = client.get("https://api.github.com/user", headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
        response.raise_for_status()
        profile = response.json()
    return profile, token


def save_connection(control: Control, user_id: str, login: str, token: str):
    old = control.rows("SELECT id FROM connections WHERE user_id=? AND provider='github'", (user_id,))
    connection_id = old[0]["id"] if old else uid("connection")
    encrypted = control.cipher.encrypt(token.encode()).decode()
    control.execute("INSERT OR REPLACE INTO connections VALUES (?,?,?,?,?,?)", (connection_id, user_id, "github", login, encrypted, now()))
    control.audit(user_id, "github.connected", details={"login": login})
    return {"id": connection_id, "login": login}


def oauth_start(control: Control, user_id: str, callback: str, private: bool = False) -> str:
    client_id = control.secret_get("github_client_id")
    if not client_id or not control.secret_get("github_client_secret"):
        raise ValueError("Configure the GitHub OAuth app in Administration first")
    state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    control.execute("DELETE FROM oauth_states WHERE expires_at<?", (time.time(),))
    control.execute("INSERT INTO oauth_states VALUES (?,?,?,?)", (state, user_id, verifier, time.time() + 600))
    return "https://github.com/login/oauth/authorize?" + urlencode({
        "client_id": client_id, "redirect_uri": callback, "state": state,
        "scope": "read:user repo" if private else "read:user", "code_challenge": challenge,
        "code_challenge_method": "S256",
    })


def oauth_callback(control: Control, user_id: str, code: str, state: str, callback: str):
    with control.connection() as db:
        row = db.execute("SELECT * FROM oauth_states WHERE state=? AND user_id=? AND expires_at>?", (state, user_id, time.time())).fetchone()
        if not row:
            raise ValueError("OAuth state is missing, expired, or belongs to another session")
        verifier = row["verifier"]
        db.execute("DELETE FROM oauth_states WHERE state=?", (state,))
    with httpx.Client(timeout=20) as client:
        response = client.post("https://github.com/login/oauth/access_token", headers={"Accept": "application/json"},
                               json={"client_id": control.secret_get("github_client_id"),
                                     "client_secret": control.secret_get("github_client_secret"),
                                     "code": code, "code_verifier": verifier, "redirect_uri": callback})
        response.raise_for_status()
        token = response.json().get("access_token")
        if not token:
            raise ValueError("GitHub did not issue an access token. Check OAuth app configuration and try again.")
        identity = client.get("https://api.github.com/user", headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
        identity.raise_for_status()
        login = identity.json()["login"]
    return save_connection(control, user_id, login, token)


class GitHub:
    def __init__(self, token: str | None = None):
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "DecisionTrail"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.client = httpx.Client(base_url="https://api.github.com", headers=headers, timeout=20)

    def get(self, path: str, params: dict | None = None):
        response = self.client.get(path, params=params)
        if response.status_code in {403, 429}:
            raise ValueError("GitHub access or rate limit prevented this request; reconnect or retry after the limit resets")
        if response.status_code == 404:
            raise ValueError("Repository or resource is not accessible with this connection")
        response.raise_for_status()
        return response.json()

    def repositories(self, page: int = 1, installation: bool = False):
        data = self.get("/installation/repositories" if installation else "/user/repos", {"per_page": 50, "page": max(page, 1), "sort": "updated"})
        if installation:
            data = data["repositories"]
        return [{"full_name": x["full_name"], "description": x.get("description"), "private": x["private"], "updated_at": x["updated_at"]} for x in data]

    def close(self):
        self.client.close()


def connection_token(control: Control, user_id: str) -> str | None:
    from app.github_app import installation_token
    return installation_token(control, user_id)


def sync_repository(control: Control, workspace: dict, payload: dict, job_id: str):
    repo_name = payload["repository"].removeprefix("https://github.com/").removesuffix("/").removesuffix(".git")
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo_name):
        raise ValueError("Enter a repository in owner/name format")
    client = GitHub(connection_token(control, workspace["owner_id"]))
    ingestor = Ingestor(control, workspace)
    imported = 0
    skipped = 0
    partial = False
    limit = min(max(int(payload.get("limit", 30)), 1), 100)
    try:
        repo = client.get(f"/repos/{repo_name}")
        repo_key = "github:repository:" + str(repo["id"])
        source = ingestor.source(f"github:{repo_name}:overview", repo_name, "github", json.dumps({
            "name": repo_name, "description": repo.get("description"), "url": repo["html_url"],
            "default_branch": repo["default_branch"], "topics": repo.get("topics", []),
        }, indent=2), repo["html_url"], metadata={"repository": repo_name})
        ingestor.graph.entity(repo_key, repo_name, "Repository", {"url": repo["html_url"]})
        ingestor.graph.mention(repo_key, source["version_id"])
        imported += 1
        if payload.get("documents", True):
            tree = client.get(f"/repos/{repo_name}/git/trees/{quote(repo['default_branch'], safe='')}", {"recursive": 1})
            docs = [x for x in tree.get("tree", []) if x["type"] == "blob" and PurePosixPath(x["path"]).suffix.lower() in {".md", ".txt", ".rst"} and x.get("size", 0) < 300_000]
            docs.sort(key=lambda item: (0 if item["path"].lower() in {"readme.md", "readme.txt", "readme.rst"} else 1, item["path"]))
            partial = tree.get("truncated", False) or len(docs) > limit
            for item in docs[:limit]:
                path = item["path"]
                content = client.get(f"/repos/{repo_name}/contents/{quote(path, safe='/')}", {"ref": repo["default_branch"]})
                if content.get("encoding") != "base64":
                    skipped += 1
                    continue
                text = base64.b64decode(content["content"]).decode("utf-8", errors="replace")
                result = ingestor.source(f"github:{repo_name}:file:{path}", f"{repo_name} / {path}", "github", text,
                                         content.get("html_url", ""), metadata={"repository": repo_name, "path": path, "sha": content.get("sha")})
                file_key = f"github:file:{digest(repo_name + ':' + path)}"
                ingestor.graph.entity(file_key, path, "File")
                ingestor.graph.mention(file_key, result["version_id"])
                ingestor.graph.relation(file_key, repo_key, "PART_OF", result["id"], result["version_id"], f"{path} in {repo_name}")
                imported += 1
                control.progress(job_id, "running", f"Imported {path}", imported, 0)
        for kind, enabled in (("issue", payload.get("issues", True)), ("pull_request", payload.get("pull_requests", True))):
            if not enabled:
                continue
            endpoint = "issues" if kind == "issue" else "pulls"
            items = client.get(f"/repos/{repo_name}/{endpoint}", {"state": "all", "per_page": min(limit + 1, 100), "sort": "updated", "direction": "desc"})
            if kind == "issue":
                items = [x for x in items if "pull_request" not in x]
            partial = partial or len(items) > limit
            for item in items[:limit]:
                text = f"{item['title']}\n\n{item.get('body') or ''}\n\nState: {item['state']}\nAuthor: {item['user']['login']}"
                result = ingestor.source(f"github:{repo_name}:{kind}:{item['number']}", f"{repo_name} #{item['number']} · {item['title']}", "github", text, item["html_url"], metadata={"repository": repo_name, "kind": kind, "number": item["number"]})
                item_key = f"github:{kind}:{item['id']}"
                ingestor.graph.entity(item_key, item["title"], "Issue" if kind == "issue" else "PullRequest", {"number": item["number"], "state": item["state"], "url": item["html_url"]})
                ingestor.graph.mention(item_key, result["version_id"])
                ingestor.graph.relation(item_key, repo_key, "IN_REPOSITORY", result["id"], result["version_id"], repo_name)
                for role, people in (("AUTHORED_BY", [item["user"]]), ("ASSIGNED_TO", item.get("assignees", []))):
                    for person in people:
                        key = f"github:person:{person['id']}"
                        ingestor.graph.entity(key, person["login"], "Person", {"url": person.get("html_url", "")})
                        ingestor.graph.mention(key, result["version_id"])
                        ingestor.graph.relation(item_key, key, role, result["id"], result["version_id"], person["login"])
                imported += 1
                control.progress(job_id, "running", f"Imported {kind} #{item['number']}", imported, 0)
        control.progress(job_id, "completed", f"Imported {imported} sources; skipped {skipped}. " + ("Configured limit reached: increase the limit to import more." if partial else "Sync complete."), imported, imported)
    finally:
        client.close()
