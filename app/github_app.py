"""GitHub App registration and short-lived installation authentication."""
from __future__ import annotations

import json
import secrets
import time
from urllib.parse import urlencode

import httpx
import jwt

from app.control import Control, now, uid


PERMISSIONS = {"metadata": "read", "contents": "read", "issues": "read", "pull_requests": "read"}


def app_jwt(control: Control) -> str:
    app_id = control.secret_get("github_app_id")
    private_key = control.secret_get("github_app_private_key")
    if not app_id or not private_key:
        raise ValueError("Register or configure a GitHub App in Administration first")
    current = int(time.time())
    try:
        return jwt.encode({"iat": current - 60, "exp": current + 540, "iss": app_id}, private_key, algorithm="RS256")
    except Exception as exc:
        raise ValueError("The configured GitHub App private key is not a valid RSA PEM key") from exc


def api_get(control: Control, path: str):
    with httpx.Client(timeout=20) as client:
        response = client.get("https://api.github.com" + path, headers={"Authorization": "Bearer " + app_jwt(control), "Accept": "application/vnd.github+json"})
        response.raise_for_status()
        return response.json()


def new_state(control: Control, user_id: str, purpose: str) -> str:
    state = secrets.token_urlsafe(32)
    control.execute("INSERT INTO oauth_states VALUES (?,?,?,?)", (state, user_id, purpose, time.time() + 1800))
    return state


def consume_state(control: Control, user_id: str, state: str, purpose: str):
    with control.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        result = db.execute("SELECT * FROM oauth_states WHERE state=? AND user_id=? AND verifier=? AND expires_at>?", (state, user_id, purpose, time.time())).fetchone()
        if not result:
            raise ValueError("This GitHub setup session is missing or expired. Start again from Administration.")
        db.execute("DELETE FROM oauth_states WHERE state=?", (state,))


def manifest(control: Control, user_id: str, origin: str):
    state = new_state(control, user_id, "app_manifest")
    return {"state": state, "action": "https://github.com/settings/apps/new?" + urlencode({"state": state}), "manifest": {
        "name": "DecisionTrail-" + secrets.token_hex(3), "url": origin,
        "description": "Company knowledge graph: read selected repository documents, issues, pull requests and ownership into DecisionTrail.",
        "redirect_url": origin + "/api/connectors/github/app/manifest/callback",
        "setup_url": origin + "/api/connectors/github/app/setup",
        "setup_on_update": True, "request_oauth_on_install": False,
        "public": False, "default_permissions": PERMISSIONS, "default_events": [],
    }}


def complete_manifest(control: Control, user_id: str, state: str, code: str):
    consume_state(control, user_id, state, "app_manifest")
    if not code or len(code) > 200:
        raise ValueError("Invalid GitHub manifest code")
    with httpx.Client(timeout=20) as client:
        response = client.post(f"https://api.github.com/app-manifests/{code}/conversions", headers={"Accept": "application/vnd.github+json"})
        response.raise_for_status()
        result = response.json()
    for key, value in {
        "github_app_id": str(result["id"]), "github_app_slug": result["slug"],
        "github_app_private_key": result["pem"], "github_app_webhook_secret": result.get("webhook_secret") or "",
    }.items():
        control.secret_set(key, value)
    control.audit(user_id, "github_app.registered", details={"app_id": result["id"], "slug": result["slug"]})
    return result["slug"]


def install_url(control: Control, user_id: str):
    slug = control.secret_get("github_app_slug")
    if not slug:
        raise ValueError("Register or configure your GitHub App first")
    return f"https://github.com/apps/{slug}/installations/new?" + urlencode({"state": new_state(control, user_id, "app_install")})


def connect_installation(control: Control, user_id: str, installation_id: int, state: str):
    consume_state(control, user_id, state, "app_install")
    installation = api_get(control, f"/app/installations/{installation_id}")
    if installation.get("suspended_at"):
        raise ValueError("This GitHub App installation is suspended")
    old = control.rows("SELECT id FROM connections WHERE user_id=? AND provider='github_app'", (user_id,))
    connection_id = old[0]["id"] if old else uid("connection")
    value = control.cipher.encrypt(json.dumps({"installation_id": installation_id, "account_id": installation["account"]["id"], "repository_selection": installation["repository_selection"]}).encode()).decode()
    control.execute("INSERT OR REPLACE INTO connections VALUES (?,?,?,?,?,?)", (connection_id, user_id, "github_app", installation["account"]["login"], value, now()))
    control.audit(user_id, "github_app.installed", details={"installation_id": installation_id, "account": installation["account"]["login"]})
    return {"id": connection_id, "login": installation["account"]["login"]}


def installation_token(control: Control, user_id: str) -> str | None:
    connections = control.rows("SELECT secret FROM connections WHERE user_id=? AND provider='github_app'", (user_id,))
    if not connections:
        return None
    metadata = json.loads(control.cipher.decrypt(connections[0]["secret"].encode()).decode())
    installation_id = int(metadata["installation_id"])
    with httpx.Client(timeout=20) as client:
        response = client.post(f"https://api.github.com/app/installations/{installation_id}/access_tokens",
                               headers={"Authorization": "Bearer " + app_jwt(control), "Accept": "application/vnd.github+json"},
                               json={"permissions": PERMISSIONS})
        response.raise_for_status()
        return response.json()["token"]
