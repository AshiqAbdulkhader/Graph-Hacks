"""DecisionTrail product API: local accounts, workspaces, ingestion, OAuth and agents."""
from __future__ import annotations

import hashlib
import html
import json
import os
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.config import settings
from app.connectors import GitHub, connection_token, github_cli_identity
from app.github_app import manifest, complete_manifest, install_url, connect_installation
from app.control import Control, check_password, hash_password, now, uid
from app.ingestion import SUPPORTED
from app.jobs import Jobs
from app.knowledge import Knowledge
from app.workspace_agent import WorkspaceAgent


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=10, max_length=200)
    name: str = Field(default="Workspace owner", min_length=1, max_length=100)


class Named(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class TextSource(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=500000)


class Query(BaseModel):
    query: str = Field(min_length=1, max_length=12000)


class Sync(BaseModel):
    repository: str = Field(min_length=3, max_length=200)
    documents: bool = True
    issues: bool = True
    pull_requests: bool = True
    limit: int = Field(default=30, ge=1, le=100)


class AgentDefinition(Named):
    instructions: str = Field(default="Answer with source evidence and identify missing information.", min_length=1, max_length=4000)


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    use_ai: bool = True


class Review(BaseModel):
    approve: bool


class TaskStatus(BaseModel):
    status: str = Field(pattern=r"^(open|in_progress|done)$")


class AppSettings(BaseModel):
    github_app_id: str = Field(default="", max_length=100, pattern=r"^\d*$")
    github_app_slug: str = Field(default="", max_length=200, pattern=r"^[A-Za-z0-9-]*$")
    github_app_private_key: str = Field(default="", max_length=20000)
    openrouter_api_key: str = Field(default="", max_length=500)
    openrouter_model: str = Field(default="", max_length=200)


def control(request: Request) -> Control:
    return request.app.state.control


def current_user(request: Request, ctl: Control = Depends(control)) -> dict:
    token = request.cookies.get("dt_session", "")
    hashed = hashlib.sha256(token.encode()).hexdigest()
    rows = ctl.rows("SELECT u.id,u.name,u.email,u.role FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=? AND s.expires_at>?", (hashed, time.time()))
    if not rows:
        raise HTTPException(401, "Sign in to your workspace")
    return rows[0]


def admin(user: dict = Depends(current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Administrator access required")
    return user


def workspace(workspace_id: str, user: dict = Depends(current_user), ctl: Control = Depends(control)):
    rows = ctl.rows("SELECT * FROM workspaces WHERE id=?", (workspace_id,))
    if not rows or (rows[0]["owner_id"] != user["id"] and user["role"] != "admin"):
        raise HTTPException(404, "Workspace not found")
    return rows[0]


def new_workspace(ctl: Control, user_id: str, name: str):
    workspace_id = uid("workspace")
    graph_name = "dt_" + workspace_id.removeprefix("workspace_")
    Knowledge(graph_name).initialize()
    ctl.execute("INSERT INTO workspaces VALUES (?,?,?,?,?)", (workspace_id, name, user_id, graph_name, now()))
    for agent_name, instruction in (
        ("Company researcher", "Investigate questions using current sources and show the relevant relationships. Cite exact evidence."),
        ("Impact analyst", "Follow graph relationships to identify affected people, projects and work. Separate confirmed dependencies from possible effects."),
        ("Knowledge curator", "Look for conflicting statements, outdated context and unclear ownership. Suggest precise review tasks supported by evidence."),
    ):
        ctl.execute("INSERT INTO agents VALUES (?,?,?,?,?)", (uid("agent"), workspace_id, agent_name, instruction, now()))
    return ctl.rows("SELECT * FROM workspaces WHERE id=?", (workspace_id,))[0]


def set_session(ctl: Control, user_id: str, response: Response):
    token = secrets.token_urlsafe(40)
    ctl.execute("INSERT INTO sessions VALUES (?,?,?)", (hashlib.sha256(token.encode()).hexdigest(), user_id, time.time() + 604800))
    response.set_cookie("dt_session", token, httponly=True, samesite="lax", secure=os.getenv("COOKIE_SECURE", "false").lower() == "true", max_age=604800)


def create_app(directory: str | Path | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.control = Control(directory)
        app.state.jobs = Jobs(app.state.control)
        app.state.jobs.resume()
        yield
        app.state.jobs.close()

    app = FastAPI(title="DecisionTrail", version="0.2.0", lifespan=lifespan)

    @app.middleware("http")
    async def origin_guard(request: Request, call_next):
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("origin")
            allowed = {os.getenv("APP_ORIGIN", "http://127.0.0.1:8765"), "http://localhost:8765", "http://127.0.0.1:5173"}
            if origin and origin not in allowed:
                return Response("Origin not permitted", status_code=403)
        return await call_next(request)

    @app.exception_handler(ValueError)
    async def invalid(request: Request, exc: ValueError):
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(httpx.HTTPError)
    async def upstream(request: Request, exc: httpx.HTTPError):
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": "The upstream service could not complete this request. Check the connector or retry."}, status_code=502)

    @app.get("/api/auth/status")
    def auth_status(ctl: Control = Depends(control)):
        return {"setup_required": not bool(ctl.rows("SELECT id FROM users LIMIT 1"))}

    @app.post("/api/auth/setup")
    def setup(body: Credentials, response: Response, ctl: Control = Depends(control)):
        user_id = uid("user")
        with ctl.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT id FROM users LIMIT 1").fetchone():
                raise HTTPException(409, "Workspace owner already exists; sign in")
            db.execute("INSERT INTO users VALUES (?,?,?,?,?,?)", (user_id, body.name, body.email.lower().strip(), hash_password(body.password), "admin", now()))
        new_workspace(ctl, user_id, "My company")
        set_session(ctl, user_id, response)
        return {"id": user_id, "name": body.name, "role": "admin"}

    @app.post("/api/auth/login")
    def login(body: Credentials, response: Response, ctl: Control = Depends(control)):
        rows = ctl.rows("SELECT * FROM users WHERE email=?", (body.email.lower().strip(),))
        if not rows or not check_password(body.password, rows[0]["password"]):
            raise HTTPException(401, "Email or password is incorrect")
        set_session(ctl, rows[0]["id"], response)
        return {k: rows[0][k] for k in ("id", "name", "role")}

    @app.post("/api/auth/logout")
    def logout(request: Request, response: Response, ctl: Control = Depends(control)):
        ctl.execute("DELETE FROM sessions WHERE token=?", (hashlib.sha256(request.cookies.get("dt_session", "").encode()).hexdigest(),))
        response.delete_cookie("dt_session")
        return {"ok": True}

    @app.post("/api/auth/github-cli")
    def cli_login(request: Request, response: Response, ctl: Control = Depends(control)):
        if os.getenv("ALLOW_GH_CLI_AUTH", "true").lower() != "true" or request.client.host not in {"127.0.0.1", "::1", "testclient"}:
            raise HTTPException(403, "GitHub CLI authentication is available only on the local installation")
        profile, token = github_cli_identity()
        identity = f"github:{profile['id']}"
        rows = ctl.rows("SELECT id FROM users WHERE email=?", (identity,))
        if rows:
            user_id = rows[0]["id"]
        else:
            with ctl.connection() as db:
                db.execute("BEGIN IMMEDIATE")
                if db.execute("SELECT id FROM users LIMIT 1").fetchone():
                    raise ValueError("Sign in with your existing account, then connect GitHub CLI from Connectors")
                user_id = uid("user")
                db.execute("INSERT INTO users VALUES (?,?,?,?,?,?)", (user_id, profile.get("name") or profile["login"], identity, hash_password(secrets.token_urlsafe(40)), "admin", now()))
            new_workspace(ctl, user_id, profile["login"] + "'s company")
        set_session(ctl, user_id, response)
        return {"ok": True}

    @app.get("/api/me")
    def me(user: dict = Depends(current_user)):
        return user

    @app.get("/api/workspaces")
    def workspaces(user: dict = Depends(current_user), ctl: Control = Depends(control)):
        return ctl.rows("SELECT * FROM workspaces WHERE owner_id=? ORDER BY created_at", (user["id"],))

    @app.post("/api/workspaces")
    def add_workspace(body: Named, user: dict = Depends(current_user), ctl: Control = Depends(control)):
        result = new_workspace(ctl, user["id"], body.name)
        ctl.audit(user["id"], "workspace.created", result["id"])
        return result

    @app.get("/api/w/{workspace_id}/overview")
    def overview(ws=Depends(workspace), ctl: Control = Depends(control)):
        return {"graph": Knowledge(ws["graph_name"]).stats(),
                "sources": ctl.rows("SELECT count(*) AS count FROM sources WHERE workspace_id=? AND status<>'archived'", (ws["id"],))[0]["count"],
                "jobs": ctl.rows("SELECT id,kind,status,progress,total,message,updated_at FROM jobs WHERE workspace_id=? ORDER BY created_at DESC LIMIT 8", (ws["id"],)),
                "agents": ctl.rows("SELECT count(*) AS count FROM agents WHERE workspace_id=?", (ws["id"],))[0]["count"],
                "pending_reviews": ctl.rows("SELECT count(*) AS count FROM proposals WHERE workspace_id=? AND status='pending'", (ws["id"],))[0]["count"]}

    @app.get("/api/w/{workspace_id}/sources")
    def sources(ws=Depends(workspace), ctl: Control = Depends(control)):
        return ctl.rows("SELECT id,title,kind,uri,version,status,metadata,updated_at FROM sources WHERE workspace_id=? ORDER BY updated_at DESC", (ws["id"],))

    @app.get("/api/w/{workspace_id}/sources/{source_id}")
    def source_detail(source_id: str, ws=Depends(workspace), ctl: Control = Depends(control)):
        rows = ctl.rows("SELECT * FROM sources WHERE id=? AND workspace_id=?", (source_id, ws["id"]))
        if not rows:
            raise HTTPException(404, "Source not found")
        return {**rows[0], "history": Knowledge(ws["graph_name"]).history(source_id)}

    def queue_upload(ctl: Control, ws: dict, data: bytes, filename: str, request: Request):
        if Path(filename).suffix.lower() not in SUPPORTED:
            raise ValueError("Unsupported format. Use TXT, MD, CSV, JSON, PDF, DOCX, RST, LOG or YAML.")
        if len(data) > 10 * 1024 * 1024:
            raise ValueError("Files must be at most 10 MB")
        upload_dir = ctl.directory / "uploads"
        upload_dir.mkdir(exist_ok=True)
        file_id = uid("file")
        (upload_dir / file_id).write_bytes(data)
        job_id = ctl.job(ws["id"], "upload", {"file_id": file_id, "filename": filename})
        request.app.state.jobs.submit(job_id)
        return {"job_id": job_id}

    @app.post("/api/w/{workspace_id}/sources/upload")
    async def upload(request: Request, file: UploadFile = File(...), ws=Depends(workspace), ctl: Control = Depends(control)):
        filename = Path((file.filename or "upload.txt").replace("\\", "/")).name[:200]
        return queue_upload(ctl, ws, await file.read(10 * 1024 * 1024 + 1), filename, request)

    @app.post("/api/w/{workspace_id}/sources/text")
    def text_source(body: TextSource, request: Request, ws=Depends(workspace), ctl: Control = Depends(control)):
        filename = Path(body.title.replace("\\", "/")).name
        if Path(filename).suffix.lower() not in SUPPORTED:
            filename += ".md"
        return queue_upload(ctl, ws, body.content.encode(), filename, request)

    @app.post("/api/w/{workspace_id}/sources/{source_id}/enrich")
    def enrich(source_id: str, request: Request, max_chunks: int = 6, ws=Depends(workspace), ctl: Control = Depends(control)):
        if not ctl.rows("SELECT id FROM sources WHERE id=? AND workspace_id=?", (source_id, ws["id"])):
            raise HTTPException(404, "Source not found")
        job_id = ctl.job(ws["id"], "enrich", {"source_id": source_id, "max_chunks": min(max(max_chunks, 1), 30)})
        request.app.state.jobs.submit(job_id)
        return {"job_id": job_id}

    @app.get("/api/w/{workspace_id}/sources/{source_id}/diff")
    def source_diff(source_id: str, before_hash: str, ws=Depends(workspace), ctl: Control = Depends(control)):
        if not ctl.rows("SELECT id FROM sources WHERE id=? AND workspace_id=?",(source_id,ws["id"])):
            raise HTTPException(404,"Source not found")
        return Knowledge(ws["graph_name"]).compare_versions(source_id,before_hash)

    @app.get("/api/w/{workspace_id}/sources/{source_id}/changes")
    def source_changes(source_id: str, ws=Depends(workspace), ctl: Control = Depends(control)):
        if not ctl.rows("SELECT id FROM sources WHERE id=? AND workspace_id=?", (source_id, ws["id"])):
            raise HTTPException(404, "Source not found")
        return Knowledge(ws["graph_name"]).relationship_changes(source_id)

    @app.get("/api/w/{workspace_id}/analysis/conflicts")
    def conflicts(ws=Depends(workspace)):
        return {"candidates": Knowledge(ws["graph_name"]).conflict_candidates(),
                "note": "Candidates only: the same subject and relationship names different targets in different current sources. Review the quoted evidence."}

    @app.post("/api/w/{workspace_id}/sources/{source_id}/archive")
    def archive(source_id: str, ws=Depends(workspace), ctl: Control = Depends(control), user=Depends(current_user)):
        if not ctl.rows("SELECT id FROM sources WHERE id=? AND workspace_id=?", (source_id, ws["id"])):
            raise HTTPException(404, "Source not found")
        Knowledge(ws["graph_name"]).source_remove(source_id)
        ctl.execute("UPDATE sources SET status='archived',updated_at=? WHERE id=?", (now(), source_id))
        ctl.audit(user["id"], "source.archived", ws["id"], {"source_id": source_id})
        return {"ok": True}

    @app.get("/api/w/{workspace_id}/jobs")
    def jobs(ws=Depends(workspace), ctl: Control = Depends(control)):
        return ctl.rows("SELECT id,kind,status,progress,total,message,created_at,updated_at FROM jobs WHERE workspace_id=? ORDER BY created_at DESC LIMIT 100", (ws["id"],))

    @app.post("/api/w/{workspace_id}/jobs/{job_id}/retry")
    def retry(job_id: str, request: Request, ws=Depends(workspace), ctl: Control = Depends(control)):
        rows = ctl.rows("SELECT status FROM jobs WHERE id=? AND workspace_id=?", (job_id, ws["id"]))
        if not rows or rows[0]["status"] != "failed":
            raise ValueError("Only failed jobs can be retried")
        ctl.progress(job_id, "queued", "Retry queued")
        request.app.state.jobs.submit(job_id)
        return {"ok": True}

    @app.get("/api/w/{workspace_id}/graph")
    def graph(search: str = "", label: str = "", limit: int = 300, offset: int = 0, visible: str = "", ws=Depends(workspace)):
        ids = [int(x) for x in visible.split(",") if x.isdigit()][:10000]
        return Knowledge(ws["graph_name"]).explore(search, label, limit, offset, ids)

    @app.get("/api/w/{workspace_id}/graph/neighbors")
    def neighbors(entity_id: str, ws=Depends(workspace)):
        return Knowledge(ws["graph_name"]).neighbors(entity_id)

    @app.post("/api/w/{workspace_id}/graph/query")
    def graph_query(body: Query, ws=Depends(workspace)):
        try:
            return Knowledge(ws["graph_name"]).query(body.query)
        except Exception as exc:
            raise ValueError("Query could not run. Use valid read-only Cypher; writes and queries over 2 seconds are rejected.") from exc

    @app.get("/api/w/{workspace_id}/graph/impact")
    def graph_impact(entity_id: str, ws=Depends(workspace)):
        return {"state":"simulation","assumption":"Selected entity becomes unavailable","items":Knowledge(ws["graph_name"]).dependency_impact(entity_id),"mutated":False}

    @app.get("/api/connectors")
    def connectors(user=Depends(current_user), ctl: Control = Depends(control)):
        connections = ctl.rows("SELECT * FROM connections WHERE user_id=? AND provider='github_app'", (user["id"],))
        safe_connections = []
        for connection in connections:
            metadata = json.loads(ctl.cipher.decrypt(connection["secret"].encode()).decode())
            safe_connections.append({key:connection[key] for key in ("id","provider","login","created_at")} | {
                "repository_selection": metadata.get("repository_selection", "selected"),
                "manage_url": "https://github.com/settings/installations/" + str(int(metadata["installation_id"])),
            })
        return {"github_configured": bool(ctl.secret_get("github_app_id") and ctl.secret_get("github_app_private_key")),
                "connections": safe_connections}

    @app.get("/api/connectors/github/start")
    def start_github(user=Depends(admin), ctl: Control = Depends(control)):
        return RedirectResponse(install_url(ctl, user["id"]))

    @app.get("/api/connectors/github/app/register")
    def register_app(user=Depends(admin), ctl: Control = Depends(control)):
        origin = os.getenv("APP_ORIGIN", "http://127.0.0.1:8765").rstrip("/")
        data = manifest(ctl, user["id"], origin)
        return HTMLResponse('<!doctype html><html><head><title>Register DecisionTrail GitHub App</title></head><body><p>Continue to GitHub to review the app name and read permissions.</p><form id="manifest" method="post" action="' + html.escape(data['action'], quote=True) + '"><input type="hidden" name="manifest" value="' + html.escape(json.dumps(data['manifest']), quote=True) + '"><button>Review on GitHub</button></form><script>document.getElementById("manifest").submit()</script></body></html>')

    @app.get("/api/connectors/github/app/manifest/callback")
    def registered_app(code: str = "", state: str = "", user=Depends(admin), ctl: Control = Depends(control)):
        complete_manifest(ctl, user["id"], state, code)
        return RedirectResponse(install_url(ctl, user["id"]))

    @app.get("/api/connectors/github/app/setup")
    def installed_app(installation_id: int, state: str, user=Depends(admin), ctl: Control = Depends(control)):
        connect_installation(ctl, user["id"], installation_id, state)
        return RedirectResponse("/?view=connectors&github=connected")

    @app.get("/api/connectors/github/repositories")
    def repositories(page: int = 1, user=Depends(current_user), ctl: Control = Depends(control)):
        token = connection_token(ctl, user["id"])
        if not token:
            raise ValueError("Connect GitHub first")
        client = GitHub(token)
        try:
            return client.repositories(page, installation=True)
        finally:
            client.close()

    @app.post("/api/connectors/github/disconnect")
    def disconnect(user=Depends(current_user), ctl: Control = Depends(control)):
        ctl.execute("DELETE FROM connections WHERE user_id=? AND provider='github_app'", (user["id"],))
        return {"ok": True}

    @app.post("/api/w/{workspace_id}/connectors/github/sync")
    def sync(body: Sync, request: Request, ws=Depends(workspace), ctl: Control = Depends(control), user=Depends(current_user)):
        job_id = ctl.job(ws["id"], "github", body.model_dump())
        request.app.state.jobs.submit(job_id)
        ctl.audit(user["id"], "github.sync_requested", ws["id"], {"repository": body.repository})
        return {"job_id": job_id}

    @app.get("/api/w/{workspace_id}/agents")
    def agents(ws=Depends(workspace), ctl: Control = Depends(control)):
        return ctl.rows("SELECT * FROM agents WHERE workspace_id=? ORDER BY created_at", (ws["id"],))

    @app.post("/api/w/{workspace_id}/agents")
    def add_agent(body: AgentDefinition, ws=Depends(workspace), ctl: Control = Depends(control)):
        agent_id = uid("agent")
        ctl.execute("INSERT INTO agents VALUES (?,?,?,?,?)", (agent_id, ws["id"], body.name, body.instructions, now()))
        return {"id": agent_id}

    @app.put("/api/w/{workspace_id}/agents/{agent_id}")
    def update_agent(agent_id: str, body: AgentDefinition, ws=Depends(workspace), ctl: Control = Depends(control)):
        if not ctl.execute("UPDATE agents SET name=?,instructions=? WHERE id=? AND workspace_id=?", (body.name, body.instructions, agent_id, ws["id"])):
            raise HTTPException(404, "Agent not found")
        return {"ok": True}

    @app.post("/api/w/{workspace_id}/agents/{agent_id}/run")
    def run_agent(agent_id: str, body: Question, ws=Depends(workspace), ctl: Control = Depends(control)):
        rows = ctl.rows("SELECT * FROM agents WHERE id=? AND workspace_id=?", (agent_id, ws["id"]))
        if not rows:
            raise HTTPException(404, "Agent not found")
        return WorkspaceAgent(ctl, ws, rows[0]).run(body.question, body.use_ai)

    @app.get("/api/w/{workspace_id}/runs")
    def runs(ws=Depends(workspace), ctl: Control = Depends(control)):
        return ctl.rows("SELECT id,agent_id,question,response,created_at FROM runs WHERE workspace_id=? ORDER BY created_at DESC LIMIT 50", (ws["id"],))

    @app.get("/api/w/{workspace_id}/reviews")
    def reviews(ws=Depends(workspace), ctl: Control = Depends(control)):
        return ctl.rows("SELECT * FROM proposals WHERE workspace_id=? ORDER BY created_at DESC", (ws["id"],))

    @app.post("/api/w/{workspace_id}/reviews/{proposal_id}")
    def review(proposal_id: str, body: Review, ws=Depends(workspace), ctl: Control = Depends(control), user=Depends(current_user)):
        rows = ctl.rows("SELECT * FROM proposals WHERE id=? AND workspace_id=?", (proposal_id, ws["id"]))
        if not rows:
            raise HTTPException(404, "Review item not found")
        proposal = rows[0]
        if proposal["status"] != "pending":
            return {"status": proposal["status"]}
        if body.approve:
            graph = Knowledge(ws["graph_name"])
            graph.entity("task:" + proposal_id, proposal["title"], "Task", {"status": "open", "reason": proposal["reason"], "approved_by": user["name"]})
            graph.write("MATCH (t:Entity {id:$id}),(d:Document {id:$source}) MERGE (t)-[:SUPPORTED_BY]->(d)", {"id": "task:" + proposal_id, "source": proposal["source_id"]})
        status = "approved" if body.approve else "rejected"
        ctl.execute("UPDATE proposals SET status=?,reviewed_at=? WHERE id=? AND status='pending'", (status, now(), proposal_id))
        ctl.audit(user["id"], "review." + status, ws["id"], {"proposal_id": proposal_id})
        return {"status": status}

    @app.get("/api/admin/settings")
    def admin_settings(user=Depends(admin), ctl: Control = Depends(control)):
        return {"github_app_id": ctl.secret_get("github_app_id") or "",
                "github_app_slug": ctl.secret_get("github_app_slug") or "",
                "github_key_configured": bool(ctl.secret_get("github_app_private_key")),
                "openrouter_key_configured": bool(ctl.secret_get("openrouter_api_key") or os.getenv("OPENROUTER_API_KEY")),
                "openrouter_model": ctl.secret_get("openrouter_model") or settings.openrouter_model,
                "callback_url": os.getenv("APP_ORIGIN", "http://127.0.0.1:8765").rstrip("/") + "/api/connectors/github/app/setup"}

    @app.get("/api/w/{workspace_id}/tasks")
    def tasks(ws=Depends(workspace)):
        return Knowledge(ws["graph_name"]).tasks()

    @app.patch("/api/w/{workspace_id}/tasks/{task_id}")
    def task_update(task_id: str,body:TaskStatus,ws=Depends(workspace),ctl:Control=Depends(control),user=Depends(current_user)):
        graph=Knowledge(ws["graph_name"])
        if not graph.read("MATCH (t:Task {id:$id}) RETURN t.id AS id",{"id":task_id}):
            raise HTTPException(404,"Task not found")
        graph.write("MATCH (t:Task {id:$id}) SET t.status=$status",{"id":task_id,"status":body.status})
        ctl.audit(user["id"],"task.updated",ws["id"],{"task_id":task_id,"status":body.status})
        return {"ok":True}

    @app.put("/api/admin/settings")
    def save_settings(body: AppSettings, user=Depends(admin), ctl: Control = Depends(control)):
        if body.openrouter_model and not (body.openrouter_model.endswith(":free") or body.openrouter_model == "openrouter/free"):
            raise ValueError("Only free OpenRouter models are allowed")
        for key, value in body.model_dump().items():
            if value.strip():
                ctl.secret_set(key, value.strip())
        ctl.audit(user["id"], "settings.updated")
        return {"ok": True}

    @app.get("/api/admin/users")
    def users(user=Depends(admin), ctl: Control = Depends(control)):
        return ctl.rows("SELECT id,name,email,role,created_at FROM users ORDER BY created_at")

    @app.post("/api/admin/users")
    def add_user(body: Credentials, user=Depends(admin), ctl: Control = Depends(control)):
        if ctl.rows("SELECT id FROM users WHERE email=?", (body.email.lower().strip(),)):
            raise ValueError("An account with this email exists")
        user_id = uid("user")
        ctl.execute("INSERT INTO users VALUES (?,?,?,?,?,?)", (user_id, body.name, body.email.lower().strip(), hash_password(body.password), "member", now()))
        new_workspace(ctl, user_id, body.name + "'s workspace")
        ctl.audit(user["id"], "user.created", details={"user_id": user_id})
        return {"id": user_id}

    @app.get("/api/admin/audit")
    def audit_log(user=Depends(admin), ctl: Control = Depends(control)):
        return ctl.rows("SELECT * FROM audit ORDER BY created_at DESC LIMIT 100")

    @app.get("/api/health")
    def health():
        return {"status": "ok", "version": "0.2.0"}

    assets = Path(__file__).parent.parent / "frontend" / "dist"
    if (assets / "assets").exists():
        app.mount("/assets", StaticFiles(directory=assets / "assets"), name="assets")

    @app.get("/")
    def index():
        if not (assets / "index.html").exists():
            raise HTTPException(503, "Build the frontend: cd frontend && npm run build")
        return FileResponse(assets / "index.html")

    return app


app = create_app()
