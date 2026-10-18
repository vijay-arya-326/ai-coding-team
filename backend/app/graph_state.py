"""Typed shared graph state, planner schema, and intent routing.

The planner classifies each user turn into one intent and returns a validated
``ExecutionPlan``. Routing sends conversational intents to a direct responder
and actionable intents to the tool-using agent. Everything here is pure logic
so it can be unit tested without a model or database.
"""

import operator
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph import MessagesState
from pydantic import BaseModel, Field, field_validator

Intent = Literal[
    "QUESTION",
    "EXPLAIN",
    "CODE",
    "MODIFY",
    "DEBUG",
    "GENERATE_TESTS",
    "RUN_TESTS",
    "REVIEW",
    "MULTI_STEP",
]

INTENTS: tuple[Intent, ...] = (
    "QUESTION",
    "EXPLAIN",
    "CODE",
    "MODIFY",
    "DEBUG",
    "GENERATE_TESTS",
    "RUN_TESTS",
    "REVIEW",
    "MULTI_STEP",
)

# Conversational intents are answered directly; the rest go to the agent.
RESPONDER_INTENTS: frozenset[str] = frozenset({"QUESTION", "EXPLAIN"})

# Nodes an intent can route to.
NODE_RESPONDER = "responder"
NODE_AGENT = "agent"


class AgentState(MessagesState):
    """Conversation messages plus the planner's structured output.

    ``messages`` comes from MessagesState. File references (paths) live here
    instead of large contents or binary data.
    """

    detected_intent: str
    execution_plan: dict | None
    current_agent: str
    agent_status: str
    clarification_needed: bool
    errors: Annotated[list[str], operator.add]
    final_response: str


class PlanStep(BaseModel):
    """A single actionable step in an execution plan."""

    description: str = Field(..., min_length=1, max_length=500)
    agent: str = Field(
        default="agent",
        description="Which agent should perform the step (agent, coder, tester, reviewer).",
    )


class ExecutionPlan(BaseModel):
    """Validated planner output: an intent plus a short ordered plan."""

    intent: Intent
    summary: str = Field(default="", max_length=1000)
    steps: list[PlanStep] = Field(default_factory=list)
    needs_clarification: bool = False
    clarification_question: str = Field(default="", max_length=500)

    @field_validator("steps")
    @classmethod
    def _cap_steps(cls, steps: list[PlanStep]) -> list[PlanStep]:
        return steps[:8]


def route_intent(state: AgentState) -> str:
    """Map the detected intent to the next node name."""
    if state.get("detected_intent") in RESPONDER_INTENTS:
        return NODE_RESPONDER
    return NODE_AGENT


def fallback_plan(reason: str) -> ExecutionPlan:
    """Plan used when the planner model fails, times out, or returns garbage.

    Falls back to the tool-using agent so the user still gets a response.
    """
    return ExecutionPlan(
        intent="MULTI_STEP",
        summary=f"Planner unavailable ({reason}); proceeding with the tool-using agent.",
        steps=[PlanStep(description="Handle the request with the tool-using agent.")],
    )
