"""Bounded graph-first agent; LangChain supplies optional free-model wording."""

from __future__ import annotations

import json
import os
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from app.config import settings
from app.graph import GraphStore


class DecisionAgent:
    def __init__(self, store: GraphStore, model: BaseChatModel | None = None):
        self.store = store
        self.model = model
        if model is None and os.getenv("OPENROUTER_API_KEY"):
            from app.openrouter_model import OpenRouterFreeChatModel

            if not (settings.openrouter_model == "openrouter/free" or settings.openrouter_model.endswith(":free")):
                raise ValueError("OPENROUTER_MODEL must be a free OpenRouter model")
            self.model = OpenRouterFreeChatModel(
                model_name=settings.openrouter_model,
                max_tokens=400,
                request_timeout=15,
            )

    def answer(self, question: str, topic: str = "atlas-launch") -> dict[str, Any]:
        """Route only to an allowlisted tool plan, then ground optional wording in results."""
        if not question.strip():
            raise ValueError("Question is required")
        history = self.store.tool_call("decision_history", topic=topic)
        current = history["result"].get("current")
        trace = [self._trace(history)]
        if not current:
            return {"state": "unknown_topic", "answer": "No decision is recorded for this topic.", "evidence": {}, "trace": trace}

        q = question.lower()
        if any(word in q for word in ("before", "previous", "history", "original", "when was")):
            evidence = {"history": history["result"]}
            fallback = "Decision history: " + "; ".join(
                f"{v['statement']} (valid from {v['valid_from']})" for v in history["result"]["versions"]
            )
        elif any(word in q for word in ("stale", "outdated", "conflict", "document", "brief")):
            drift = self.store.tool_call("find_stale_claims", decision_id=current["id"])
            trace.append(self._trace(drift))
            evidence = {"decision": current, "drift": drift["result"]}
            rows = drift["result"]["items"]
            fallback = "Outdated claims: " + (
                "; ".join(f"{r['source']}: {r['statement']}" for r in rows) if rows else "none recorded."
            )
        else:
            impact = self.store.tool_call("impact_of_change", decision_id=current["id"])
            trace.append(self._trace(impact))
            evidence = {"decision": current, "impact": impact["result"]}
            rows = impact["result"]["items"]
            fallback = "Connected affected work: " + (
                "; ".join(f"{r['name']} via {' → '.join(r['path'])}" for r in rows)
                if rows else "no dependency path is recorded."
            )

        answer = self._word(question, evidence, fallback)
        return {"state": "answered", "answer": answer, "evidence": evidence, "trace": trace,
                "model_used": answer != fallback}

    @staticmethod
    def _trace(call: dict[str, Any]) -> dict[str, Any]:
        result = call["result"]
        count = len(result.get("items", result.get("versions", [])))
        return {"tool": call["tool"], "arguments": call["arguments"],
                "duration_ms": call["duration_ms"], "rows": count, "state": result.get("state", "found")}

    def _word(self, question: str, evidence: dict[str, Any], fallback: str) -> str:
        if self.model is None:
            return fallback
        try:
            response = self.model.invoke([
                SystemMessage(content=(
                    "You explain company graph evidence. Use ONLY the JSON evidence provided. "
                    "Do not invent people, projects, dates, causation, or actions. "
                    "Say when a relationship is merely recorded or missing. "
                    "Use at most three sentences."
                )),
                HumanMessage(content=f"Question: {question}\nEvidence JSON: {json.dumps(evidence, default=str)}"),
            ])
            text = response.content if isinstance(response.content, str) else ""
            if not text.strip():
                return fallback
            # A generated explanation can omit items, but cannot introduce new proper names.
            known_names = {
                str(value).lower()
                for value in self._all_values(evidence)
                if isinstance(value, str)
            }
            known_tokens = {token for value in known_names for token in value.replace(":", " ").split()}
            protected = ["atlas", "beacon", "maya", "priya", "leo"]
            if any(name in text.lower() and name not in known_tokens for name in protected):
                return fallback
            return text.strip()
        except Exception:
            return fallback

    @classmethod
    def _all_values(cls, obj: Any) -> list[Any]:
        if isinstance(obj, dict):
            return [v for value in obj.values() for v in cls._all_values(value)]
        if isinstance(obj, list):
            return [v for value in obj for v in cls._all_values(value)]
        return [obj]
