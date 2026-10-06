# Phase 6 — Graph, Service & Human Approval

**Goal:** wire the full pipeline (spec §9.2) as an outer LangGraph `StateGraph`, expose it through `run_agent()` / `resume_agent()`, and implement human-in-the-loop with `interrupt()`.

**Depends on:** Phases 4 and 5 · **Estimate:** 40 min · **Skills:** `llm-engineering`, `api-design` (response contract), `logging-observability`, `testing`

## Deliverables

| File | Content |
|---|---|
| `src/agents/state.py` | `OpsState` (TypedDict) |
| `src/agents/nodes.py` | `validate_input`, `investigate`, `guardrails`, `execute_actions`, `human_approval`, `respond` + routers |
| `src/agents/graph.py` | `build_graph(model, checkpointer, **limits)` |
| `src/memory/checkpointer.py` | `get_checkpointer()` → singleton `InMemorySaver` (agent memory) |
| `src/common/schemas/response.py` | `AnalyzeResponse`, `RecommendedAction`, `ExecutedAction`, `ApprovalRequest` (shared with API/UI) |
| `src/agents/service.py` | `run_agent(message) -> AnalyzeResponse`, `resume_agent(thread_id, decisions) -> AnalyzeResponse` |
| `test/test_agent.py` | End-to-end graph tests with `FakeChatModel` |

## Node behaviour

| Node | Does | Routes to |
|---|---|---|
| `validate_input` | Trim the message, enforce 1–2000 chars, extract IDs with `extract_ids()` (`utils/ids.py`) from `history` + `message`. Only empty or too-long input → `respond` (`error`). **Missing IDs do not short-circuit**: the LLM handles them (D5) | `investigate` or `respond` |
| `investigate` | Invoke the investigator with every customer message (history + latest), each wrapped in `<customer_request>`. An invalid/missing proposal sets `error="invalid_llm_output"` | `guardrails` or `respond` |
| `guardrails` | Re-read facts from the repositories, then `classify_severity` + `evaluate` (Phase 4). R5 turns missing information into `needs_more_info` with every action blocked. Rule 7 layer 2 checks the proposal IDs against `verified_ids` (set by `investigate` from human + tool messages). Log each `guardrail_decision` with its rule | `execute_actions` or `respond` (needs_more_info / not_found / unverified ID) |
| `execute_actions` | Run decisions with `execution == "auto"` (ticket, notification, customer response draft). For the draft:<br>1. `check_customer_draft(proposal.customer_response_draft)` (R8).<br>2. If it passes, use the LLM draft; otherwise use `fallback_customer_draft(...)` and log the violation.<br>3. Call `prepare_customer_response(..., draft=final_text)`.<br>Record `executed_actions` | `human_approval` |
| `human_approval` | For `human_approval` decisions: `request_human_approval` (idempotent), then `interrupt({"approvals": [...]})`. Only `issue_refund` can reach this node (D2). On resume: approved → run the simulated `issue_refund`; rejected → record it | `respond` |
| `respond` | Assemble `AnalyzeResponse` (status, severity, evidence, recommended actions with risk/execution/rule, executed actions, approvals, draft, message). For `needs_more_info`, `message` = the LLM's `clarification_question` (fallback: the spec's fixed sentence if the LLM left it empty) | END |

Blocked actions (duplicate ticket) appear in `recommended_actions` with `execution="blocked"` and the reason. Example: "An existing support ticket already exists. Ticket: TCK-2001, Status: open".

## Service (`service.py`)

- `run_agent(message, history: list[str] | None = None)`:
  0. `history` holds the earlier customer messages of a clarification exchange (D5). The service stays **stateless per turn**: the client (Streamlit `session_state`, or the API caller) keeps the history, so there are no conversation-state resets to manage in the checkpointer.
  1. Generate `request_id` (`req-<uuid8>`) and set the logging ContextVar.
  2. Invoke the graph with the config (`thread_id=request_id`, `recursion_limit=25`, `run_name`, `tags`, `metadata={request_id, prompt_versions}`).
  3. If the result has `__interrupt__`, return `status="awaiting_approval"`; otherwise return the `respond` output.
- `resume_agent(thread_id, decisions: dict[approval_id, "approve" | "reject"])` → `Command(resume={"decisions": decisions})` (always wrapped, see notes) → final `AnalyzeResponse`.
- Catch-all: an unexpected exception (OpenAI error, recursion limit) returns `status="error"` with a safe message. No action has run at that point, and the exception is logged with `logger.exception`.
- The compiled graph is built once (`get_graph()` cached). Streamlit additionally wraps it in `st.cache_resource` (Phase 7).

## Tests (`test/test_agent.py`, all with `FakeChatModel`)

- **Test 3** `test_missing_order_id_asks_for_it`: the model returns a proposal with `missing_fields=["order_id"]` + `clarification_question`. Assert `status == "needs_more_info"`, `message` is the LLM's question, no tool executed, and no actions/approvals.
- `test_missing_id_cannot_be_bypassed`: the model first tries `get_order("ORD-1007")` (a guessed ID, not in the message), then proposes `issue_refund` with no `missing_fields`. The spy tool is never called (middleware). The result is still `needs_more_info`/`error` with no actions (guardrails).
- `test_follow_up_with_id_resumes_investigation`: `run_agent("It's ORD-1007.", history=["My order hasn't arrived and I want a refund."])` → refund flow → `awaiting_approval`.
- **Test 6** `test_existing_ticket_prevents_duplicate` (ORD-1008): no new ticket in the action store; TCK-2001 is reported.
- **Test 7** `test_safe_actions_execute_automatically` (ORD-1001): ticket + notification are in `executed_actions` and the action store.
- **Test 8** `test_malformed_llm_output_triggers_no_action`: `status == "error"`; no executed actions; no approvals.
- `test_refund_pauses_for_approval_then_executes_on_approve` (ORD-1007): `awaiting_approval` → resume approve → `issue_refund` executed; the approval was created **once**.
- `test_refund_rejected_is_not_executed`
- `test_llm_customer_draft_is_used_when_compliant`: the scripted draft appears unchanged in `customer_response`.
- `test_llm_customer_draft_promising_refund_is_replaced`: a scripted draft "We have refunded your order" leads to the fallback draft, an R8 violation in the response, and other actions unaffected.
- `test_unknown_order_returns_not_found` (ORD-9999)
- `test_hallucinated_order_id_is_rejected`: the proposal names an ID that is in neither the message nor any tool result. This tests layer 2; layer 1 (middleware) is covered in Phase 5.

## Acceptance criteria

- All of the above pass offline.
- A manual run of `run_agent()` on scenarios 1–5 (+6) with the real model gives the outcomes in the Phase 2 scenario table.

## Out of scope

UI/API (Phase 7).

## Implementation notes

- **Bug fix carried over from Phase 5:** `verified_ids_from` trusted every tool message. A middleware `UNVERIFIED_ID` error quotes the guessed ID, so retrying the same guess **passed** the middleware, and the structured-output `AgentProposal` tool message echoes the model's own IDs. Now error tool messages are never trusted, and the `investigate` node passes `trusted_tools=READ_TOOL_NAMES`. Regression test `test_retrying_a_blocked_id_is_still_blocked` fails on the old code.
- **Resume value is wrapped** as `{"decisions": {...}}`. LangGraph treats a dict whose keys all look like interrupt-ID hashes as a per-interrupt resume map; `{}` qualifies, which left the run paused.
- **Checkpointer serde allowlist** (`make_checkpointer()`): the default `InMemorySaver` logged 13 "Deserializing unregistered type … will be blocked in a future version" warnings per pause/resume; the allowlisted serde logs 0. Tests use the same checkpointer.
- **`responder.build_response`** is shared by the `respond` node and the service while paused (the interrupt payload supplies the pending approvals).
- `AnalyzeResponse` uses `approvals` (pending, approved, or rejected) plus `approval_required`, instead of `pending_approvals`, and adds `thread_id`, `severity_reasons`, and `draft_policy_violations`.
- **Real-model run** (`gpt-4.1-mini`) of `run_agent()` on S1–S6 (+5b, + approve) found two LLM issues:
  1. `AgentProposal.customer_response_draft` was optional and omitted in about half the runs. All proposal fields are now **required**, and the draft was present 6/6.
  2. A "delivered but not received" order (ORD-1009) got no ticket/refund. Prompt v3 treats it as `missing_order` and always proposes `issue_refund` when a refund is asked for.

  Final pass: every scenario returned the expected status; every approval led to `refund=ok`; every draft came from the LLM.
