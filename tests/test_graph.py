from __future__ import annotations

import uuid

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from app.agent import DecisionAgent
from app.graph import GraphStore
from app.seed import seed


@pytest.fixture
def graph():
    name = "decisiontrail_test_" + uuid.uuid4().hex[:10]
    seed(reset=True, graph_name=name)
    store = GraphStore(name)
    yield store
    store.graph.delete()


def change(graph: GraphStore):
    return graph.commit_decision(
        "atlas-launch", "2026-10-23", "Atlas moves to Friday after localization delay.",
        "2026-10-17T09:00:00+05:30", "fixture-change",
    )


def test_seed_has_three_hop_path_and_negative_control(graph: GraphStore):
    impact = graph.impact_of_change("decision:atlas-tuesday")
    by_id = {item["id"]: item for item in impact["items"]}
    assert by_id["milestone:atlas-launch"]["hops"] == 0
    assert by_id["commitment:partner-preview"]["path"] == [
        "decision:atlas-tuesday", "milestone:atlas-launch", "deliverable:launch-brief",
        "deliverable:partner-announcement", "commitment:partner-preview",
    ]
    assert "deliverable:beacon-brief" not in by_id


def test_preview_does_not_mutate(graph: GraphStore):
    before = graph.summary()
    preview = graph.preview_decision("atlas-launch", "2026-10-23")
    assert preview["state"] == "simulation"
    assert preview["delta_days"] == 3
    assert graph.summary() == before
    assert graph.decision_history("atlas-launch")["current"]["value"] == "2026-10-20"


def test_change_preserves_history_and_finds_stale_claim(graph: GraphStore):
    result = change(graph)
    assert result["state"] == "committed"
    assert graph.decision_history("atlas-launch")["current"]["value"] == "2026-10-23"
    assert graph.decision_history("atlas-launch", "2026-10-16T12:00:00+05:30")["current"]["value"] == "2026-10-20"
    assert result["drift"]["items"][0]["source_id"] == "source:atlas-brief"
    assert result["drift"]["items"][0]["owner"] == "Priya"
    assert graph.commit_decision("atlas-launch", "2026-10-23", "Atlas moves to Friday after localization delay.",
                                 "2026-10-17T09:00:00+05:30", "fixture-change")["state"] == "already_committed"


def test_actions_are_reviewed_once_and_missing_owner_is_blocked(graph: GraphStore):
    decision_id = change(graph)["decision_id"]
    actions = graph.actions(decision_id)
    partner = next(a for a in actions if a["target_id"] == "deliverable:partner-announcement")
    social = next(a for a in actions if a["target_id"] == "deliverable:social-kit")
    assert social["status"] == "needs_owner"
    with pytest.raises(ValueError, match="owner"):
        graph.review_action(social["id"], True, "Tester")
    assert graph.review_action(partner["id"], True, "Tester")["state"] == "approved"
    assert graph.review_action(partner["id"], True, "Tester")["state"] == "already_reviewed"
    updated = next(a for a in graph.actions(decision_id) if a["id"] == partner["id"])
    assert updated["current_value"] == "2026-10-23"


def test_rejection_keeps_target_unchanged(graph: GraphStore):
    decision_id = change(graph)["decision_id"]
    partner = next(a for a in graph.actions(decision_id) if a["target_id"] == "commitment:partner-preview")
    assert graph.review_action(partner["id"], False, "Tester", "Check with partner")["state"] == "rejected"
    after = next(a for a in graph.actions(decision_id) if a["id"] == partner["id"])
    assert after["current_value"] == "2026-10-20"


def test_unknown_and_missing_are_distinct(graph: GraphStore):
    assert graph.find_owner("deliverable:social-kit")["state"] == "missing_owner"
    assert graph.find_owner("not-here")["state"] == "unknown_entity"
    assert graph.trace_why("decision:atlas-tuesday", "deliverable:beacon-brief")["state"] == "not_connected_in_graph"


def test_langchain_fake_model_and_fallback(graph: GraphStore):
    model = FakeListChatModel(responses=["The Atlas launch affects the launch brief and partner announcement."])
    answer = DecisionAgent(graph, model=model).answer("What is affected?")
    assert answer["model_used"] is True
    assert len(answer["trace"]) == 2
    assert answer["evidence"]["impact"]["items"]
    fallback = DecisionAgent(graph, model=FakeListChatModel(responses=[""])).answer("What is affected?")
    assert fallback["model_used"] is False
    assert "Connected affected work" in fallback["answer"]
