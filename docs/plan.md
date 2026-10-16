# Local Multimodal AI Coding Agent --- Implementation Plan

## 1. Current State

The initial MVP is already implemented and working:

-   React chat UI
-   FastAPI backend
-   Ollama integration
-   Qwen3 4B local model
-   Streaming chat responses

**Do not rebuild or duplicate these components.** First inspect the
repository, preserve working behavior, and extend the existing
implementation.

## 2. Target Architecture

``` text
React Chat UI (existing)
  ├── Text
  ├── Image ──> Qwen2.5-VL 3B ──┐
  ├── Audio ──> Whisper ─────────┤
  └── Files ─────────────────────┤
                                 v
                         Input Normalizer
                                 v
                       LangGraph Router
                                 v
                         Qwen3 4B Planner
                                 |
                  +--------------+--------------+
                  |              |              |
                Coding         Testing         Review
             Qwen2.5-Coder  Qwen2.5-Coder    Qwen3 4B
                  |              |
               Code files     Test files
                  +------+-------+
                         v
                    Test Runner
                  pytest / Docker
                         v
                    Test Results
                         v
                      Reviewer
                         |
                    +----+----+
                    |         |
                   PASS      FAIL
                    |         |
               Final reply   Coder -> Test Runner
```

All inference should run locally. Verify the exact Ollama model tags and
capabilities on the target machine. The application---not the LLM---must
validate and execute tool calls.

## 3. Implementation Phases

### Phase 0 --- Inspect the Existing Repository

-   [ ] Map the current frontend, backend, API, streaming,
    configuration, and tests.
-   [ ] Run the existing application and test suite.
-   [ ] Document existing endpoints, event formats, and state
    management.
-   [ ] Identify reusable modules and gaps against this plan.
-   [ ] Record a baseline so regressions can be detected.

**Exit criteria:** Existing functionality is understood and a small,
repository-specific task plan is recorded. No working code has been
replaced unnecessarily.

### Phase 1 --- LangGraph Integration

-   [ ] Define typed shared `AgentState`.
-   [ ] Add graph nodes and edges using the existing backend
    conventions.
-   [ ] Integrate the existing Qwen3 4B model as the planner.
-   [ ] Implement intent routing for `QUESTION`, `EXPLAIN`, `CODE`,
    `MODIFY`, `DEBUG`, `GENERATE_TESTS`, `RUN_TESTS`, `REVIEW`, and
    `MULTI_STEP`.
-   [ ] Make the planner return validated structured plans.
-   [ ] Handle clarification, model errors, and timeouts.
-   [ ] Connect graph events to the existing streaming mechanism.
-   [ ] Add unit tests for state updates, routing, and plan validation.

Suggested state fields:

-   `conversation_id`, `run_id`, `user_message`, `attachments`
-   `image_analysis`, `audio_transcript`, `file_context`
-   `detected_intent`, `execution_plan`, `current_agent`, `agent_status`
-   `code_changes`, `generated_test_files`, `tool_results`
-   `test_results`, `review_results`, `iteration_count`
-   `pending_approval`, `errors`, `final_response`

Store file references in state rather than large file contents or binary
data.

**Exit criteria:** A text request flows through the existing chat,
planner, and LangGraph, with progress streamed to the UI.

### Phase 2 --- Controlled Tools and Coding Agent

-   [ ] Integrate Qwen2.5-Coder 3B through the local model runtime.
-   [ ] Implement validated tools: `list_files`, `read_file`,
    `search_code`, `write_file`, `patch_file`, and
    `get_project_structure`.
-   [ ] Restrict all file operations to a configured workspace.
-   [ ] Prevent path traversal and unsafe overwrites.
-   [ ] Prefer targeted patches over rewriting entire files.
-   [ ] Record changed-file paths and concise diffs.
-   [ ] Show code and file-change cards in the chat.
-   [ ] Add tests for path validation, tool inputs, and file operations.

**Exit criteria:** The agent can inspect and make a controlled,
verifiable change inside the workspace.

### Phase 3 --- Testing Agent and Test Runner

-   [ ] Use Qwen2.5-Coder 3B to generate test scenarios and test files.
-   [ ] Start with Python and pytest; add Playwright only where
    required.
-   [ ] Cover positive cases, negative cases, edge cases, and stated
    requirements.
-   [ ] Implement a deterministic test runner in application code.
-   [ ] Capture exit code, stdout, stderr, duration, passed, failed,
    skipped, and error details.
-   [ ] Add execution timeouts and output limits.
-   [ ] Display test summaries and failure details in the chat.
-   [ ] Test successful, failing, timed-out, and invalid test runs.

**Exit criteria:** Tests are actually executed and the application
reports real results rather than model-generated claims.

### Phase 4 --- Reviewer and Fix/Retest Loop

-   [ ] Use Qwen3 4B to review the original request, plan, changes, and
    actual test results.
-   [ ] Return a validated review with status, requirements met, issues,
    suggested fixes, and summary.
-   [ ] Route passing results to final response.
-   [ ] Route failures to the coding agent, then rerun tests and review.
-   [ ] Set `MAX_ITERATIONS = 3`.
-   [ ] Stop on success, iteration limit, unrecoverable error, or
    required approval.
-   [ ] Do not repeat an unchanged failing operation.
-   [ ] Preserve results from each iteration and report remaining
    failures honestly.

**Exit criteria:** The graph completes a bounded coding → testing →
execution → review cycle and terminates correctly.

### Phase 5 --- Image and Screenshot Processing

-   [ ] Add image upload to the existing React composer.
-   [ ] Validate image format and size.
-   [ ] Integrate Qwen2.5-VL 3B locally.
-   [ ] Extract relevant UI elements, visible text, errors, layouts, and
    context.
-   [ ] Preserve the original attachment reference.
-   [ ] Pass image analysis and user instructions together to the
    normalizer and planner.
-   [ ] Test image-only and text-plus-image requests.
-   [ ] Handle missing model, invalid image, and inference failures
    gracefully.

**Exit criteria:** A user can attach a screenshot and request an
explanation, code change, or test plan using the same chat.

### Phase 6 --- Audio Processing

-   [ ] Add audio upload and microphone recording where browser
    permissions allow.
-   [ ] Integrate local Whisper Small or Base transcription.
-   [ ] Normalize the transcript alongside the original user message.
-   [ ] Retain attachment metadata and transcript for the conversation.
-   [ ] Test clear speech, empty audio, unsupported formats, and
    transcription errors.
-   [ ] Keep audio processing optional for text-only requests.

**Exit criteria:** Audio requests are transcribed locally and routed
through the same workflow as text requests.

### Phase 7 --- Chat Events and Agent Activity

-   [ ] Standardize streaming event schemas while preserving current
    chat streaming.
-   [ ] Support events such as `run_started`, `agent_started`,
    `agent_progress`, `agent_message`, `plan_created`, `tool_started`,
    `tool_completed`, `file_modified`, `test_started`, `test_completed`,
    `approval_required`, `error`, and `final_response`.
-   [ ] Include run ID, timestamp, event type, and relevant data.
-   [ ] Render concise inline activity cards, plans, code changes, and
    test results.
-   [ ] Handle disconnects and duplicate events safely.
-   [ ] Avoid exposing hidden chain-of-thought; show user-facing
    summaries and actions.

**Exit criteria:** The user can follow the workflow in the conversation
without navigating to a separate dashboard.

### Phase 8 --- Persistence and Recovery

-   [ ] Add SQLite persistence if not already present.
-   [ ] Persist conversations, messages, attachment metadata, run
    summaries, plans, tool results, approvals, and test results.
-   [ ] Add LangGraph checkpointing for resumable execution.
-   [ ] Store attachment files separately and persist references.
-   [ ] Implement conversation listing, retrieval, and deletion.
-   [ ] Isolate data by conversation and run.
-   [ ] Test restart recovery and interrupted runs.

**Exit criteria:** Conversation history survives application restarts
and graph state can be recovered where supported.

### Phase 9 --- Safety, Approval, and Isolation

-   [ ] Enforce workspace-only filesystem access.
-   [ ] Validate every tool's schema and authorization before execution.
-   [ ] Allowlist test commands and avoid arbitrary shell execution.
-   [ ] Require approval for destructive or sensitive operations.
-   [ ] Apply timeouts, output limits, and resource limits.
-   [ ] Use Docker isolation for generated or untrusted code when
    available.
-   [ ] Never expose secrets to generated code or logs.
-   [ ] Fail closed if safe execution is unavailable.
-   [ ] Log tool actions and approval decisions.

**Exit criteria:** Unsafe actions are blocked or explicitly approved,
and test execution has defined limits.

### Phase 10 --- Integration, Regression, and Documentation

-   [ ] Run backend unit and integration tests.
-   [ ] Run frontend tests and build.
-   [ ] Verify existing chat and streaming still work.
-   [ ] Verify planner routing and state updates.
-   [ ] Verify code changes remain inside the workspace.
-   [ ] Verify actual test results drive reviewer decisions.
-   [ ] Verify the retry limit is enforced.
-   [ ] Verify image, audio, and combined multimodal requests.
-   [ ] Verify missing models, timeouts, invalid files, and disconnected
    clients.
-   [ ] Update README, architecture notes, setup steps, and
    troubleshooting.
-   [ ] Document completed features and known limitations accurately.

## 4. Cross-Cutting Requirements

-   Preserve existing working components and conventions.
-   Inspect before modifying; do not replace code blindly.
-   Keep modules typed, testable, and narrowly scoped.
-   Keep model names, workspace paths, limits, and runtime URLs
    configurable.
-   Use `.env.example`; never commit secrets.
-   Validate model availability and configuration at startup or on
    demand.
-   Do not claim a feature is complete unless it has been tested.
-   Do not send hidden chain-of-thought to the UI or store it as
    user-facing output.
-   Handle errors explicitly and return actionable messages.
-   Do not store binary attachments or large source blobs in graph
    checkpoints.
-   Ask the user for clarification only when required to proceed
    correctly or safely.

## 5. Definition of Done

-   [ ] Existing React chat, FastAPI, Ollama, Qwen3 4B, and streaming
    still work.
-   [ ] LangGraph routes tasks and streams meaningful progress.
-   [ ] Coding tools can safely inspect and modify workspace files.
-   [ ] Testing agent generates test files.
-   [ ] Test runner executes tests and returns real results.
-   [ ] Reviewer uses actual code and test evidence.
-   [ ] Fix/retest loop stops after at most three iterations.
-   [ ] Image input is analyzed locally.
-   [ ] Audio input is transcribed locally.
-   [ ] Conversation persistence and checkpointing work, if implemented.
-   [ ] Sensitive operations are restricted or require approval.
-   [ ] Automated tests pass, and any failures or limitations are
    documented.
-   [ ] README contains reproducible installation and run instructions.

## 6. Execution Instructions for the Coding Agent

1.  Inspect the repository and run the current baseline tests.
2.  Compare the current code against this plan.
3.  Identify the next incomplete phase and its dependencies.
4.  Implement one phase at a time in small changes.
5.  Run relevant tests after each phase and fix regressions before
    continuing.
6.  Update this checklist as work is completed; distinguish implemented,
    tested, and pending items.
7.  Do not rebuild the completed MVP.
8.  Do not stop after producing another plan: implement the next phase.
9.  At each phase boundary, summarize changed files, tests run, results,
    and remaining limitations.
