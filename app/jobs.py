from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.control import Control
from app.connectors import sync_repository
from app.ingestion import Ingestor, parse_file

logger = logging.getLogger(__name__)


class Jobs:
    def __init__(self, control: Control):
        self.control = control
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ingestion")

    def resume(self):
        for row in self.control.rows("SELECT id FROM jobs WHERE status IN ('queued','running') ORDER BY created_at"):
            self.submit(row["id"])

    def submit(self, job_id: str):
        self.pool.submit(self.run, job_id)

    def run(self, job_id: str):
        rows = self.control.rows("SELECT * FROM jobs WHERE id=?", (job_id,))
        if not rows or rows[0]["status"] == "completed":
            return
        job = rows[0]
        workspace = self.control.rows("SELECT * FROM workspaces WHERE id=?", (job["workspace_id"],))[0]
        payload = json.loads(job["payload"])
        self.control.progress(job_id, "running", "Processing source")
        try:
            ingestor = Ingestor(self.control, workspace)
            if job["kind"] == "github":
                sync_repository(self.control, workspace, payload, job_id)
                return
            if job["kind"] == "enrich":
                result = ingestor.enrich(payload["source_id"], payload.get("max_chunks", 6))
                self.control.progress(job_id, "completed", f"Accepted {result['relations']} evidenced relationships; enriched {result['processed_chunks']}/{result['total_chunks']} passages." , result["processed_chunks"], result["total_chunks"])
                return
            path = (self.control.directory / "uploads" / payload["file_id"]).resolve()
            if path.parent != (self.control.directory / "uploads").resolve():
                raise ValueError("Invalid stored upload path")
            text, structured = parse_file(payload["filename"], path.read_bytes())
            result = ingestor.source("upload:" + payload["filename"], payload["filename"], "upload", text, structured=structured)
            self.control.progress(job_id, "completed", f"Indexed {result['chunks']} passages; source version {result['version']}" + (" (unchanged)" if not result["changed"] else ""), result["chunks"], result["chunks"])
        except Exception as exc:
            logger.warning("Job %s failed (%s)", job_id, type(exc).__name__)
            public_message = str(exc) if isinstance(exc, ValueError) else f"{type(exc).__name__}: operation failed. Retry after checking the connector and source."
            self.control.progress(job_id, "failed", public_message)

    def close(self):
        self.pool.shutdown(wait=False)
