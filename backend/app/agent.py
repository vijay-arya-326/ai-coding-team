"""Public facade for the AI agent backend.

Keeps the previous flat import surface while the implementation now lives in
focused modules:
  config        central constants/env overrides
  shell         shell classification/execution
  approvals     pending approvals + command exemptions
  tools         agent tools (filesystem, shell, calculator)
  persistence   SQLite threads/runs repository
  db            SQLite connection + schema/migrations
  model         LLM wiring and agent graph
"""

from .approvals import (  # noqa: F401
    ONE_TIME_ALLOWED,
    PENDING_APPROVALS,
    PERMANENT_ALLOWED,
    APPROVAL_TTL,
    grant_exception,
    resolve_approval,
)
from .config import (  # noqa: F401
    ALLOWED_COMMANDS_FILE,
    APP_TITLE,
    APP_VERSION,
    BASE_DIR,
    GENERATION_IDLE_TIMEOUT,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    PREVIEW_LIMIT,
    PROJECT_ROOT,
    RECURSION_LIMIT,
    SHELL_TIMEOUT,
    SYSTEM_PROMPT,
    THREADS_DB_PATH,
)
from .model import get_graph  # noqa: F401
from .persistence import (  # noqa: F401
    _now,
    close_checkpointer,
    delete_thread,
    ensure_thread_meta,
    get_thread,
    list_threads,
    open_checkpointer,
    record_message,
    record_runs,
    runs_summary,
    thread_runs,
    update_thread_meta,
)
from .shell import (  # noqa: F401
    SAFE_COMMANDS,
    UNSAFE_MARKERS,
    classify_command,
    run_shell,
)
from .tools import (  # noqa: F401
    TOOLS,
    calculator,
    create_dir,
    create_file,
    delete_file,
    delete_folder,
    edit_file,
    rename_file,
    run_shell_command,
)