"""Model wiring: LLM factory, tool-capability detection, and the agent graph.

All chat-model construction and graph assembly lives here — create_llm chooses
and configures the model, model_supports_tools decides whether to bind tools,
and get_graph builds the cached LangGraph from those parts.
"""

import asyncio
import logging
import os

import httpx
from langchain_core.messages import SystemMessage
from langchain_ollama import ChatOllama
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from .config import (
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    PLANNER_MODEL,
    PLANNER_TIMEOUT,
    PLANNER_PROMPT,
    SYSTEM_PROMPT,
)
from .graph_state import (
    AgentState,
    ExecutionPlan,
    RESPONDER_INTENTS,
    fallback_plan,
    route_intent,
)
from .persistence import open_checkpointer
from .tools import TOOLS
from .workspace import get_current, load_workspace_guidelines

logger = logging.getLogger("app.agent")

_graph = None


def system_prompt_for_current() -> str:
    """Base system prompt plus the active workspace's guidelines.md, if any."""
    try:
        ws = get_current()
        guidelines = load_workspace_guidelines(ws.root_path).strip()
    except Exception:  # pragma: no cover - never block a chat on prompt building
        logger.exception("failed to load workspace guidelines")
        return SYSTEM_PROMPT
    if not guidelines:
        return SYSTEM_PROMPT
    return (
        f"{SYSTEM_PROMPT}\n\n"
        f"Workspace: {ws.name} (root: {ws.root_path})\n"
        f"Follow these workspace guidelines:\n{guidelines}"
    )


def create_llm(model: str = OLLAMA_MODEL, bind_tools: bool = True) -> ChatOllama:
    llm = ChatOllama(
        model=model,
        base_url=OLLAMA_BASE_URL,
        temperature=0.2,
        num_predict=1024,
        num_ctx=4096,
    )
    if bind_tools and model_supports_tools():
        llm = llm.bind_tools(TOOLS)
        logger.info("Model %s: tool calling enabled", model)
    elif bind_tools:
        logger.info("Model %s: tool calling not supported, chat-only", model)
    return llm


def model_supports_tools(model: str = OLLAMA_MODEL) -> bool:
    """Check Ollama's /api/tags for a 'tools' capability on the given model."""
    if os.getenv("FORCE_TOOLS") == "1":
        return True
    if os.getenv("DISABLE_TOOLS") == "1":
        return False
    try:
        resp = httpx.get(f"{OLLAMA_BASE_URL.rstrip('/')}/api/tags", timeout=5)
        resp.raise_for_status()
        for entry in resp.json().get("models", []):
            name = entry.get("name", "")
            # Match "phi3" or "phi3:latest" when configured as "phi3".
            if name == model or name.startswith(f"{model}:"):
                return "tools" in entry.get("capabilities", [])
    except Exception:
        pass
    # Assume tool support if Ollama cannot be inspected; degrade gracefully on 400.
    return True


def _agent_node(llm: ChatOllama) -> callable:
    def agent(state: AgentState) -> dict:
        messages = [SystemMessage(content=system_prompt_for_current()), *state["messages"]]
        return {
            "messages": [llm.invoke(messages)],
            "current_agent": "agent",
            "agent_status": "running",
        }

    return agent


def _planner_node(structured_planner) -> callable:
    async def planner(state: AgentState) -> dict:
        messages = [SystemMessage(content=PLANNER_PROMPT), *state["messages"]]
        try:
            plan = await asyncio.wait_for(
                structured_planner.ainvoke(messages), timeout=PLANNER_TIMEOUT
            )
            if not isinstance(plan, ExecutionPlan):
                plan = ExecutionPlan.model_validate(plan)
        except Exception as exc:  # noqa: BLE001 - planner must never block a reply
            logger.warning("planner failed: %s", exc)
            fallback = fallback_plan(type(exc).__name__)
            return {
                "detected_intent": fallback.intent,
                "execution_plan": fallback.model_dump(),
                "current_agent": "agent",
                "agent_status": "planning_failed",
                "errors": [f"planner: {exc}"],
            }
        logger.info("planner intent=%s steps=%d", plan.intent, len(plan.steps))
        return {
            "detected_intent": plan.intent,
            "execution_plan": plan.model_dump(),
            "current_agent": "responder" if plan.intent in RESPONDER_INTENTS else "agent",
            "agent_status": "planned",
            "clarification_needed": plan.needs_clarification,
        }

    return planner


def _responder_node(llm: ChatOllama) -> callable:
    def responder(state: AgentState) -> dict:
        messages = [SystemMessage(content=system_prompt_for_current()), *state["messages"]]
        return {
            "messages": [llm.invoke(messages)],
            "current_agent": "responder",
            "agent_status": "done",
        }

    return responder


def _build_graph(checkpointer: AsyncSqliteSaver):
    llm = create_llm()
    responder_llm = create_llm(bind_tools=False)
    planner_llm = create_llm(PLANNER_MODEL, bind_tools=False)
    structured_planner = planner_llm.with_structured_output(ExecutionPlan)

    graph = StateGraph(AgentState)
    graph.add_node("planner", _planner_node(structured_planner))
    graph.add_node("responder", _responder_node(responder_llm))
    graph.add_node("agent", _agent_node(llm))
    graph.add_node("tools", ToolNode(TOOLS))

    graph.add_edge(START, "planner")
    graph.add_conditional_edges(
        "planner",
        route_intent,
        {"responder": "responder", "agent": "agent"},
    )
    graph.add_edge("responder", END)
    graph.add_conditional_edges("agent", tools_condition)
    graph.add_edge("tools", "agent")
    graph.add_edge("agent", END)

    return graph.compile(checkpointer=checkpointer)


async def get_graph():
    """Return a cached compiled graph sharing the SQLite checkpointer."""
    global _graph
    if _graph is None:
        checkpointer = await open_checkpointer()
        _graph = _build_graph(checkpointer)
    return _graph