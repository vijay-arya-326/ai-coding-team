# Todo List — Local Multimodal AI Coding Agent

Source: `docs/plan.md`

## Phase 0 — Inspect the Existing Repository

- [ ] Map the current frontend, backend, API, streaming, configuration, and tests.
- [ ] Run the existing application and test suite.
- [ ] Document existing endpoints, event formats, and state management.
- [ ] Identify reusable modules and gaps against the plan.
- [ ] Record a baseline so regressions can be detected.

**Exit criteria:** Existing functionality is understood and a small, repository-specific task plan is recorded. No working code has been replaced unnecessarily.

## Phase 1 — LangGraph Integration

- [x] Define typed shared `AgentState`.
- [x] Add graph nodes and edges using the existing backend conventions.
- [x] Integrate the existing Qwen3 4B model as the planner.
- [x] Implement intent routing for `QUESTION`, `EXPLAIN`, `CODE`, `MODIFY`, `DEBUG`, `GENERATE_TESTS`, `RUN_TESTS`, `REVIEW`, and `MULTI_STEP`.
- [x] Make the planner return validated structured plans.
- [x] Handle clarification, model errors, and timeouts.
- [x] Connect graph events to the existing streaming mechanism.
- [x] Add unit tests for state updates, routing, and plan validation.

Suggested state fields: `conversation_id`, `run_id`, `user_message`, `attachments`, `image_analysis`, `audio_transcript`, `file_context`, `detected_intent`, `execution_plan`, `current_agent`, `agent_status`, `code_changes`, `generated_test_files`, `tool_results`, `test_results`, `review_results`, `iteration_count`, `pending_approval`, `errors`, `final_response`.

Store file references in state rather than large file contents or binary data.

**Exit criteria:** A text request flows through the existing chat, planner, and LangGraph, with progress streamed to the UI. ✅ *(plan event streamed; UI rendering deferred to Phase 7)*

**Notes:** Implemented in `backend/app/graph_state.py` + `model.py`; see `docs/architecture.md`. Planner model defaults to `OLLAMA_MODEL` (`qwen3:4b` not installed on target). 29 tests pass.

## Phase 2 — Controlled Tools and Coding Agent

- [ ] Integrate Qwen2.5-Coder 3B through the local model runtime.
- [ ] Implement validated tools: `list_files`, `read_file`, `search_code`, `write_file`, `patch_file`, and `get_project_structure`.
- [ ] Restrict all file operations to a configured workspace.
- [ ] Prevent path traversal and unsafe overwrites.
- [ ] Prefer targeted patches over rewriting entire files.
- [ ] Record changed-file paths and concise diffs.
- [ ] Show code and file-change cards in the chat.
- [ ] Add tests for path validation, tool inputs, and file operations.

**Exit criteria:** The agent can inspect and make a controlled, verifiable change inside the workspace.

## Phase 3 — Testing Agent and Test Runner

- [ ] Use Qwen2.5-Coder 3B to generate test scenarios and test files.
- [ ] Start with Python and pytest; add Playwright only where required.
- [ ] Cover positive cases, negative cases, edge cases, and stated requirements.
- [ ] Implement a deterministic test runner in application code.
- [ ] Capture exit code, stdout, stderr, duration, passed, failed, skipped, and error details.
- [ ] Add execution timeouts and output limits.
- [ ] Display test summaries and failure details in the chat.
- [ ] Test successful, failing, timed-out, and invalid test runs.

**Exit criteria:** Tests are actually executed and the application reports real results rather than model-generated claims.

## Phase 4 — Reviewer and Fix/Retest Loop

- [ ] Use Qwen3 4B to review the original request, plan, changes, and actual test results.
- [ ] Return a validated review with status, requirements met, issues, suggested fixes, and summary.
- [ ] Route passing results to final response.
- [ ] Route failures to the coding agent, then rerun tests and review.
- [ ] Set `MAX_ITERATIONS = 3`.
- [ ] Stop on success, iteration limit, unrecoverable error, or required approval.
- [ ] Do not repeat an unchanged failing operation.
- [ ] Preserve results from each iteration and report remaining failures honestly.

**Exit criteria:** The graph completes a bounded coding → testing → execution → review cycle and terminates correctly.

## Phase 5 — Image and Screenshot Processing

- [ ] Add image upload to the existing React composer.
- [ ] Validate image format and size.
- [ ] Integrate Qwen2.5-VL 3B locally.
- [ ] Extract relevant UI elements, visible text, errors, layouts, and context.
- [ ] Preserve the original attachment reference.
- [ ] Pass image analysis and user instructions together to the normalizer and planner.
- [ ] Test image-only and text-plus-image requests.
- [ ] Handle missing model, invalid image, and inference failures gracefully.

**Exit criteria:** A user can attach a screenshot and request an explanation, code change, or test plan using the same chat.

## Phase 6 — Audio Processing

- [ ] Add audio upload and microphone recording where browser permissions allow.
- [ ] Integrate local Whisper Small or Base transcription.
- [ ] Normalize the transcript alongside the original user message.
- [ ] Retain attachment metadata and transcript for the conversation.
- [ ] Test clear speech, empty audio, unsupported formats, and transcription errors.
- [ ] Keep audio processing optional for text-only requests.

**Exit criteria:** Audio requests are transcribed locally and routed through the same workflow as text requests.

## Phase 7 — Chat Events and Agent Activity

- [ ] Standardize streaming event schemas while preserving current chat streaming.
- [ ] Support events: `run_started`, `agent_started`, `agent_progress`, `agent_message`, `plan_created`, `tool_started`, `tool_completed`, `file_modified`, `test_started`, `test_completed`, `approval_required`, `error`, and `final_response`.
- [ ] Include run ID, timestamp, event type, and relevant data.
- [ ] Render concise inline activity cards, plans, code changes, and test results.
- [ ] Handle disconnects and duplicate events safely.
- [ ] Avoid exposing hidden chain-of-thought; show user-facing summaries and actions.

**Exit criteria:** The user can follow the workflow in the conversation without navigating to a separate dashboard.

## Phase 8 — Persistence and Recovery

- [ ] Add SQLite persistence if not already present.
- [ ] Persist conversations, messages, attachment metadata, run summaries, plans, tool results, approvals, and test results.
- [ ] Add LangGraph checkpointing for resumable execution.
- [ ] Store attachment files separately and persist references.
- [ ] Implement conversation listing, retrieval, and deletion.
- [ ] Isolate data by conversation and run.
- [ ] Test restart recovery and interrupted runs.

**Exit criteria:** Conversation history survives application restarts and graph state can be recovered where supported.

## Phase 9 — Safety, Approval, and Isolation

- [ ] Enforce workspace-only filesystem access.
- [ ] Validate every tool's schema and authorization before execution.
- [ ] Allowlist test commands and avoid arbitrary shell execution.
- [ ] Require approval for destructive or sensitive operations.
- [ ] Apply timeouts, output limits, and resource limits.
- [ ] Use Docker isolation for generated or untrusted code when available.
- [ ] Never expose secrets to generated code or logs.
- [ ] Fail closed if safe execution is unavailable.
- [ ] Log tool actions and approval decisions.

**Exit criteria:** Unsafe actions are blocked or explicitly approved, and test execution has defined limits.

## Phase 10 — Integration, Regression, and Documentation

- [ ] Run backend unit and integration tests.
- [ ] Run frontend tests and build.
- [ ] Verify existing chat and streaming still work.
- [ ] Verify planner routing and state updates.
- [ ] Verify code changes remain inside the workspace.
- [ ] Verify actual test results drive reviewer decisions.
- [ ] Verify the retry limit is enforced.
- [ ] Verify image, audio, and combined multimodal requests.
- [ ] Verify missing models, timeouts, invalid files, and disconnected clients.
- [ ] Update README, architecture notes, setup steps, and troubleshooting.
- [ ] Document completed features and known limitations accurately.

---

## Phase Status

| Phase | Status |
|-------|--------|
| 0 — Inspect Repository | ⏸ pending |
| 1 — LangGraph Integration | ✅ implemented (29 tests pass) |
| 2 — Controlled Tools + Coding Agent | ⏸ pending |
| 3 — Testing Agent + Test Runner | ⏸ pending |
| 4 — Reviewer + Fix/Retest Loop | ⏸ pending |
| 5 — Image/Screenshot Processing | ⏸ pending |
| 6 — Audio Processing | ⏸ pending |
| 7 — Chat Events + Agent Activity | ⏸ pending |
| 8 — Persistence + Recovery | ⏸ pending |
| 9 — Safety, Approval, Isolation | ⏸ pending |
| 10 — Integration, Regression, Docs | ⏸ pending |
