from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.agent import DecisionAgent
from app.graph import GraphStore


app = FastAPI(title="DecisionTrail", version="0.1.0")


@lru_cache
def get_store() -> GraphStore:
    return GraphStore()


def store_dependency() -> GraphStore:
    return get_store()


def _run(call):
    try:
        return call()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Graph operation failed: {type(exc).__name__}") from exc


class DecisionInput(BaseModel):
    topic: str = "atlas-launch"
    value: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    source_text: str = Field(min_length=1, max_length=4000)
    effective_at: str
    event_id: str = Field(min_length=1, max_length=128)


class PreviewInput(BaseModel):
    topic: str = "atlas-launch"
    value: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


class QuestionInput(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    topic: str = "atlas-launch"


class ReviewInput(BaseModel):
    approve: bool
    reviewer: str = Field(min_length=1, max_length=100)
    reason: str = Field(default="", max_length=1000)


@app.get("/")
def index():
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.get("/api/health")
def health(store: GraphStore = Depends(store_dependency)):
    return _run(store.summary)


@app.get("/api/decisions/{topic}/history")
def history(topic: str, as_of: str | None = None, store: GraphStore = Depends(store_dependency)):
    return _run(lambda: store.decision_history(topic, as_of))


@app.post("/api/decisions/preview")
def preview(body: PreviewInput, store: GraphStore = Depends(store_dependency)):
    return _run(lambda: store.preview_decision(body.topic, body.value))


@app.post("/api/decisions/commit")
def commit(body: DecisionInput, store: GraphStore = Depends(store_dependency)):
    return _run(lambda: store.commit_decision(**body.model_dump()))


@app.get("/api/decisions/{decision_id}/impact")
def impact(decision_id: str, depth: int = 4, store: GraphStore = Depends(store_dependency)):
    return _run(lambda: store.impact_of_change(decision_id, depth))


@app.get("/api/decisions/{decision_id}/drift")
def drift(decision_id: str, store: GraphStore = Depends(store_dependency)):
    return _run(lambda: store.find_stale_claims(decision_id))


@app.get("/api/actions")
def actions(decision_id: str | None = None, store: GraphStore = Depends(store_dependency)):
    return _run(lambda: store.actions(decision_id))


@app.post("/api/actions/{action_id}/review")
def review(action_id: str, body: ReviewInput, store: GraphStore = Depends(store_dependency)):
    return _run(lambda: store.review_action(action_id, **body.model_dump()))


@app.post("/api/questions")
def question(body: QuestionInput, store: GraphStore = Depends(store_dependency)):
    return _run(lambda: DecisionAgent(store).answer(body.question, body.topic))


@app.get("/api/entities/{entity_id}/owner")
def owner(entity_id: str, store: GraphStore = Depends(store_dependency)):
    return _run(lambda: store.find_owner(entity_id))


@app.get("/api/trace")
def trace(from_id: str, to_id: str, store: GraphStore = Depends(store_dependency)):
    return _run(lambda: store.trace_why(from_id, to_id))
