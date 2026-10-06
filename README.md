# OpsPilot: AI Operations Automation Agent

OpsPilot helps a customer-support / operations team handle incoming requests for a (fictional) direct-to-consumer e-commerce company. It reads a customer message, investigates internal operational data with tools, explains the issue with evidence, runs safe internal actions automatically, and **stops for a human** before anything risky. Every refund waits for approval, and nothing is ever sent to a customer.

> **The core idea:** the LLM *investigates and recommends*; deterministic code *decides*; a human *approves* money.

---

## 1. Problem

Support agents triage every request by hand: they read the message, open several systems (orders, customers, tickets, subscriptions), judge how serious it is, check for an existing ticket, decide what to do, and write a reply. This is slow and inconsistent.

Handing the work to an AI agent naively is dangerous. An LLM can:

- **invent data**, for example describe an order that does not exist;
- **take a financial action on its own**, such as issuing a refund;
- **say the wrong thing to a customer**, such as promising a refund nobody approved.

## 2. Solution

OpsPilot splits the work by what each part is good at:

| Step | Who | What |
|---|---|---|
| Understand + investigate | **LLM** (OpenAI via LangChain `create_agent`) | Classifies the request, calls **read-only** tools, writes a summary, evidence, recommended actions, and a reply draft |
| Decide | **Deterministic rules** (`src/guardrails`) | Re-read the data and compute severity. For every recommended action they decide **automatic / human approval / blocked**. |
| Act | **Workflow code** | Runs only the actions the rules allowed (simulated ticket, Slack alert, draft) |
| Approve | **Human** | Approves or rejects refunds; the workflow pauses until they decide |

If information is missing, OpsPilot asks for it. If a record does not exist, it says so. If the LLM output is invalid, nothing happens. *When uncertain, do less rather than more.*

## 3. Architecture

```text
                        ┌──────────────────────┐
                        │   Customer request   │  Streamlit UI · REST API
                        └──────────┬───────────┘
                                   ▼
                        ┌──────────────────────┐
                        │    validate_input    │  deterministic: length, ID extraction
                        └──────────┬───────────┘
                                   ▼
 ┌─────────────────────────────────────────────────────────────────────┐
 │ investigate: LangChain create_agent (the ONLY LLM step)             │
 │   tools: get_order · get_customer · get_support_tickets ·           │
 │          get_subscription (read-only)                               │
 │   middleware (guardrail layer 1): VerifiedIdMiddleware (no guessed  │
 │     IDs) · PIIMiddleware (emails redacted) · model/tool call limits │
 │   output: AgentProposal (Pydantic, via ToolStrategy)                │
 └──────────────────────────────────┬──────────────────────────────────┘
                                   ▼
                        ┌──────────────────────┐
                        │      guardrails      │  deterministic (layer 2): re-reads data,
                        │  severity + R1–R8    │  automatic / human_approval / blocked
                        └──────┬───────────┬───┘
               stop rules      │           │ proceed
     (missing info, not found, │           ▼
      unverified ID)           │  ┌──────────────────────┐
                               │  │   execute_actions    │  ticket · ops alert · reply draft (R8-checked)
                               │  └──────────┬───────────┘
                               │             ▼
                               │  ┌──────────────────────┐
                               │  │    human_approval    │  interrupt(): pauses for refunds,
                               │  └──────────┬───────────┘  resumes on Approve / Reject
                               ▼             ▼
                        ┌──────────────────────┐
                        │       respond        │  structured AnalyzeResponse
                        └──────────────────────┘
```

The outer pipeline is an explicit LangGraph `StateGraph`. Pausing for approval uses LangGraph `interrupt()` with a checkpointer; `Command(resume=...)` continues the run after the decision. Every run is traced in **LangSmith** (`run_name="opspilot"`, metadata `request_id` + `prompt_versions`), and every decision is logged as a `key=value` event.

### Where things live

| Path | Responsibility |
|---|---|
| `src/agents/` | `graph.py` (pipeline), `nodes.py` (node logic), `investigator.py` (`create_agent`), `service.py` (`run_agent` / `resume_agent`), `responder.py` |
| `src/guardrails/` | `rules.py` (R1–R7), `severity.py`, `draft_policy.py` (R8): **pure functions, no LLM**. `middleware.py`: investigation-time guardrails |
| `src/tools/` | LangChain `@tool`s: 4 read tools for the LLM; action tools called only by workflow nodes |
| `src/prompts/` | Versioned Markdown prompts (`ops_agent_system.md`, `customer_response_example.md`) + loader |
| `src/common/schemas/` | Pydantic models and enums shared across layers (`AgentProposal`, `GuardrailDecision`, `AnalyzeResponse`, …) |
| `src/repositories/` | Read-only JSON data store + in-memory action store (created tickets, approvals, refunds) |
| `src/memory/` | LangGraph checkpointer (agent memory for pause/resume) |
| `src/web/`, `src/api/` | Streamlit demo UI and FastAPI endpoint: thin adapters over `service.py` |
| `data/` | Fictional sample data: 15 orders, 12 customers, 8 tickets, 10 subscriptions |
| `specs/`, `plans/` | Specification and the phase-by-phase implementation plan |

## 4. Key Design Decisions

**LLM reasoning is separated from deterministic rules.** Only the `investigate` node calls the LLM. Severity, approval, duplicate detection, and execution are pure functions in `src/guardrails/`, with their own tests and their own span in LangSmith. `AgentProposal` deliberately has **no** severity, risk, or approval fields, so the model cannot even express such a decision. A test parses imports with `ast` to guarantee `src/guardrails` never imports LangChain models or `src.llm`.

**The LLM can only read.** `create_agent` gets the 4 read tools only. Ticket creation, notifications, approvals, and refunds are called by workflow nodes, and only for actions the guardrails allowed. Malformed LLM output yields no proposal, and the run ends with a safe error and no action.

**Guardrails run in two layers** (spec §12.7):

1. *Inside the agent loop*, LangChain middleware: `VerifiedIdMiddleware` stops a tool call for any ID the customer never wrote (and no tool returned), so a guessed order is never fetched. `PIIMiddleware` keeps customer emails away from the model. Call limits bound the loop.
2. *After the investigation*, the `guardrails` node re-reads the facts from the data (never the LLM's narrative) and applies the business rules:

| Rule | Effect |
|---|---|
| R1 `refund_requires_approval` | Every refund waits for a human, any amount |
| R2 `high_value_order` (≥ $500) | Escalates ticket priority / alert to `critical` and severity to CRITICAL |
| R3 `external_communication_blocked` | OpsPilot has no way to message customers; it only drafts |
| R4 `duplicate_ticket` | An open/in-progress ticket for the same issue blocks a new one |
| R5 `missing_information` | No order/customer ID: ask (the LLM writes the question); every action blocked |
| R6 `order_not_found` | Unknown ID: say so; every action blocked |
| R7 `unverified_id` | The proposal names an ID nobody wrote: treated as a hallucination, every action blocked |
| R8 `customer_draft_policy` | A reply draft promising a refund/compensation or leaking internal details is replaced by a safe fallback |

Business rules are deliberately **not** middleware: the LLM never calls action tools, so there is nothing to intercept, and `HumanInTheLoopMiddleware` cannot express data-dependent rules such as "orders of $500 or more".

**Human approval via `interrupt()`.** The `human_approval` node creates an idempotent approval request and pauses the graph. The run resumes with the reviewer's decision; a missing decision counts as a rejection. `issue_refund` itself refuses unless the approval is approved, as defense in depth.

**Prompts are versioned Markdown.** Every instruction lives in `src/prompts/*.md` with YAML frontmatter. The customer-reply example is a separate file injected into the system prompt, so the reply style can change without touching agent instructions. Prompt versions are attached to every LangSmith trace.

**Tools never fabricate data.** Tools return structured results (`{"success": false, "error": "ORDER_NOT_FOUND", ...}`), and the prompt forbids stating facts that are not in tool results. Delays are computed from the data (`days_late`), not from the customer's claim.

**No external communication without a human.** The system produces a reply *draft*, labelled "not sent", and has no capability to send it.

### Decisions on points the spec left open

| ID | Decision |
|---|---|
| D1 | Scenario 3 uses ORD-1008 (open ticket TCK-2001), so it does not conflict with Scenario 2's ORD-1007. A fixed `REFERENCE_DATE=2026-10-10` makes delays deterministic (ORD-1007 is exactly 15 days late). |
| D2 | **Only refunds need approval.** Rule 2 (orders of $500 or more) escalates priority and severity instead of adding approvals; internal actions stay automatic so the team is alerted at once. Customer messaging does not exist. |
| D3 | Severity is a deterministic table; when several conditions match, the highest wins. Severity drives display and priority, not approval. |
| D4 | The LLM writes the reply draft from an example template (`customer_response_example.md`); deterministic policy R8 checks it before use. |
| D5 | A request without an ID still reaches the LLM, which asks for the missing information in its own words; code guarantees no tool or action runs. Follow-up replies are sent with the earlier messages as `history`. |

Also: the spec suggests logging `user_input`. OpsPilot logs the message **length** and the IDs instead of the raw text, to keep customer text and PII out of application logs. The full text is visible in LangSmith when debugging.

## 5. How to Run

Requirements: [uv](https://docs.astral.sh/uv/) (it installs Python 3.14 from `.python-version`), an OpenAI API key, and optionally a LangSmith API key.

```bash
uv sync
cp src/.env/.env.example src/.env/.env      # then set OPENAI_API_KEY, OPENAI_MODEL (e.g. gpt-4.1-mini), LANGSMITH_*

uv run python -m streamlit run src/web/app.py     # demo UI → http://localhost:8501
uv run uvicorn src.main:app --reload              # REST API → http://localhost:8000/docs
uv run pytest                                     # tests (offline: no OpenAI or LangSmith calls)
```

Run commands from the repository root. Use `python -m streamlit`, which puts the repo root on `sys.path` so that `import src…` works. `src/.env` is a directory; the real secrets file `src/.env/.env` is gitignored.

API example:

```bash
curl -X POST localhost:8000/api/v1/agent/analyze -H 'Content-Type: application/json' \
  -d '{"message": "Please check order ORD-9999."}'
# → {"status": "not_found", "message": "I couldn't find order ORD-9999 in the available operations data.", ...}
```

Quality checks: `uv run ruff format --check . && uv run ruff check . && uv run mypy && uv run pytest`.

## 6. Demo Examples

Use the sidebar buttons in the Streamlit UI. "Today" is fixed at 2026-10-10.

| # | Input | Expected outcome |
|---|---|---|
| 1 | My order ORD-1001 is two days late. Can you check what is happening? | `completed`, **MEDIUM**: ticket + ops alert + draft run automatically; no high-risk action |
| 2 | My order ORD-1007 is 15 days late. I want a refund. | `awaiting_approval`, **HIGH**: ticket, alert, and draft run; **refund waits for Approve/Reject** |
| 3 | Please help with my delayed order ORD-1008. | Ticket **blocked**: "An existing support ticket already exists. Ticket: TCK-2001, Status: open"; ops follow-up alert sent |
| 4 | Please check order ORD-9999. | `not_found`, no invented data, no actions |
| 5 | My order hasn't arrived and I want a refund. | `needs_more_info`: the agent asks for the order ID; no tool or action runs |
| 5b | Reply "It's ORD-1007." to Scenario 5 | Continues with full context → refund waits for approval |
| 6 | My order ORD-1015 is delayed. Please refund the order. | `awaiting_approval`, **CRITICAL** ($1,200): refund needs approval; ticket/alert get `critical` priority |

All of these were verified end to end with `gpt-4.1-mini`, including Approve → simulated refund executed.

## 7. Known Limitations

- Sample data is local JSON; there is no database.
- All actions are simulated: no real ticketing system, Slack, or payment provider.
- Human approval is simulated in the demo UI. Approvals and paused runs live in memory (`InMemorySaver`, in-memory action store) and are lost on restart; the action store is shared by all browser sessions.
- No authentication or authorization; anyone with the UI can approve a refund.
- The evaluation set is small: scripted offline tests plus manual real-model runs of the demo scenarios. There is no automated LLM eval suite.
- LLM behaviour is non-deterministic. Guardrails make outcomes safe, but recommendations can vary between runs (e.g. a reply draft may fall back to the safe template).
- LangSmith traces contain the customer's message text, acceptable only because all demo data is fictional.
- Duplicate detection matches tickets by order **and** issue type, so it depends on the LLM classifying the issue type consistently.

## 8. Production Improvements

| Area | Change |
|---|---|
| Persistence | Real database for operational data; **durable checkpointer** (e.g. LangGraph Postgres saver) so paused approvals survive restarts |
| Integrations | Real ticketing (e.g. Zendesk/Jira) and Slack clients behind the same tool interfaces; payment-provider refunds with **idempotency keys** |
| Security | Authentication, **RBAC** (who may approve which refunds, approval limits), secrets in a secret manager |
| Approval workflow | Persistent approval queue with assignees, SLAs, an audit trail, and an approval API (not only the UI) |
| Audit & compliance | Immutable audit log of every guardrail decision, executed action, and approval, keyed by `request_id`; **PII redaction** in logs and traces |
| Reliability | Retry policies with backoff around integrations, **model fallback** (secondary model or provider), rate limiting, timeouts per dependency |
| Quality | LangSmith datasets + evaluators run on every prompt/model change (regression gate); online evaluation of production traces |
| Observability | Metrics and alerting (approval latency, block rates, LLM error rates) on top of LangSmith traces and structured logs |
| Prompt management | Prompt versions promoted through environments, with an A/B or canary rollout |
| Architecture | Event-driven intake (queue per channel) so requests are processed asynchronously and idempotently |

---

**Tech stack:** Python 3.14 · uv · LangChain v1 (`create_agent`, middleware) · LangGraph (`StateGraph`, `interrupt`) · OpenAI · LangSmith · Pydantic v2 · Streamlit · FastAPI · pytest · ruff · mypy (strict).
