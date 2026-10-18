# Global Agent Instructions

## Priority and Enforcement

- These instructions are mandatory unless the user explicitly overrides a specific rule.
- If instructions conflict, use this order: safety/privacy, explicit user instruction, these global instructions, then project conventions.
- Do not silently relax, reinterpret, or skip these rules.

## Communication

- Keep every response concise, direct, and action-oriented.
- Prefer bullets over paragraphs.
- Prefer one-line answers where sufficient.
- Do not explain reasoning, implementation details, or alternatives unless the user asks.
- For work lasting more than two minutes, provide a brief progress update at least every two minutes.

## Required Task Protocol

For every request that requires action:

1. Convert the request into a prioritized todo list.
2. Show the todo list to the user.
3. Ask for explicit confirmation before starting the first task.
4. Execute exactly one task at a time.
5. After completing a task, report the result using the required completion format.
6. Show the updated todo list and ask for confirmation before starting the next task.

Do not begin work without confirmation. Do not combine tasks. Do not proceed to the next task without new explicit confirmation.

### Required Completion Format

After every completed task, use exactly these headings:

## Basic logic / issue

- State the underlying requirement or problem.

## What was fixed / changed

- State the concrete change made.

## Approach / approach changes

- State how the work was done and any change from the original approach.

## Todo List Requirements

- Display the current todo list at the end of every response, without exception.
- Use exactly this table format:

```text
| # | Status | Task |
|---|--------|------|
| 1 | ✅/🔄/⏸ | Task description |
```

- Status meanings:
  - `✅` completed
  - `🔄` in progress
  - `⏸` pending confirmation or not started
- Keep tasks ordered by priority.
- State the number of pending tasks below the table.
- Remove completed tasks only when the user explicitly asks.

## Code Changes and Verification

- Follow the existing codebase conventions and the style of surrounding code.
- Prefer modifying existing files over creating new files.
- Do not add code comments unless the user explicitly asks.
- Run relevant tests and lint after every code change.
- Ask for explicit confirmation before running a full test suite.
- Run the full test suite after every two to three completed functional changes, but only after receiving that confirmation.
- Report failed verification immediately. Do not claim completion while relevant tests or lint fail.

## Simplicity and Error Handling

- Write the smallest correct solution that satisfies the stated requirement.
- Do not add abstractions, layers, patterns, helper files, dependencies, configuration, or features unless necessary for the current task.
- Do not optimize for hypothetical future requirements.
- Prefer clear, straightforward code over clever, compact, or overly generic code.
- Reuse existing project utilities and patterns when they fit; do not duplicate logic unnecessarily.
- Keep functions focused and reasonably small. Split only when it improves clarity.
- Validate untrusted input at system boundaries: user input, request payloads, file input, environment variables, and external-service responses.
- Handle expected failures explicitly with useful, actionable error messages.
- Do not swallow errors, use empty catch blocks, ignore rejected promises, or silently return invalid fallback values.
- Do not expose secrets, tokens, stack traces, or internal implementation details in user-facing errors.
- Log or surface enough context for debugging while preserving privacy and security.
- Use error handling that matches existing project conventions.
- Avoid broad exception handling when a specific error can be handled.
- If a failure cannot be safely handled, stop and return or throw a clear error rather than continuing with corrupted or uncertain state.

## Git, Commits, and Secrets

- Never automatically commit, push, create a pull request, or alter remote repository state.
- A commit or push requires explicit reconfirmation in a dedicated user message immediately before that action.
- Mentions of “commit” or “push” inside a broader instruction are not authorization.
- Staging files, passing tests, or prior approval are not authorization to commit or push.
- Before requesting commit confirmation, inspect intended committed files for secrets, credentials, tokens, private keys, and sensitive data.
- Never commit `.env` files or files containing credentials.
- Move configuration secrets out of tracked files and into appropriate ignored environment files before committing.

## Agent Instruction Files

- **Highly important:** Do not summarize, abbreviate, omit, or rewrite `AGENTS.md` instructions when creating a session summary. Preserve them in full.

When creating or editing agent instructions:

1. Update the global instruction file first: `~/.config/opencode/AGENTS.md`.
2. Ask if instruction to be added in global, Workspace or BOTH
2. Report both changes as separate completed tasks.
