# Session Handover Notes

Snapshot for the next agent session (generated 2026-09-22). Branch: `feature/genui-streaming` (latest commits `0f59a8b` recent dropdown, `8b9382d` sidebar workspace list; this note + pending changes are the next commit).

## Environment
- OS: Windows (win32), shell pwsh. Backend at `:8000` (headless uvicorn from `backend/`), frontend vite at `:5173`.
- Model: `llama3.1:8b` via Ollama (`http://localhost:11434`). DB: `backend/db/agent_state.db`.
- `testing/` is gitignored; suite `testing/run_all_checks.py` (105 checks) takes ~15 min.
- **Rules**: never delete user files/threads/logs; never `git commit`/`git push` without explicit user approval; no comments in code unless asked.
- Pitfalls: backend files are CRLF (edit with exact/large anchors); never use `$PID` in PowerShell; suite's `request(method, path, body)` expects a **dict** body (it JSON-encodes); processes spawned in this shell are headless (no GUI dialogs) — the OS folder-picker was removed for that reason; custom in-page picker is the design.

## Done & committed (earlier)
- **M1 workspaces**: per-workspace file/tool scoping via `.local_agent_workspace`, workspace CRUD API+UI, chat threads private per workspace (`workspace_id` guard), Runs scoped to active workspace.
- **Folder picker**: custom in-page picker (Up/Home/This PC/New Folder), starts at user home, `~` expansion server-side, remembers last path + top-10 recent paths dropdown (localStorage).
- **Sidebar**: workspace list + New workspace form + Activate/Delete live in the app's left sidebar (only the list scrolls); main `Spaces` pane shows the selected workspace's config.

## This session's changes (uncommitted until now)
- **`.local_agent_workspace` is now a FOLDER** (was a JSON file):
  - `.local_agent_workspace/config.json` = policy (safe/unsafe/allowed/exemptions).
  - `.local_agent_workspace/guidelines.md` = free-form rules **injected into the agent system prompt** (`app/model.py: system_prompt_for_current()`).
  - Legacy `.local_agent_workspace` JSON file auto-migrates to the folder (content preserved).
  - API `GET/PATCH /workspaces` returns/accepts `guidelines`; `create_workspace` seeds a template `guidelines.md`.
  - UI: guidelines editor added below the policy editor (`WorkspacesView.tsx`).
  - Tests updated: config path now points at folder `config.json`; added 2 guidelines checks.
- **HITL approval UI**: removed the "Approve & Allow once" button; narrowed `allow` type to `'always'`; HITL card disappears after any decision (`ChatView.tsx`).

## Next priorities (in order)
1. **Cross-platform portability — user's explicit highest priority, NOT yet started.**
   - `app/shell.py:76` uses `shell=True` → spawns `cmd.exe` on Windows; make shell selection platform-aware (Windows `ver`/`where.com` vs POSIX `uname`/`which`); command tables in shell/approvals.
   - Folder browse `<drives>` sentinel is Windows-only (`_WINDOWS_DRIVES` in `app/main.py`; `workspace.py`), returns empty on POSIX — map it to filesystem root `/` on POSIX; keep drive letters on Windows. Browse This-PC-at-drive-root logic assumes `X:\` shape. `mkdir` name validation rejects `<>:"|?*` (Windows-only chars) — restrict to `/`+NUL on POSIX.
   - Verify path handling (`Path`, `os.path.expanduser`, `.local_agent_workspace` folder) and `config.py` startup on mac/Linux; frontend already portable.
   - Goal: user can run backend on Windows, macOS, or Linux.
2. **Workspace context flakiness (bug found, fix NOT implemented)** — `workspace.py` `_current` is a module-global mutable; concurrent chats / mid-chat workspace activation leak between requests and can false-403 a continuation ("Thread belongs to another workspace"). Proposed: make the request/thread workspace context per-request (e.g., contextvar) and base the `/chat` guard on that, instead of the shared global.
3. **Full E2E suite re-run** — last green baseline `testing/logs/e2e_20260921_131049.log` (105/0) predates the folder/guidelines + browse-home changes. Launch detached, poll `backend.err.log` for the `==== SUMMARY ====` banner.
4. **Roadmap for later** (from `todo.txt`): SearXNG docker web-search API; page viewer/summarizer (obscura/playwright); agent task decomposition + todo UI; agent re-plans tasks; git drift/fetch before push.

## Typical commands
- Restart backend: stop the `:8000` listener, then `WScript.Shell.Run('cmd /c "cd /d <repo>\backend && .venv\Scripts\uvicorn.exe app.main:app --port 8000 > backend.out.log 2> backend.err.log"', 0)`; poll `/health`.
- Frontend: `npm run dev` (vite, HMR); build `npm run build`; lint `npm run lint` (0 errors).
- Probe scripts live under `C:\Users\VIJAYK~1\AppData\Local\Temp\opencode\` (throwaway): `chat_probe.py`, `ws_folder_probe.py`, `db_trace.py`, etc.