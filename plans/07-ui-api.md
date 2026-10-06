# Phase 7 — Streamlit UI & REST API

**Goal:** two thin adapters over `src/agents/service.py`. Streamlit is the demo surface (with Approve/Reject); FastAPI lets a reviewer `curl` the agent.

**Depends on:** Phase 6 · **Estimate:** 30 min · **Skills:** `api-design`, `python-engineering`

## Deliverables

| File | Content |
|---|---|
| `src/web/app.py` | Streamlit page |
| `src/api/schemas.py` | `AnalyzeRequest` only (`AnalyzeResponse` is imported from `src/common/schemas`) |
| `src/api/routes.py` | `POST /api/v1/agent/analyze` |
| `src/main.py` | `create_app()`: router, `/healthz`, exception handler (safe error envelope) |
| `test/test_api.py` | Smoke test with `TestClient` (patched `run_agent`) |

## Streamlit page (`src/web/app.py`)

Use default components only, no styling work (spec §18).

1. **Sidebar:** one button per demo scenario (Phase 2 table) that pre-fills the text area, and a "Reset demo data" button (`action_store.reset()`).
2. **Main:** a text area and an **Analyze** button → `run_agent(message, history=st.session_state.history)`.
   - If the response is `needs_more_info`, show the agent's question (`message`) as a chat bubble and keep the conversation. The next submission sends the reply plus `history` (D5).
   - Any other status ends the exchange and clears `history`.
   - `st.chat_message` is fine for this. No custom styling.
3. **Result:**
   - status badge, severity, issue summary;
   - evidence list;
   - recommended actions table (action, risk, execution, rule, reason), where blocked and approval rows are clearly marked;
   - executed actions;
   - customer response draft labelled "Draft — not sent";
   - `request_id`.
4. **Pending approvals:** one row per approval with **Approve** / **Reject** buttons. When submitted, call `resume_agent(thread_id, decisions)` and re-render the final result.

Implementation notes:
- Wrap `get_graph()` / the checkpointer in `st.cache_resource` so paused runs survive Streamlit reruns.
- Keep `thread_id` and the last response in `st.session_state`.
- Call `configure_logging()` once at the top.
- Run with `uv run python -m streamlit run src/web/app.py` from the repo root.

## REST API

- `POST /api/v1/agent/analyze` with `{"message": "...", "history": ["..."]}` (`history` optional, for clarification follow-ups) → `AnalyzeResponse` (200 for all business outcomes, including `awaiting_approval`, `not_found`, `needs_more_info`, `error`).
- `GET /healthz` → `{"status": "ok"}`.
- `422` on an invalid body. `500` returns the safe envelope `{"error": {"code", "message", "request_id"}}`.
- Routes are sync (`def`). No resume endpoint: approvals happen in Streamlit (spec §18.2).

## Tests

- `test_analyze_returns_response_shape` (patched `run_agent`)
- `test_analyze_rejects_empty_message` → 422
- `test_analyze_passes_history_to_service` (patched `run_agent` receives `history`)
- `test_unexpected_error_returns_safe_envelope` → 500, no stack trace in the body
- `test_healthz`

Streamlit is verified manually (below), not with automated tests.

## Acceptance criteria

- Manual run in Streamlit, with a real key, of all scenarios:
  - Scenario 2 shows a pending refund; Approve leads to `issue_refund` executed, and Reject leads to it not executed.
  - Scenario 3 shows the blocked duplicate ticket.
  - Scenarios 4 and 5 show no actions.
- `curl -X POST localhost:8000/api/v1/agent/analyze -H 'Content-Type: application/json' -d '{"message":"Please check order ORD-9999."}'` returns `status: "not_found"`.
- `/docs` renders cleanly.

## Out of scope

Visual polish, auth, an approval API endpoint.
