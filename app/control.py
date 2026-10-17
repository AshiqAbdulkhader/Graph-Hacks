"""Persistent local control plane. Company relationships live in FalkorDB."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def uid(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(10)}"


class Control:
    def __init__(self, directory: str | Path | None = None):
        self.directory = Path(directory or os.getenv("DECISIONTRAIL_DATA_DIR", ".data")).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "workspace.sqlite3"
        key_path = self.directory / "encryption.key"
        if not key_path.exists():
            try:
                with key_path.open("xb") as stream:
                    stream.write(Fernet.generate_key())
            except FileExistsError:
                pass
        self.cipher = Fernet(key_path.read_bytes())
        with self.connection() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,name TEXT,email TEXT UNIQUE,password TEXT,role TEXT,created_at TEXT);
            CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id TEXT,expires_at REAL);
            CREATE TABLE IF NOT EXISTS workspaces(id TEXT PRIMARY KEY,name TEXT,owner_id TEXT,graph_name TEXT UNIQUE,created_at TEXT);
            CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY,workspace_id TEXT,external_id TEXT,title TEXT,kind TEXT,uri TEXT,content TEXT,content_hash TEXT,version INTEGER,status TEXT,metadata TEXT,created_at TEXT,updated_at TEXT,UNIQUE(workspace_id,external_id));
            CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,workspace_id TEXT,kind TEXT,status TEXT,payload TEXT,progress INTEGER,total INTEGER,message TEXT,created_at TEXT,updated_at TEXT);
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);
            CREATE TABLE IF NOT EXISTS connections(id TEXT PRIMARY KEY,user_id TEXT,provider TEXT,login TEXT,secret TEXT,created_at TEXT);
            CREATE TABLE IF NOT EXISTS oauth_states(state TEXT PRIMARY KEY,user_id TEXT,verifier TEXT,expires_at REAL);
            CREATE TABLE IF NOT EXISTS agents(id TEXT PRIMARY KEY,workspace_id TEXT,name TEXT,instructions TEXT,created_at TEXT);
            CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY,workspace_id TEXT,agent_id TEXT,question TEXT,response TEXT,created_at TEXT);
            CREATE TABLE IF NOT EXISTS audit(id TEXT PRIMARY KEY,user_id TEXT,workspace_id TEXT,event TEXT,details TEXT,created_at TEXT);
            CREATE TABLE IF NOT EXISTS proposals(id TEXT PRIMARY KEY,workspace_id TEXT,title TEXT,target_id TEXT,source_id TEXT,reason TEXT,status TEXT,created_at TEXT,reviewed_at TEXT);
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=20)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def rows(self, sql: str, params=()) -> list[dict]:
        with self.connection() as db:
            return [dict(row) for row in db.execute(sql, params).fetchall()]

    def execute(self, sql: str, params=()):
        with self.connection() as db:
            return db.execute(sql, params).rowcount

    def secret_set(self, key: str, value: str):
        encrypted = self.cipher.encrypt(value.encode()).decode()
        self.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (key, encrypted))

    def secret_get(self, key: str) -> str | None:
        rows = self.rows("SELECT value FROM settings WHERE key=?", (key,))
        return self.cipher.decrypt(rows[0]["value"].encode()).decode() if rows else None

    def audit(self, user_id: str, event: str, workspace_id: str = "", details: dict | None = None):
        self.execute("INSERT INTO audit VALUES (?,?,?,?,?,?)", (uid("audit"), user_id, workspace_id, event, json.dumps(details or {}), now()))

    def job(self, workspace_id: str, kind: str, payload: dict) -> str:
        job_id = uid("job")
        self.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?)",
                     (job_id, workspace_id, kind, "queued", json.dumps(payload), 0, 0, "Waiting to start", now(), now()))
        return job_id

    def progress(self, job_id: str, status: str, message: str, progress: int = 0, total: int = 0):
        self.execute("UPDATE jobs SET status=?,message=?,progress=?,total=?,updated_at=? WHERE id=?",
                     (status, message[:1000], progress, total, now(), job_id))


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 600_000).hex()
    return f"{salt}:{digest}"


def check_password(password: str, encoded: str) -> bool:
    salt, expected = encoded.split(":", 1)
    actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 600_000).hex()
    return hmac.compare_digest(actual, expected)
