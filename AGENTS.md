# Project Rules

- Always ask for explicit confirmation before running `git commit` or `git push`. Never stage, commit, amend, or push without the user's explicit approval.
- At the start of a session, read NOTES.md first — it contains the latest task state, environment, and priorities for the next agent.
- At the end of a session (or when state changes), update NOTES.md so the next agent has accurate environment, completed work, and ordered next steps.
- Environment is macOS (zsh); commands in NOTES.md are POSIX. Don't apply the historical Windows/pwsh commands.
- Prefer `uv` for backend Python deps (`backend/` uses `uv.lock`).
