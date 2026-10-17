from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    host: str = os.getenv("FALKORDB_HOST", "localhost")
    port: int = int(os.getenv("FALKORDB_PORT", "6379"))
    graph: str = os.getenv("FALKORDB_GRAPH", "decisiontrail")
    username: str | None = os.getenv("FALKORDB_USERNAME") or None
    password: str | None = os.getenv("FALKORDB_PASSWORD") or None
    ssl: bool = os.getenv("FALKORDB_SSL", "false").lower() in {"true", "1", "yes"}
    openrouter_model: str = os.getenv("OPENROUTER_MODEL", "liquid/lfm-2.5-2.6b:free")


settings = Settings()
