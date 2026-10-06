# Phase 9: Customer Chatbot, Operation Admin & Slack Notifications

**Goal:** turn the demo into the product shape the client asked for:

1. **Customers** talk to OpsPilot as a **chatbot**. It replies like a person, asks for missing information, and answers with the (R8-checked) reply draft.
2. The agent posts the **full analysis report** to a **Slack channel**, tagging the responsible people, whenever guardrails allow `send_operations_notification`.
3. **Operations admins** review cases and **approve/reject refunds** on a separate **Operation Admin** page; each decision is also posted in the Slack thread.

**Depends on:** Phases 1–8 · **Estimate:** ~2 h · **Skills:** `llm-engineering`, `python-engineering`, `api-design`, `testing`, `logging-observability`

## Decisions (confirmed by the client)

| ID | Decision | Spec impact |
|---|---|---|
| D6 | **The chatbot shows the reply draft to the customer.** It replies conversationally: a clarification question when information is missing, otherwise the LLM draft after the R8 policy check (a violating draft is still replaced by the safe fallback). | **Changes spec Rule 3** ("never send automatically"): the customer now sees the draft. Refund/compensation promises remain impossible (R8). Documented as a deliberate change in spec + README. |
| D7 | **Real Slack notifications** via a Slack bot (`chat.postMessage`), tagging configured people. **Optional**: without Slack config the system falls back to the simulated log, so tests and fresh clones never need Slack. | Extends spec Tool 6 / §27 ("no real Slack"). Documented as an optional integration. |
| D8 | **Approvals move to an Operation Admin page** in Streamlit. Customers never see severity, rules, or approve buttons. Slack only notifies (no buttons, so no Socket Mode / app token). | Refines spec §18 UI. |
| D9 | Slack is notified only when guardrails allow `send_operations_notification` (unchanged rule). | None |

## Slack configuration (`src/.env/.env`)

```text
SLACK_BOT_TOKEN=xoxb-...              # scope chat:write (bot invited to the channel)
SLACK_CHANNEL_ID=C0XXXXXXX
SLACK_MENTION_USER_IDS=U0XXXXXXX,U0YYYYYYY   # people tagged on every report
```

All optional. `Settings.slack_enabled` is true only when the token and channel are set.

## Architecture changes

### New node `notify_operations` (between `execute_actions` and `human_approval`)

```text
validate_input → investigate → guardrails → execute_actions → notify_operations → human_approval → respond
```

Why a new node: the Slack report must contain the **whole** case (executed actions, the reply draft, and the **pending refund approval**). Today the notification runs inside `execute_actions`, before approvals exist. The new node:

1. Creates the approval requests (moved here from `human_approval`; still idempotent per `(request_id, action)`).
2. If guardrails allowed `send_operations_notification`: builds an `OperationsReport` from the state and posts it to Slack. It records the Slack `channel` + `ts` in state, so the decision can be replied in the thread.

`human_approval` then **only** interrupts and processes decisions. Because `notify_operations` completed before the pause, resuming **never re-posts** the Slack message. After a decision, `human_approval` replies in the Slack thread, for example "✅ Refund APR-1002 approved · RFD-0001" or "❌ Refund APR-1002 rejected".

`send_operations_notification` is removed from `execute_actions` (it ran there before) and runs only in `notify_operations`.

### Slack integration (`src/integrations/`, new layer)

| File | Content |
|---|---|
| `src/integrations/slack.py` | `Notifier` protocol: `post(report) -> NotificationResult(delivered, channel, ts, error)` and `reply(channel, ts, text)`. `SlackNotifier` uses the official `slack_sdk.WebClient` (timeout, built-in rate-limit retry). `LogNotifier` prints the `[SIMULATED SLACK]` block when Slack is not configured. `get_notifier()` picks one from settings. |
| `src/integrations/slack_report.py` | Pure function `build_report_blocks(report) -> (blocks, fallback_text)` (Block Kit). |

Failure policy: a Slack error never fails the request. The notification is recorded as `ExecutedAction(success=False, error="SLACK_ERROR: ...")`, logged at WARNING, and the run continues.

Layering: `tools` → `integrations` → `config`, `common`, `utils`. `integrations` never imports `agents`, `guardrails`, or `llm`.

### Report content (Block Kit), matching the client's sample

```text
🔴 CRITICAL · Refund request · ORD-1015
<@U0XXX> <@U0YYY> please review

Order: ORD-1015      Customer: CUS-111 (Emma Schmidt)      Severity reasons: high_value_refund

Issue summary
Order ORD-1015 is delayed by 18 days and has not been delivered yet. The customer requested a refund.

Evidence (from operational data)
• Order status is delayed.
• Expected delivery date 2026-09-22 has passed; 18 days late.

Recommended actions & guardrail decisions
• create_support_ticket: ✅ automatic (high_value_order)
• send_operations_notification: ✅ automatic
• issue_refund: ⏸️ human approval (refund_requires_approval)

Executed actions
• create_support_ticket → TCK-2011 · prepare_customer_response → DRF-0005

Human approval
⏸️ APR-1002 · issue_refund · 1200.00 USD: waiting for a decision in Operation Admin

Customer response (shown to the customer)
> Hi Emma, … your refund request is being reviewed …

request_id: req-75f00288
```

Severity emoji: 🟢 LOW, 🟡 MEDIUM, 🟠 HIGH, 🔴 CRITICAL. Long text is truncated to Slack's block limits.

### New/changed schemas (`src/common/schemas/`)

- `OperationsReport`: the report payload (severity, reasons, intent, order/customer + customer name, summary, evidence, decisions, executed actions, approvals, customer response, request_id, mentions).
- `NotificationResult`: `delivered`, `simulated`, `channel`, `ts`, `error`.
- `CaseRecord`: `request_id`, `created_at`, the latest `AnalyzeResponse`, and the Slack thread (`channel`, `ts`), for the admin page.

### Case store (`src/repositories/case_store.py`)

In-memory store of `CaseRecord`s (locked, reset with the demo). The service saves/updates the case after every `run_agent` / `resume_agent`. The admin page reads from it; Streamlit sessions share the process, so a customer tab and an admin tab see the same cases.

## UI changes (`src/web/`)

Streamlit multipage app via `st.navigation`:

| Page | File | Audience | Content |
|---|---|---|---|
| **Chat** | `src/web/pages/chat.py` | Customer | `st.chat_input` + `st.chat_message` history. Bot replies: the clarification question (`needs_more_info`), the not-found / error message, or the customer reply draft (`completed` / `awaiting_approval`). No severity, rules, or approve buttons. History is sent while a clarification is open, then a new case starts. Sidebar: demo scenario shortcuts + "New conversation". |
| **Operation Admin** | `src/web/pages/admin.py` | Ops admin | Cases list (pending approvals first, then recent cases). Each case shows the full report (today's result view: severity, evidence, decision table, executed actions, draft) plus **Approve / Reject** for pending refunds → `resume_agent`. Also a "Reset demo data" button. |

`src/web/app.py` becomes the entry point that registers both pages (run command unchanged).

## Service changes

- `run_agent` / `resume_agent` save the result in the case store.
- `pending_cases()` / `recent_cases()` helpers for the admin page (a thin read over the case store).

## Tests

| Test file | Covers |
|---|---|
| `test/test_slack_report.py` | Block content per section; severity emoji; mentions rendered as `<@U…>`; truncation of long text; pending vs decided approval wording |
| `test/test_notifier.py` | `SlackNotifier` with a fake `WebClient` (no network): correct channel/blocks; Slack API error → `delivered=False` with the error code; `LogNotifier` when unconfigured; `get_notifier()` selection |
| `test/test_agent.py` (extended) | The report is posted **once** even across pause/resume. The approval decision is replied in the thread. A Slack failure does not fail the run. No post when guardrails block the notification (e.g. not found / missing info). The report contains the pending approval. |
| `test/test_web.py` (rewritten) | Chat page: send message, clarification round-trip, the draft shown as the bot reply, no internal details rendered. Admin page: a pending case is listed, Approve → `resume_agent` called and the decision shown. |
| `test/test_settings.py` | Slack settings parsing (comma-separated mentions, `slack_enabled`) |

All offline: tests run with Slack unconfigured, or with a fake notifier injected.

## Tasks

- [ ] `uv add slack-sdk`; Slack fields in `Settings` and `.env.example`.
- [ ] `src/integrations/` (notifier + report builder) + schemas.
- [ ] Graph: `notify_operations` node; move approval creation there; thread reply on decision; remove the notification from `execute_actions`.
- [ ] Case store + service hooks.
- [ ] Streamlit multipage: Chat + Operation Admin.
- [ ] Tests above; full suite, ruff, mypy.
- [ ] Spec: Rule 3 change (D6), Tool 6 / §27 Slack (D7), §18 UI (D8), §19 tree, layering table. README: decisions, how to run (Slack config), demo flow, limitations. CLAUDE.md + skills.
- [ ] **Manual verification with the real Slack workspace:**
  - S2 → a report with mentions appears in the channel;
  - approve in Admin → a thread reply appears;
  - S3/S6 reports;
  - S4/S5 → no Slack message.

## Implementation notes

- `NotificationResult` lives in its own module (`common/schemas/delivery.py`) to avoid an import cycle: `response` ↔ `notifications`.
- The notifier is a process-wide holder (`get_notifier()` / `set_notifier()`), built lazily from settings; tests reset it in `conftest.py` and inject `FakeNotifier`.
- `send_operations_notification(report)` records every attempt in the action store (including failures, for the audit trail); a Slack failure returns `NOTIFICATION_FAILED`.
- Slack text from customers/LLM is escaped (`& < >`), so it cannot inject `<!channel>` or links; long text is truncated to Block Kit limits.
- Chat replies go through `components.as_markdown`, because Streamlit renders `$…$` as LaTeX (e.g. `$249.99`).
- **Real verification** (real `gpt-4.1-mini` + the client's Slack workspace, driven via AppTest):
  - Chat S2 and S3 posted tagged reports (`ts` returned); S4 and S5 posted nothing.
  - Operation Admin showed 1 pending case; Approve → `issue_refund:RFD-0001`, case completed, thread reply posted.
  - One S3 run returned a non-compliant draft that R8 replaced with the fallback; 3/3 re-runs were compliant (LLM nondeterminism, caught by design).
- Tests: 226 offline (report rendering, notifier with a fake WebClient, post-once across resume, thread replies, Slack failure tolerance, no post on stop rules, case store, Chat + Admin AppTest flows).

## Out of scope

Slack interactive buttons (Socket Mode), a customer authentication flow, persisting cases across restarts.
