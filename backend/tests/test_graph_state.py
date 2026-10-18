"""Unit tests for Phase 1: typed state, plan validation, and intent routing.

These are pure-logic tests: no Ollama, no database. The planner node is
exercised with a fake structured-output runnable so success and failure paths
are covered deterministically.
"""

import asyncio

import pytest

from app.graph_state import (
    INTENTS,
    NODE_AGENT,
    NODE_RESPONDER,
    RESPONDER_INTENTS,
    AgentState,
    ExecutionPlan,
    PlanStep,
    fallback_plan,
    route_intent,
)


def test_agent_state_declares_plan_fields():
    keys = AgentState.__annotations__
    for field in (
        "messages",
        "detected_intent",
        "execution_plan",
        "current_agent",
        "agent_status",
        "clarification_needed",
        "errors",
        "final_response",
    ):
        assert field in keys, f"AgentState missing {field}"


@pytest.mark.parametrize("intent", INTENTS)
def test_route_intent_covers_every_intent(intent):
    assert route_intent({"detected_intent": intent}) in (NODE_RESPONDER, NODE_AGENT)


@pytest.mark.parametrize("intent", sorted(RESPONDER_INTENTS))
def test_route_intent_sends_conversational_intents_to_responder(intent):
    assert route_intent({"detected_intent": intent}) == NODE_RESPONDER


@pytest.mark.parametrize(
    "intent", [i for i in INTENTS if i not in RESPONDER_INTENTS]
)
def test_route_intent_sends_actionable_intents_to_agent(intent):
    assert route_intent({"detected_intent": intent}) == NODE_AGENT


def test_route_intent_defaults_to_agent_when_unset():
    assert route_intent({}) == NODE_AGENT


def test_execution_plan_accepts_valid_plan():
    plan = ExecutionPlan(
        intent="CODE",
        summary="add a helper",
        steps=[PlanStep(description="write util")],
    )
    assert plan.intent == "CODE"
    assert len(plan.steps) == 1


def test_execution_plan_rejects_unknown_intent():
    with pytest.raises(Exception):
        ExecutionPlan(intent="NONSENSE")


def test_execution_plan_rejects_blank_step():
    with pytest.raises(Exception):
        ExecutionPlan(intent="CODE", steps=[PlanStep(description="")])


def test_execution_plan_caps_steps_at_eight():
    steps = [PlanStep(description=f"step {i}") for i in range(12)]
    plan = ExecutionPlan(intent="MULTI_STEP", steps=steps)
    assert len(plan.steps) <= 8


def test_fallback_plan_is_actionable():
    plan = fallback_plan("TimeoutError")
    assert plan.intent == "MULTI_STEP"
    assert "TimeoutError" in plan.summary
    assert plan.steps


@pytest.mark.asyncio
async def test_planner_node_returns_validated_plan():
    from app.model import _planner_node

    class FakeStructured:
        async def ainvoke(self, _messages):
            return ExecutionPlan(
                intent="EXPLAIN",
                summary="explain the file",
                steps=[PlanStep(description="read the file")],
            )

    node = _planner_node(FakeStructured())
    result = await node({"messages": []})
    assert result["detected_intent"] == "EXPLAIN"
    assert result["current_agent"] == NODE_RESPONDER
    assert result["execution_plan"]["summary"] == "explain the file"


@pytest.mark.asyncio
async def test_planner_node_falls_back_on_error():
    from app.model import _planner_node

    class BrokenStructured:
        async def ainvoke(self, _messages):
            raise RuntimeError("model exploded")

    node = _planner_node(BrokenStructured())
    result = await node({"messages": []})
    assert result["detected_intent"] == "MULTI_STEP"
    assert result["current_agent"] == NODE_AGENT
    assert result["agent_status"] == "planning_failed"
    assert result["errors"]


@pytest.mark.asyncio
async def test_planner_node_falls_back_on_timeout(monkeypatch):
    from app import model
    from app.model import _planner_node

    monkeypatch.setattr(model, "PLANNER_TIMEOUT", 0)

    class SlowStructured:
        async def ainvoke(self, _messages):
            await asyncio.sleep(1)
            return ExecutionPlan(intent="CODE")

    node = _planner_node(SlowStructured())
    result = await node({"messages": []})
    assert result["detected_intent"] == "MULTI_STEP"
    assert result["errors"]


def test_build_graph_compiles_with_planner_and_responder(monkeypatch):
    monkeypatch.setenv("DISABLE_TOOLS", "1")
    from app.model import _build_graph

    graph = _build_graph(checkpointer=None)
    nodes = set(graph.get_graph().nodes)
    assert {"planner", "responder", "agent", "tools"} <= nodes
