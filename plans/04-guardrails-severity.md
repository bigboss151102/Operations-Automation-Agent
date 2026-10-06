# Phase 4 — Guardrails & Severity

**Goal:** every business decision (severity, per-action execution mode, duplicates, invalid or unverified IDs) is made by **pure, deterministic functions** with full test coverage. This is the core of spec §11–§13 (Guardrails = 20% and Architecture = 25% of the grade).

**Depends on:** Phase 3 (models/enums; no LLM) · **Estimate:** 35 min · **Skills:** `python-engineering`, `testing`, `logging-observability`

## Deliverables

| File | Content |
|---|---|
| `src/common/schemas/decisions.py` | `Facts`, `GuardrailDecision`, `SeverityResult` (shared: guardrails produce them, agents/response consume them) |
| `src/common/schemas/enums.py` | + `Severity`, `Execution`, `ActionName`, `RuleId` |
| `src/guardrails/severity.py` | `classify_severity(facts) -> SeverityResult` |
| `src/guardrails/rules.py` | `evaluate(proposal, facts, *, high_value_threshold) -> GuardrailResult` |
| `src/guardrails/draft_policy.py` | `check_customer_draft(text) -> list[PolicyViolation]` (R8, decision D4) |
| `test/test_guardrails.py` | Spec Tests 4, 5, 6 + severity + ID checks |
| *(added during implementation)* `src/common/schemas/proposal.py` | `AgentProposal` / `ProposedAction`, moved up from Phase 5 because guardrails consume it |
| *(added)* enums | `Intent`, `ORDER_INTENTS`, `RequestedAction`, `ActionName`, `Risk`, `Execution` (`automatic` / `human_approval` / `blocked`, matching spec §14), `RuleId`, `GuardrailOutcome` |

Implementation notes:
- Stop-rule precedence is **R7 → R5 → R6**. A proposal that names an ID nobody wrote is treated as a hallucination even when information is also missing.
- `GuardrailResult.priority` is the ticket priority / notification level for the case: severity mapped to priority, or `critical` for high-value orders (R2).

## Inputs

**`Facts`** are re-read from the data store by the `guardrails` node (Phase 6). They are **never** taken from the LLM's narrative:
- `order` (or None)
- `customer`
- open tickets for the order
- `days_late`
- `extracted_ids` (from the regex in `validate_input`)

**From the LLM proposal**, guardrails use only the classification (`intent`, `issue_type`, `requested_action`) and `proposed_actions` (names + reasons).

## Action catalogue (decision D2: only refunds need human approval)

| Action | Base risk | Execution (any order value) | Order of $500 or more (Rule 2) |
|---|---|---|---|
| `prepare_customer_response` | none | auto (draft only, never sent) | auto |
| `send_operations_notification` | low | auto (internal) | auto, `severity`/priority `critical` |
| `create_support_ticket` | low | auto, unless a duplicate exists → **blocked** (Rule 4) | auto, ticket priority `critical` |
| `issue_refund` | high | **human_approval** (Rule 1, any amount) | **human_approval** |

- **Refund is the only action that ever needs approval.**
- **`send_customer_message` is not in the catalogue.** The agent can only *draft* replies, never send them. If the LLM proposes it anyway → **blocked** (`external_communication_blocked`, Rule 3).
- Any other action name outside this catalogue → **blocked** (`unknown_action`).

## Rules (rule IDs appear in logs and in the response)

| Rule ID | Condition | Effect |
|---|---|---|
| `refund_requires_approval` (R1) | action = `issue_refund` | execution = human_approval |
| `high_value_order` (R2) | `order.total_amount >= threshold` | **No extra approval** (D2). Escalates handling: ticket priority and notification severity = `critical`, and feeds the CRITICAL severity rows below. A refund on such an order still goes to approval via R1 |
| `external_communication_blocked` (R3) | action = `send_customer_message` | execution = blocked (the agent only drafts; a human sends) |
| `duplicate_ticket` (R4) | action = `create_support_ticket` and an open/in_progress ticket exists for the same order **and** same issue type | execution = blocked; report existing ticket ID + status |
| `missing_information` (R5) | `proposal.missing_fields` is non-empty, **or** the intent needs an order (`delivery_issue`, `refund_request`, `order_status`) and there is no verified `order_id`, **or** a subscription issue has no verified `customer_id` | status = needs_more_info; **all** actions blocked; the response message is the LLM's `clarification_question` (fallback: the spec's fixed text) |
| `order_not_found` (R6) | proposal references an order that is not in the data | status = not_found; **all** actions blocked |
| `unverified_id` (R7) | proposal's `order_id`/`customer_id` is not among the IDs the customer wrote or that tool results returned | status = error; all actions blocked (anti-hallucination). **Layer 2** of R7. Layer 1 is `VerifiedIdMiddleware` (Phase 5), which blocks the lookup itself |
| `customer_draft_policy` (R8) | The LLM's `customer_response_draft` contains a refund/compensation promise (e.g. "we have refunded", "you will receive a refund", "refund has been processed", "we will compensate"), or internal details (severity words, rule IDs, "priority", "guardrail", `APR-`/`TCK-` internal IDs other than the customer's own order ID), or it is empty | The draft is replaced by `fallback_customer_draft(...)`; the violation is logged and listed in the response. Other actions are unaffected |

Precedence: R5/R6/R7 (stop everything) → R3/R4 (block) → R1 (approval) → auto. R2 never changes execution, only priority/severity. A decision carries **every** rule that matched, and the strictest effect wins.

## Severity (decision D3 — confirmed)

Compute every rule below, then take the **maximum**. Severity does **not** decide approval (only R1 does). It drives the displayed severity, the notification severity, and the ticket priority.

| Severity | Condition (deterministic) |
|---|---|
| LOW | Informational request (`intent = order_status`) on an order that is not late |
| MEDIUM | `days_late` 1–7; or subscription / address / cancelled-order issue |
| HIGH | Refund requested; or `days_late > 7`; or `issue_type = missing_order` |
| CRITICAL | Refund requested on an order of $500 or more; or ≥ 2 open `refund_request` tickets for the same order; or `issue_type = missing_order` on an order of $500 or more |

The result includes the matched rule names. `not_found` / `needs_more_info` / `error` results have severity `None`.

## Tasks

- [ ] Schemas in `common/schemas/decisions.py` + enums (Pydantic, `StrEnum`). `src/guardrails/` contains only logic.
- [ ] `classify_severity` and `evaluate` as pure functions. They take the threshold as an argument and do no I/O.
- [ ] Decorate `evaluate` with `@traceable(name="guardrails.evaluate")` (LangSmith; a no-op when tracing is off).
- [ ] Factory helpers in tests: `make_order(**overrides)`, `make_proposal(**overrides)`, `make_ticket(**overrides)`.

## Tests (`test/test_guardrails.py`)

- **Test 4** `test_refund_requires_approval`: parametrized over amounts 20, 49.99, 50, 249.99.
- **Test 5** `test_high_value_order_requires_approval`: parametrized at 499.99 / 500 / 500.01.
  - A refund on a high-value order → `human_approval` and severity CRITICAL.
  - Ticket and notification stay auto, but get `critical` priority/severity at ≥ 500 and not below.
- **Test 6** `test_duplicate_ticket_is_blocked`: reports TCK id + status. Plus: a closed ticket does not block, and a different issue type does not block.
- `test_only_refund_requires_approval`: across every catalogue action, only `issue_refund` gets `human_approval`.
- `test_send_customer_message_is_blocked` (R3)
- `test_unknown_action_is_blocked`
- `test_order_not_found_blocks_all_actions`
- `test_customer_draft_policy`: parametrized.
  - Safe: "Our team is reviewing your refund request" → no violations.
  - Violations: "We have refunded your order", "You will receive a full refund", "This was classified as HIGH severity", "Ticket TCK-2042 has high priority", and an empty draft.
- `test_missing_information_blocks_all_actions`: parametrized over (a) `missing_fields=["order_id"]`, (b) a refund intent with no verified order, even when the LLM proposed `issue_refund` and `create_support_ticket`, and (c) a subscription issue with no customer ID. Each gives `needs_more_info` and every action blocked.
- `test_unverified_order_id_blocks_all_actions`: proposal says ORD-1007, but the message had no such ID.
- `test_severity_table`: one parametrized case per row above, plus "highest wins" when several match.

## Acceptance criteria

- `uv run pytest test/test_guardrails.py` passes.
- `src/guardrails/rules.py` and `severity.py` import nothing from `langchain` or `src.llm`. `middleware.py` (Phase 5) may import only `langchain.agents.middleware`. Enforce this with `test_guardrails_have_no_llm_imports`, which parses the imports with `ast`.

## Placement note

Business rules live here as pure functions, **not** as LangChain middleware (spec §12.7):
- the LLM never calls action tools, so there is nothing for middleware to intercept;
- `HumanInTheLoopMiddleware` can't express data-dependent rules (Rule 2);
- severity is computed over the final proposal.

Middleware is used only for investigation-time guardrails (Phase 5).

## Out of scope

Executing actions, approvals flow (Phase 6).
