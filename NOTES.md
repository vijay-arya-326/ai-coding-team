# Session Handover Notes

Snapshot for the next agent session (updated 2026-10-02). Branch: `feature/genui-streaming` (HEAD `89d11cc`; uncommitted: `frontend/package-lock.json` only).

## Environment
- **OS: macOS (darwin), shell zsh.** Repo: `/Users/vj/Sites/official/ai-coding-team`. (Older snapshots were Windows/pwsh — Windows-specific commands below are historical only.)
- Backend: uvicorn on `:8000` — **verified booting on macOS 2026-10-02** (`{"status":"ok"}`), DB `backend/db/agent_state.db` fine.
- Frontend: vite on `:5173`, `frontend/node_modules` installed.
- Python: venv at `backend/.venv` (created by `uv`, Python 3.14.7, `uv` at `~/.local/bin/uv`). Model: `llama3.1:8b` via Ollama (`http://localhost:11434`) — **not yet verified reachable on this Mac.**
- `testing/` E2E suite (105 checks, ~15 min) is gitignored and **not present on this machine** — needs to be copied/restored before any suite run.
- **Rules**: never delete user files/threads/logs; never `git commit`/`git push` without explicit user approval; no comments in code unless asked.
- Pitfalls: backend files are CRLF (edit with exact/large anchors); suite's `request(method, path, body)` expects a **dict** body; processes are headless (no GUI dialogs) — custom in-page folder picker is the design; zsh has no `timeout` (use `gtimeout` or background+poll).

## Done & committed
- **M1 workspaces**: per-workspace file/tool scoping via `.local_agent_workspace` folder (`config.json` policy + `guidelines.md` injected into system prompt at `app/model.py: system_prompt_for_current()`), workspace CRUD API+UI, chat threads private per workspace, Runs scoped to active workspace; legacy JSON file auto-migrates.
- **Folder picker**: custom in-page picker (Up/Home/This PC/New Folder), `~` expansion server-side, remembers last path + top-10 recent paths (localStorage).
- **Sidebar**: workspace list + New workspace form + Activate/Delete in left sidebar; main `Spaces` pane shows selected workspace's config (incl. guidelines editor).
- **HITL approval UI**: "Approve & Allow once" removed; `allow` type narrowed to `'always'`; HITL card disappears after any decision.

## Next priorities (in order)
1. **Cross-platform portability — user's explicit highest priority. Now runnable on macOS, so POSIX can be tested directly.**
   - `app/shell.py:76` uses `shell=True` → spawns POSIX `sh` here, `cmd.exe` on Windows; make shell selection platform-aware (Windows `ver`/`where.com` vs POSIX `uname`/`which`); command tables in shell/approvals.
   - Folder browse `<drives>` sentinel is Windows-only (`_WINDOWS_DRIVES` in `app/main.py:131`, `app/main.py:417`; `workspace.py`) — returns empty on POSIX; map to filesystem root `/` on POSIX; keep drive letters on Windows.
   - `mkdir` name validation rejects `<>:"|?*` (Windows-only chars) — restrict to `/`+NUL on POSIX.
   - Verify `Path`/`os.path.expanduser`/config startup on mac/Linux (backend boot already OK); frontend already portable.
   - Goal: backend runs on Windows, macOS, or Linux.
2. **Workspace context flakiness (bug found, fix NOT implemented)** — `workspace.py` `_current` is a module-global mutable; concurrent chats / mid-chat workspace activation can false-403 ("Thread belongs to another workspace"). Proposed fix: per-request workspace context (contextvar) and base the `/chat` guard on it.
3. **Restore + re-run full E2E suite** — `testing/` missing on this Mac; last green baseline was `testing/logs/e2e_20260921_131049.log` (105/0) on Windows, predating folder/guidelines + browse-home changes.
4. **Roadmap for later** (from `todo.txt`): SearXNG docker web-search API; page viewer/summarizer (obscura/playwright); agent task decomposition + todo UI; agent re-plans tasks; git drift/fetch before push.

## Typical commands
- Restart backend: stop the `:8000` listener, then `WScript.Shell.Run('cmd /c "cd /d <repo>\backend && .venv\Scripts\uvicorn.exe app.main:app --port 8000 > backend.out.log 2> backend.err.log"', 0)`; poll `/health`.
- Frontend: `npm run dev` (vite, HMR); build `npm run build`; lint `npm run lint` (0 errors).
- Probe scripts live under `C:\Users\VIJAYK~1\AppData\Local\Temp\opencode\` (throwaway): `chat_probe.py`, `ws_folder_probe.py`, `db_trace.py`, etc.
## Quick start (how to run services)

### Backend
`powershell
cd C:\Users\VijayKumar\Desktop\Projects\personal\vj\ai-coding-team\backend
.\.venv\Scripts\uvicorn.exe app.main:app --reload --port 8000
`
Or run from backend dir: uv run uvicorn app.main:app --reload --port 8000

Health: http://localhost:8000/health | Docs: http://localhost:8000/docs

### Frontend
`powershell
cd C:\Users\VijayKumar\Desktop\Projects\personal\vj\ai-coding-team\frontend
npm install  # first time
npm run dev
`
Runs at http://localhost:5173

## Quick start (how to run services)

### Backend
`powershell
cd C:\Users\VijayKumar\Desktop\Projects\personal\vj\ai-coding-team\backend
.\.venv\Scripts\uvicorn.exe app.main:app --reload --port 8000
` 
Or run from backend dir: uv run uvicorn app.main:app --reload --port 8000

Health: http://localhost:8000/health | Docs: http://localhost:8000/docs

### Frontend
`powershell
cd C:\Users\VijayKumar\Desktop\Projects\personal\vj\ai-coding-team\frontend
npm install  # first time
npm run dev
` 
Runs at http://localhost:5173
