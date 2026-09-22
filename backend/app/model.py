"""Model wiring: LLM factory, tool-capability detection, and the agent graph.

All chat-model construction and graph assembly lives here — create_llm chooses
and configures the model, model_supports_tools decides whether to bind tools,
and get_graph builds the cached LangGraph from those parts.
"""

import logging
import os

import httpx
from langchain_core.messages import SystemMessage
from langchain_ollama import ChatOllama
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, MessagesState, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from .config import OLLAMA_BASE_URL, OLLAMA_MODEL, SYSTEM_PROMPT
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


def create_llm() -> ChatOllama:
    llm = ChatOllama(
        model=OLLAMA_MODEL,
        base_url=OLLAMA_BASE_URL,
        temperature=0.2,
        num_predict=1024,
        num_ctx=4096,
    )
    if model_supports_tools():
        llm = llm.bind_tools(TOOLS)
        logger.info("Model %s: tool calling enabled", OLLAMA_MODEL)
    else:
        logger.info("Model %s: tool calling not supported, chat-only", OLLAMA_MODEL)
    return llm


def model_supports_tools() -> bool:
    """Check Ollama's /api/tags for a 'tools' capability on the configured model."""
    if os.getenv("FORCE_TOOLS") == "1":
        return True
    if os.getenv("DISABLE_TOOLS") == "1":
        return False
    try:
        resp = httpx.get(f"{OLLAMA_BASE_URL.rstrip('/')}/api/tags", timeout=5)
        resp.raise_for_status()
        for model in resp.json().get("models", []):
            name = model.get("name", "")
            # Match "phi3" or "phi3:latest" when configured as "phi3".
            if name == OLLAMA_MODEL or name.startswith(f"{OLLAMA_MODEL}:"):
                return "tools" in model.get("capabilities", [])
    except Exception:
        pass
    # Assume tool support if Ollama cannot be inspected; degrade gracefully on 400.
    return True


def _agent_node(llm: ChatOllama) -> callable:
    def agent(state: MessagesState) -> dict:
        messages = [SystemMessage(content=system_prompt_for_current()), *state["messages"]]
        return {"messages": [llm.invoke(messages)]}

    return agent


def _build_graph(checkpointer: AsyncSqliteSaver):
    llm = create_llm()

    graph = StateGraph(MessagesState)
    graph.add_node("agent", _agent_node(llm))
    graph.add_node("tools", ToolNode(TOOLS))

    graph.add_edge(START, "agent")
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