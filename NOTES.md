# Session Handover Notes

Snapshot for the next agent session (updated 2026-10-02). Branch: `feature/genui-streaming` (base HEAD `1506176`). This snapshot: `app/logging.py` → `app/logconfig.py` rename (+ `main.py` import) to stop stdlib shadowing, NOTES quick-start refresh, `llama3.1:8b` pulled to Ollama (chat smoke-tested OK, tools enabled). Smoke-test residue: untracked `tmp/output.txt` + thread `thread_b9d9b9c52a634886b657bfb28569b2a6`.

## Environment
- **OS: macOS (darwin), shell zsh.** Repo: `/Users/vj/Sites/official/ai-coding-team`. (Sessions before 2026-10-02 ran on Windows/pwsh.)
- Backend: uvicorn on `:8000` — **verified booting on macOS 2026-10-02** (`{"status":"ok"}`), DB `backend/db/agent_state.db` fine.
- Frontend: vite on `:5173`, `frontend/node_modules` installed.
- Python: venv at `backend/.venv` (uv-managed, `uv` at `~/.local/bin/uv`). Ollama (`http://localhost:11434`) reachable; pulled models: `llama3.1:8b` (app default, `OLLAMA_MODEL` in `config.py:9`, tools-capable), `qwen2.5vl:7b`, `qwen2.5vl:3b`, `phi3:latest`, `gemma4:e2b`, `LLAMA3.2:latest`, `mistral:latest`, `gemma:latest`. NOTE: the compiled agent graph caches tool-capability at first chat request — restart backend after pulling a model.
- **Do not add PyPI `logging` as a dependency** (a bogus `logging>=0.4.9.6` was briefly added while debugging the import error, then removed) — never depend on packages whose names shadow stdlib.
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

## Quick start — run services (OS-independent)

`<project_root>` = repo root (this file's folder). Forward slashes work in zsh/bash and PowerShell; on cmd.exe use backslashes. Requires: [uv](https://docs.astral.sh/uv), Node.js, Ollama with a pulled model.

### Backend → http://localhost:8000
```sh
cd <project_root>/backend
uv sync                                  # first time: creates .venv
uv run uvicorn app.main:app --reload --port 8000
```
Expected:
```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Application startup complete.
```
Verify:
```sh
curl http://localhost:8000/health
# {"status":"ok"}
```
- Docs: http://localhost:8000/docs | Stop: kill the listener on port 8000 (`lsof -nP -iTCP:8000 -sTCP:LISTEN` to find PID).
- Logs: file `backend/logs/app.log` (daily rotation, 7-day retention) + stderr.

### Frontend → http://localhost:5173
```sh
cd <project_root>/frontend
npm install                               # first time
npm run dev                               # vite, HMR
```
Expected (vite ~8.x):
```
  VITE v8.x.x  ready in <n> ms
  ➜  Local:   http://localhost:5173/
```
- Build: `npm run build` | Lint: `npm run lint`

### Model config
- Backend talks to Ollama at `OLLAMA_MODEL` (default `llama3.1:8b`, `config.py:9`) — already pulled and smoke-tested 2026-10-02; override the env var to switch models (no `.env` exists).
