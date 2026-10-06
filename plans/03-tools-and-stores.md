# Phase 3 — Tools & Stores

**Goal:** deterministic data access and simulated actions as LangChain `@tool` functions, backed by a read-only data store and an in-memory action store.

**Depends on:** Phase 2 · **Estimate:** 30 min · **Skills:** `llm-engineering` (Tools section), `python-engineering`, `testing`

## Deliverables

| File | Content |
|---|---|
| `src/utils/ids.py` | `ORDER_ID_RE`, `CUSTOMER_ID_RE`, `is_entity_id(s)`, `extract_ids(text) -> ExtractedIds(order_ids, customer_ids, all)`, `verified_ids_from(messages) -> set[str]` (IDs in human + tool messages). This is the single ID definition, shared with `validate_input` (Phase 6) and `VerifiedIdMiddleware` (Phase 5). |
| `src/repositories/data_store.py` | `DataStore`: loads `data/*.json` once and validates it into `common/schemas/domain.py` models; lookup by ID |
| `src/repositories/action_store.py` | `ActionStore`: created tickets, notifications, approvals, executed actions; `next_id()`; `reset()` |
| `src/tools/orders.py` | `get_order` |
| `src/tools/customers.py` | `get_customer` |
| `src/tools/subscriptions.py` | `get_subscription` |
| `src/tools/tickets.py` | `get_support_tickets`, `create_support_ticket` |
| `src/tools/actions.py` | `send_operations_notification`, `prepare_customer_response`, `request_human_approval`, plus approval-only `issue_refund` |
| `src/tools/registry.py` | `READ_TOOLS`, `ACTION_TOOLS`, `APPROVAL_ONLY_ACTIONS` |
| `test/test_tools.py` | Tool tests (spec Tests 1–2) |

## Design

**Stores** (`src/repositories/`; `src/memory/` is reserved for agent memory, the checkpointer in Phase 6)
- `get_data_store()` and `get_action_store()` are cached module-level singletons. `ActionStore.reset()` exists for tests (autouse fixture) and runs on app start.
- `next_id(prefix)` continues above the highest existing ID across sample data and created records (`TCK-2042`, `APR-1001`, `NTF-0001`). It never collides with sample data.
- `get_support_tickets` returns sample tickets **plus** tickets created in this process. Without that, duplicate detection would miss tickets the agent just created.

**Tool return contract.** Every tool returns a dict:
- `{"success": true, ...data}`, or
- `{"success": false, "error": "<CODE>", "message": "<human text>"}`

Error codes: `ORDER_NOT_FOUND`, `CUSTOMER_NOT_FOUND`, `SUBSCRIPTION_NOT_FOUND`, `INVALID_ID_FORMAT`. Expected failures never raise.

**ID validation:** `ORD-\d{4}`, `CUS-\d{3}`, defined only in `src/utils/ids.py`. A malformed ID returns `INVALID_ID_FORMAT` without a lookup.

**Read tools** (given to the LLM): `get_order(order_id)`, `get_customer(customer_id)`, `get_support_tickets(customer_id, order_id=None)`, `get_subscription(customer_id)`.
- `get_order` also returns derived facts: `days_late`, computed from `today(settings)`. The LLM then never has to do date math.
- Docstrings say what the tool does, when to use it, and what it returns (the model reads them).

**Action tools** (graph nodes only, never given to the LLM):
- `create_support_ticket(customer_id, order_id, issue_type, priority, summary)` → `{"success": true, "ticket_id": "TCK-…"}`. The tool does *not* check duplicates; that is guardrail Rule 4 (Phase 4), which keeps a single source of truth.
- `send_operations_notification(severity, summary, order_id, recommended_action)` logs the `[SIMULATED SLACK]` block from spec Tool 6 and stores it.
- `prepare_customer_response(customer_name, issue_summary, recommended_action, draft)` (decision D4):
  - It does **not** generate text. The LLM wrote `draft` from the example template.
  - It does **not** check policy either. The `execute_actions` node runs `check_customer_draft` (Phase 4) first and passes the final text, so `tools` never imports `guardrails`.
  - It stores the draft and returns `{"success": true, "draft_id": "DRF-…", "draft": "..."}`.
  - It also exposes `fallback_customer_draft(customer_name, issue_summary)`, a short deterministic text used when the LLM's draft is missing or violates policy: "Hi {name}, thank you for contacting us about {issue}. Our team is reviewing your request and will get back to you shortly."
- `request_human_approval(action, reason, context)` → `{"approval_id": "APR-…", "status": "pending", ...}`. It is **idempotent** per `(request_id, action)` (Phase 6 resumes re-run nodes).
- `issue_refund(order_id, amount)` is simulated, logs `[SIMULATED REFUND]`, and is callable **only** after approval. It is the sole entry in `APPROVAL_ONLY_ACTIONS` (D2), not in `ACTION_TOOLS`.
- There is **no** `send_customer_message` tool. The agent only drafts replies (spec Rule 3), so sending is not something the system can do.

## Tasks

- [ ] Data store with lookups: `order(id)`, `customer(id)`, `tickets(customer_id, order_id)`, `subscription(customer_id)`.
- [ ] Action store with records and `reset()`.
- [ ] Read tools + action tools + registry.
- [ ] Log each call: `log_event("tool_called", tool=..., success=..., error=...)`.
- [ ] `test/conftest.py`: autouse fixture `reset_action_store`.

## Tests (`test/test_tools.py`)

- **Test 1** `test_get_order_returns_existing_order`: the data matches the JSON, and `days_late` is 15 for ORD-1007.
- **Test 2** `test_get_order_returns_not_found_for_unknown_id`: ORD-9999 returns `ORDER_NOT_FOUND`.
- `test_get_order_rejects_malformed_id`: `"ORD-99x"` returns `INVALID_ID_FORMAT`.
- `test_get_support_tickets_includes_created_tickets`
- `test_create_support_ticket_generates_non_colliding_id`
- `test_request_human_approval_is_idempotent`
- `test_prepare_customer_response_stores_draft_unchanged`
- `test_fallback_customer_draft_is_safe`: the fallback mentions neither refund nor compensation.
- `test_registry_separates_read_and_action_tools`: no action tool appears in `READ_TOOLS`.
- `test_extract_ids` (`utils/ids.py`): finds `ORD-1007` / `CUS-102` in free text, ignores `ORD-99x` and `ORD-123456`.

## Acceptance criteria

`uv run pytest test/test_tools.py` passes. Tools are importable without OpenAI configured.

## Out of scope

Deciding *whether* an action may run (Phase 4) and calling tools from the graph (Phase 6).
