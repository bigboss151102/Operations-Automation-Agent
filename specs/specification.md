# OpsPilot — AI Operations Automation Agent

## 1. Overview

Build a small working AI agent called **OpsPilot** that helps a customer-support / operations team analyze incoming customer requests, identify operational issues, recommend next actions, and safely execute or simulate operational actions.

This project is an AI Demo Challenge for a Senior AI Developer role.

The primary goal is NOT to build a production-grade application or polished UI.

The primary goal is to demonstrate:

* Practical AI agent architecture
* Tool calling
* Structured reasoning
* Reliable decision making
* Guardrails
* Human-in-the-loop approval
* Safe handling of invalid or incomplete input
* Clear separation between AI reasoning and deterministic business rules
* Good software engineering practices

Expected implementation time: approximately 2–4 hours.

Keep the implementation intentionally small and focused.

---

# 2. Business Scenario

OpsPilot assists a customer-support / operations team for a fictional DTC e-commerce company.

The system receives customer-support requests related to:

* Delayed orders
* Missing orders
* Cancelled orders
* Refund requests
* Subscription problems
* Address issues
* Other operational problems

The agent should investigate the request using internal operational data and determine:

1. What is the customer's issue?
2. How severe is the issue?
3. What evidence supports the conclusion?
4. What should happen next?
5. Can the action be performed automatically?
6. Does the action require human approval?

The system must never invent operational facts that are not present in the provided data.

---

# 3. Core Requirements

The system MUST support the following capabilities.

## 3.1 Analyze Incoming Requests

Accept a natural-language customer-support request.

Example:

> My order ORD-1007 has not arrived yet. It has been 15 days and I would like a refund.

The agent should extract structured information such as:

```json
{
  "intent": "refund_request",
  "order_id": "ORD-1007",
  "customer_id": null,
  "issue_type": "delayed_order",
  "requested_action": "refund"
}
```

The exact schema may be improved if necessary.

---

# 4. Sample Data

Create small local sample datasets.

Use JSON or CSV files.

Do NOT build a real database unless there is a strong reason.

Recommended structure:

```text
data/
├── orders.json
├── customers.json
├── support_tickets.json
└── subscriptions.json
```

The datasets should contain enough cases to demonstrate:

* Normal order
* Delayed order
* Cancelled order
* Delivered order
* Missing order ID
* Invalid order ID
* Refund request
* Subscription issue
* Existing support ticket
* High-value order
* Potential duplicate request

Create approximately 10–20 records per dataset.

The data should be deterministic and easy to understand during the demo.

---

# 5. Example Order Schema

Use a structure similar to:

```json
{
  "order_id": "ORD-1007",
  "customer_id": "CUS-102",
  "status": "delayed",
  "order_date": "2026-09-20",
  "expected_delivery_date": "2026-09-25",
  "actual_delivery_date": null,
  "total_amount": 249.99,
  "currency": "USD"
}
```

Possible order statuses:

* pending
* processing
* shipped
* delivered
* delayed
* cancelled

---

# 6. Example Customer Schema

```json
{
  "customer_id": "CUS-102",
  "name": "Alex Johnson",
  "email": "alex@example.com",
  "subscription_status": "active"
}
```

Do not use real personal data.

All customer information must be fictional.

---

# 7. Example Support Ticket Schema

```json
{
  "ticket_id": "TCK-2001",
  "customer_id": "CUS-107",
  "order_id": "ORD-1008",
  "status": "open",
  "priority": "high",
  "issue_type": "delivery_delay",
  "created_at": "2026-10-05",
  "summary": "Order ORD-1008 past its expected delivery date; carrier investigation requested."
}
```

`order_id` is optional (e.g. subscription tickets). Only `open` and `in_progress` tickets count as existing tickets for duplicate protection (Rule 4).

---

# 8. Example Subscription Schema

```json
{
  "subscription_id": "SUB-301",
  "customer_id": "CUS-102",
  "status": "active",
  "plan": "premium",
  "next_billing_date": "2026-10-15"
}
```

---

# 9. Agent Architecture

Implement a small agent architecture.

Logical flow:

```text
User Request
     │
     ▼
Input Validation
     │
     ▼
Operations Agent
     │
     ├── get_order()
     ├── get_customer()
     ├── get_support_tickets()
     ├── get_subscription()
     │
     ▼
Issue Analysis
     │
     ▼
Risk / Action Classification
     │
     ▼
Guardrail Check
     │
     ├── Safe → Execute / Simulate
     │
     └── Risky → Human Approval
```

## 9.1 Framework

The agent is built with **LangChain v1** and **LangGraph**:

* **`create_agent`** (LangChain v1) runs the LLM investigation: the model/tool loop plus structured output. The model is specified as `"openai:<model>"` via `init_chat_model`.
* An explicit **LangGraph `StateGraph`** wraps it in a deterministic pipeline: validation, guardrails, execution, and human approval.
* Tracing goes to **LangSmith** (Section 22).

There is a single agent: no multi-agent setup and no extra abstraction layers. Don't use the legacy `create_react_agent`, and don't hand-roll a model ↔ `ToolNode` loop.

## 9.2 LangGraph Design

```text
START
  │
  ▼
validate_input ──── invalid / missing info ─────────────────────┐
  │ ok                                                            │
  ▼                                                               │
investigate  create_agent(model, tools=READ_TOOLS,                │
               system_prompt=ops_agent_system.md,                 │
               response_format=ToolStrategy(AgentProposal),       │
               middleware=[VerifiedIdMiddleware,                  │
                           PIIMiddleware("email"), call limits])  │
  │            ├── get_order, get_customer,                       │
  │            │   get_support_tickets, get_subscription          │
  │            └── → structured_response: AgentProposal           │
  │                                                               │
  ├── no valid proposal ──────────────────────────────────────────┤
  ▼ valid proposal                                                │
guardrails  (deterministic: severity, Rules 1–7, per-action       │
             decision: auto / approval / blocked)                 │
  │                                                               │
  ▼                                                               │
execute_actions  (auto actions only:                              │
                  create_support_ticket,                          │
                  send_operations_notification,                   │
                  prepare_customer_response)                      │
  │                                                               │
  ▼                                                               │
human_approval  (request_human_approval + interrupt()             │
                 when any action needs approval)                  │
  │                                                               │
  ▼                                                               │
respond  (assemble final structured response) ◄───────────────────┘
  │
  ▼
END
```

| Node | Type | Responsibility |
|---|---|---|
| `validate_input` | Deterministic | Check the request is non-empty and within the length limit, and extract IDs (`ORD-…`, `CUS-…`) with a regex. Only malformed input (empty or too long) goes straight to `respond`. A request **without IDs still goes to the LLM**, which asks the user for what is missing (Rule 5). |
| `investigate` | LLM | A `create_agent` that may call only **read-only** tools and must return an `AgentProposal` (intent, IDs, issue summary, evidence, proposed actions, draft customer response), validated by Pydantic. Guardrail middleware runs inside the agent loop: `VerifiedIdMiddleware` blocks lookups of IDs the customer never wrote, `PIIMiddleware` redacts emails from tool results, and `ModelCallLimitMiddleware` / `ToolCallLimitMiddleware` cap the loop. |
| `guardrails` | Deterministic | Compute severity, apply Rules 1–7, and decide per proposed action whether it runs automatically, needs approval, or is blocked. |
| `execute_actions` | Deterministic | Run only the actions that `guardrails` approved for automatic execution. |
| `human_approval` | Deterministic + HITL | Create approval requests and pause the graph with LangGraph `interrupt()`. The run resumes with the reviewer's decision (approve / reject), and approved actions are simulated. |
| `respond` | Deterministic | Build the final structured output (Section 14). |

Key rules:

* **The LLM never calls action tools.** Action tools (`create_support_ticket`, `send_operations_notification`, `request_human_approval`, and the simulated `issue_refund`, the only action that needs approval) are not given to `create_agent`. Only `execute_actions` and `human_approval` call them, after `guardrails` has decided.
* `AgentProposal` contains no severity, risk, or approval fields. Those are computed only by `guardrails`.
* If `investigate` produces no valid `AgentProposal` (validation error or call limit reached), the graph goes to `respond` with a safe error. No action is executed.
* Human-in-the-loop uses LangGraph `interrupt()` in the `human_approval` node, with a checkpointer (`InMemorySaver`) and a `thread_id` per request, so a paused run can be resumed after the approval decision. `HumanInTheLoopMiddleware` is not used: it only gates tool calls the LLM makes, while approval here is decided by deterministic rules.
* All prompts are versioned Markdown files in `src/prompts/` (see Section 19).
* Guardrails run in two layers (Section 12.7): LangChain middleware protects the LLM's investigation, and the `guardrails` node makes the business decisions.

Prefer a simple implementation over unnecessary framework complexity.

---

# 10. Tools

Implement deterministic tools as LangChain `@tool` functions with typed arguments. Tools never call the LLM and never fabricate data.

Tools fall into two groups (see Section 9.2):

| Group | Tools | Called by |
|---|---|---|
| `READ_TOOLS` | `get_order`, `get_customer`, `get_support_tickets`, `get_subscription` | The LLM (passed to `create_agent(tools=...)`) |
| `ACTION_TOOLS` | `create_support_ticket`, `send_operations_notification`, `prepare_customer_response`, `request_human_approval` | Graph nodes `execute_actions` / `human_approval` only, after guardrails |

At minimum:

## Tool 1 — get_order

```text
get_order(order_id)
```

Returns the order information.

If the order does not exist, return a structured error.

Example:

```json
{
  "success": false,
  "error": "ORDER_NOT_FOUND",
  "message": "Order ORD-9999 was not found."
}
```

Never fabricate an order.

---

## Tool 2 — get_customer

```text
get_customer(customer_id)
```

Returns customer information.

---

## Tool 3 — get_support_tickets

```text
get_support_tickets(customer_id, order_id?)
```

Returns existing support tickets related to the customer or order.

This allows the agent to detect duplicate or already-open issues.

---

## Tool 4 — get_subscription

```text
get_subscription(customer_id)
```

Returns subscription information.

---

## Tool 5 — create_support_ticket

```text
create_support_ticket(
    customer_id,
    order_id,
    issue_type,
    priority,
    summary
)
```

This can be a simulated action.

It should create a new ticket in an in-memory store or local JSON file.

Return a ticket ID.

Example:

```json
{
  "success": true,
  "ticket_id": "TCK-2042"
}
```

---

## Tool 6 — send_operations_notification

```text
send_operations_notification(
    severity,
    summary,
    order_id,
    recommended_action
)
```

Do NOT send a real Slack message.

Simulate the action by logging the notification or storing it locally.

Example:

```text
[SIMULATED SLACK]
Channel: #operations-alerts

HIGH PRIORITY
Order ORD-1007 has been delayed for 15 days.
Recommended action: Review refund request.
```

---

## Tool 7 — prepare_customer_response

```text
prepare_customer_response(
    customer_name,
    issue_summary,
    recommended_action,
    draft
)
```

Generate a draft response.

This action is safe because it does not send anything to the customer.

How the draft is produced:

* **The LLM writes the draft** (`AgentProposal.customer_response_draft`) during `investigate`. It follows an example response template kept in `src/prompts/customer_response_example.md`, which is injected into the system prompt. Changing the tone or structure of customer replies means editing that `.md` file, not code.
* **The tool does not write text.** Before it runs, the `execute_actions` node checks the draft against a deterministic content policy (`guardrails.check_customer_draft`: no refund or compensation promises, no internal details such as severity, rule names, or ticket priority). The tool then stores the draft, which is attached to the response labelled *draft — not sent*.
* If the draft violates the policy, it is not used. A short deterministic fallback draft takes its place, and the violation is logged.

---

## Tool 8 — request_human_approval

```text
request_human_approval(
    action,
    reason,
    context
)
```

Creates a pending approval request.

Example:

```json
{
  "approval_id": "APR-1001",
  "status": "pending",
  "action": "issue_refund",
  "reason": "Refund is a financial action."
}
```

---

# 11. Important Design Rule

The LLM MUST NOT directly perform business-critical actions.

Use the LLM for:

* Understanding the request
* Reasoning about the issue
* Selecting appropriate tools
* Producing summaries
* Recommending actions

Use deterministic application code for:

* Validation
* Risk classification
* Permission checks
* Financial thresholds
* Duplicate detection
* Final action authorization

The architecture should clearly separate:

```text
LLM Reasoning
        +
Deterministic Business Rules
        +
Tool Execution
```

---

# 12. Guardrails

Implement basic but meaningful guardrails.

## Rule 1 — Refunds require human approval

Any action that issues or processes a refund MUST NOT execute automatically.

Example:

```text
Refund < $50
    → still requires approval

Refund >= $50
    → requires approval
```

The exact threshold is less important than demonstrating the principle.

---

## Rule 2 — High-value orders require human approval

If:

```text
order.total_amount >= $500
```

the agent must not automatically perform operationally significant actions.

It should request human approval.

**Implementation decision (D2):** the only operationally significant action is a **refund**, and refunds always require approval (Rule 1). For high-value orders, Rule 2 therefore:

* routes any refund to human approval (already guaranteed by Rule 1, for any amount);
* escalates handling: ticket priority and operations-notification severity become `critical`, and severity rises to CRITICAL for refunds or missing orders (Section 13).

Internal actions (ticket, notification, draft) stay automatic, so the operations team is alerted immediately about the most valuable orders.

---

## Rule 3 — Sending external communication

The agent may prepare a customer response automatically.

It must NOT automatically send the response.

Allowed:

```text
prepare_customer_response()
```

Not allowed:

```text
send_customer_message()
```

unless explicitly approved by a human.

**Implementation decision (D2):** OpsPilot has no `send_customer_message` capability at all. It only produces a draft (labelled *draft — not sent*) for a human to send through their usual channel. If the LLM proposes sending a message, guardrails block it (`external_communication_blocked`).

---

## Rule 4 — Duplicate ticket protection

Before creating a new support ticket:

```text
get_support_tickets()
```

If there is already an open ticket for the same issue, do not create another ticket.

Instead report:

```text
An existing support ticket already exists.
Ticket: TCK-2001
Status: open
```

---

## Rule 5 — Missing critical information

If an action requires an order ID but no order ID is available:

Do NOT guess.

Ask the user for the missing information.

Example:

```text
I can investigate this issue, but I need the order ID
to continue.
```

How it is enforced:

* **The LLM asks.** It identifies what is missing for this specific request (order ID for an order issue, customer ID for a subscription issue). It returns `missing_fields` and a `clarification_question` in its proposal, without calling any tool.
* **Code guarantees nothing happens.** `VerifiedIdMiddleware` blocks any lookup with a guessed ID. The `guardrails` node sets status `needs_more_info` and blocks **every** action whenever required information is missing, even if the LLM proposed actions anyway.
* **The conversation continues.** The user's answer is sent together with the earlier messages, so the agent can resume the investigation with the full context.

---

## Rule 6 — Invalid IDs

If:

```text
order_id = ORD-999999
```

and the order does not exist:

Do not invent an order.

Return:

```text
I couldn't find order ORD-999999 in the available
operations data.
```

---

## Rule 7 — Unverified IDs (anti-hallucination)

The agent may only use order/customer IDs that the customer wrote, or IDs returned by an earlier tool result (e.g. the `customer_id` on an order). Any other ID is treated as hallucinated:

* A tool lookup with such an ID is blocked before the tool runs (`UNVERIFIED_ID`).
* A proposal referencing such an ID is rejected: status `error`, no actions.

---

## 12.7 Where Guardrails Are Enforced

Guardrails run in two deterministic layers. Neither layer uses an LLM.

| Layer | Mechanism | Guardrails | Why here |
|---|---|---|---|
| **1. Inside the investigator** | LangChain middleware on `create_agent` | `VerifiedIdMiddleware` (`wrap_tool_call`, Rule 7: block the lookup itself) · `PIIMiddleware("email", apply_to_tool_results=True)` (the LLM never sees customer emails) · `ModelCallLimitMiddleware` / `ToolCallLimitMiddleware` (bounded loop) | They protect *how the LLM investigates*. Middleware intercepts each model/tool call as it happens. |
| **2. `guardrails` node** | Pure functions in `src/guardrails/rules.py` and `severity.py` | Rules 1–4 and 6, Rule 7 (proposal check), severity, per-action decision (auto / human_approval / blocked) | They decide *what may happen* after the investigation, using data re-read from the repositories. |

Business decisions are deliberately **not** implemented as middleware:

* The LLM never calls action tools (Section 11), so there is no tool call for `wrap_tool_call` or `HumanInTheLoopMiddleware` to intercept.
* `HumanInTheLoopMiddleware` is configured statically per tool name. It cannot express data-dependent rules such as "orders of $500 or more need approval" (Rule 2).
* Severity is computed over the final proposal and the data, not over a single model or tool call.
* Pure functions in a separate graph node are easier to test exhaustively, and they show up as a distinct step in LangSmith traces. This makes the AI-vs-rules separation visible.

Rule 5 (missing information) spans both layers. The LLM writes the clarification question, layer 1 blocks guessed lookups, and layer 2 forces `needs_more_info` and blocks all actions.

---

# 13. Severity Classification

The agent should classify issues into:

```text
LOW
MEDIUM
HIGH
CRITICAL
```

Example deterministic guidelines:

### LOW

Simple informational request.

Example:

> Where is my order?

---

### MEDIUM

Issue requires operational investigation.

Example:

> My order is delayed by two days.

---

### HIGH

Significant operational problem or refund request.

Example:

> My order has been delayed for 15 days and I want a refund.

---

### CRITICAL

Potential financial or operational risk.

Examples:

* High-value refund
* Multiple duplicate refund requests
* Suspicious order activity
* Significant customer-impacting operational issue

The final severity should not depend entirely on LLM judgment.

Use deterministic rules where possible.

---

# 14. Agent Output

The final response should use a structured schema.

Example:

```json
{
  "issue_summary": "Order ORD-1007 is delayed by 15 days.",
  "severity": "HIGH",
  "evidence": [
    "Order status is delayed.",
    "Expected delivery date has passed.",
    "Customer requested a refund."
  ],
  "recommended_actions": [
    {
      "action": "create_support_ticket",
      "risk": "low",
      "execution": "automatic"
    },
    {
      "action": "send_operations_notification",
      "risk": "low",
      "execution": "automatic"
    },
    {
      "action": "issue_refund",
      "risk": "high",
      "execution": "human_approval"
    }
  ],
  "customer_response": "...",
  "approval_required": true
}
```

The schema can be improved as long as it remains clear and structured.

---

# 15. Safety Principle

The system must follow this principle:

> When uncertain, do less rather than more.

The agent should never:

* Invent missing data
* Invent an order
* Invent a customer
* Invent a support ticket
* Issue a refund without approval
* Send an external customer message automatically
* Assume missing information
* Execute an action when required context is unavailable

---

# 16. Required Demo Scenarios

The demo MUST include at least five scenarios.

All scenarios run against the sample data in `data/` with `REFERENCE_DATE=2026-10-10` as "today", so delays are deterministic: ORD-1001 is 2 days late, ORD-1007 is 15 days late, and ORD-1008 is 7 days late.

| # | Order | Data that drives the outcome | Status | Severity |
|---|---|---|---|---|
| 1 | ORD-1001 | Delayed 2 days, $89.50; only a **closed** ticket | `completed` | MEDIUM |
| 2 | ORD-1007 | Delayed 15 days, $249.99, customer Alex Johnson; **no** open ticket | `awaiting_approval` | HIGH |
| 3 | ORD-1008 | Delayed 7 days; **open** ticket TCK-2001 (`delivery_delay`) | `completed` | MEDIUM |
| 4 | ORD-9999 | Does not exist | `not_found` | — |
| 5 | — | No ID in the message | `needs_more_info` | — |
| 5b | ORD-1007 | Follow-up reply to Scenario 5 | `awaiting_approval` | HIGH |
| 6 (opt.) | ORD-1015 | Delayed 18 days, **$1,200** (high value) | `awaiting_approval` | CRITICAL |

## Scenario 1 — Normal delayed order

Input:

```text
My order ORD-1001 is two days late.
Can you check what is happening?
```

Expected:

* Retrieve order
* Detect delay (2 days past the expected delivery date)
* Summarize issue
* Recommend action
* No high-risk action
* Ticket + operations notification run automatically. The earlier ticket TCK-2004 is closed, so it does not block a new one.
* Severity MEDIUM

---

## Scenario 2 — Refund request

Input:

```text
My order ORD-1007 is 15 days late.
I want a refund.
```

Expected:

* Retrieve order
* Detect delivery delay (15 days, computed from the data, not from the customer's claim)
* Detect refund request
* Create a support ticket (no open ticket exists for ORD-1007) + operations notification
* Prepare customer response (draft, addressed to Alex, refund "being reviewed")
* Request human approval for refund
* Do NOT issue refund automatically
* Severity HIGH; status `awaiting_approval`

---

## Scenario 3 — Existing ticket

Input:

```text
Please help with my delayed order ORD-1008.
```

An open ticket (TCK-2001, `delivery_delay`) already exists for ORD-1008.

Expected:

* Retrieve existing ticket
* Do not create duplicate ticket (`create_support_ticket` → blocked, rule `duplicate_ticket`)
* Inform operations team or recommend follow-up
* Explain why a new ticket was not created ("An existing support ticket already exists. Ticket: TCK-2001, Status: open")

---

## Scenario 4 — Invalid order ID

Input:

```text
Please check order ORD-9999.
```

Expected:

```text
Order ORD-9999 was not found.
I cannot determine the order status from the available data.
```

No hallucinated information.

---

## Scenario 5 — Missing order ID

Input:

```text
My order hasn't arrived and I want a refund.
```

Expected:

```text
I can help investigate this, but I need the order ID
before I can check the order or determine whether a refund
is appropriate.
```

No tool should attempt to retrieve a guessed order.

The LLM phrases the question itself (Rule 5). Guardrails guarantee status `needs_more_info`, no tool execution, and no actions.

## Scenario 5b — Follow-up with the missing ID

Input, sent with Scenario 5's message as `history`:

```text
It's ORD-1007.
```

Expected:

* The agent combines both messages and continues as in Scenario 2 (refund → human approval)

---

# 17. Optional Scenario — High Value Refund

If time permits, include:

```text
My order ORD-1015 is delayed.
Please refund the order.
```

where:

```text
total_amount = $1,200
```

Expected:

```text
CRITICAL

Refund cannot be processed automatically.

Human approval required.
```

Severity is CRITICAL because a refund is requested on an order of $500 or more (Section 13). The ticket and operations notification still run automatically, with `critical` priority (decision D2 in Rule 2).

This scenario is useful for demonstrating guardrails.

---

# 18. User Interface

Keep the UI extremely simple.

## 18.1 Demo UI — Streamlit

The demo UI is a single **Streamlit** page (`src/web/app.py`). It should:

* Provide a text area for the customer request and a submit button.
* Show the structured result: issue summary, severity, evidence, recommended actions, and the draft customer response.
* Show executed actions and guardrail decisions, so the demo can explain *why* something was or wasn't done.
* Show pending approvals with **Approve / Reject** buttons that resume the paused LangGraph run.
* When the agent asks for missing information (`needs_more_info`), show its question and let the user reply in place. The reply is sent with the conversation history.

Implementation notes:

* Streamlit calls the agent **in-process** through the same service function used by the API (e.g. `run_agent(message)` / `resume_agent(thread_id, decision)`). It does not call the agent over HTTP.
* Build the compiled graph and its checkpointer once with `st.cache_resource`. Streamlit reruns the script on every interaction, and paused runs must survive those reruns.
* Use default Streamlit components only. Do NOT spend time on styling.

## 18.2 REST API

A thin FastAPI wrapper over the same service function:

```text
POST /api/v1/agent/analyze
```

Request:

```json
{
  "message": "My order ORD-1007 is 15 days late and I want a refund."
}
```

Response:

```json
{
  "issue_summary": "...",
  "severity": "HIGH",
  "evidence": [],
  "recommended_actions": [],
  "approval_required": true
}
```

Follow-up turns (Rule 5): when a response has `status: "needs_more_info"`, the client sends the user's answer as `message` and the earlier customer messages as an optional `history`. The service stays stateless per turn.

```json
{
  "message": "It's ORD-1007.",
  "history": ["My order hasn't arrived and I want a refund."]
}
```

In the demo, approval decisions are made through the Streamlit UI. The API returns pending approvals in its response but does not need a resume endpoint.

Do NOT spend significant time on visual design.

---

# 19. Project Structure

The repository uses the following structure:

```text
Operations-Automation-Agent/
│
├── src/
│   ├── main.py                  # FastAPI entry point: app = create_app()  →  uvicorn src.main:app
│   │
│   ├── .env/
│   │   ├── .env.example         # Committed template
│   │   └── .env                 # Real secrets (gitignored)
│   │
│   ├── config/
│   │   └── settings.py          # pydantic-settings; loads src/.env/.env (OpenAI model, thresholds, data dir, reference date)
│   │
│   ├── api/
│   │   ├── routes.py            # POST /api/v1/agent/analyze, GET /healthz
│   │   └── schemas.py           # AnalyzeRequest (response model comes from common/schemas)
│   │
│   ├── agents/
│   │   ├── graph.py             # build_graph(): outer LangGraph StateGraph wiring + compile(checkpointer)
│   │   ├── investigator.py      # build_investigator(): create_agent(READ_TOOLS, ToolStrategy(AgentProposal), limits)
│   │   ├── nodes.py             # validate_input, investigate, guardrails, execute_actions, human_approval, respond
│   │   ├── state.py             # OpsState (input, extracted IDs, proposal, decisions, actions, approvals, error)
│   │   ├── responder.py         # build_response(): AnalyzeResponse from graph state (also while paused)
│   │   └── service.py           # run_agent() / resume_agent(): shared by Streamlit and FastAPI
│   │
│   ├── common/
│   │   └── schemas/             # Pydantic models + enums shared across layers (no logic, no I/O)
│   │       ├── __init__.py      # Re-exports the public schemas
│   │       ├── enums.py         # OrderStatus, IssueType, TicketStatus, Severity, Execution, ...
│   │       ├── ids.py           # Entity ID formats (ORD-\d+, CUS-\d+): the single definition
│   │       ├── domain.py        # Order, Customer, SupportTicket, Subscription
│   │       ├── actions.py       # OperationsNotification, CustomerDraft, ApprovalRequest, RefundRecord
│   │       ├── proposal.py      # AgentProposal, ProposedAction (LLM structured output)
│   │       ├── decisions.py     # Facts, GuardrailDecision, GuardrailResult, PolicyViolation (guardrails I/O)
│   │       └── response.py      # AnalyzeResponse + nested models (shared by API and Streamlit)
│   │
│   ├── llm/
│   │   └── client.py            # get_chat_model(): init_chat_model("openai:<model>", timeout, max_retries)
│   │
│   ├── prompts/                 # Every LLM instruction lives here as a .md file — no prompt text in .py
│   │   ├── loader.py            # load_prompt(name) → Prompt(name, version, text); parses YAML frontmatter
│   │   ├── ops_agent_system.md  # System prompt for `investigate` (frontmatter: name, version, description, variables)
│   │   └── customer_response_example.md  # Example customer reply the LLM follows; injected into ops_agent_system via $customer_response_example
│   │
│   ├── tools/                   # LangChain @tool functions — deterministic, never call the LLM
│   │   ├── orders.py            # get_order
│   │   ├── customers.py         # get_customer
│   │   ├── tickets.py           # get_support_tickets, create_support_ticket
│   │   ├── subscriptions.py     # get_subscription
│   │   ├── actions.py           # send_operations_notification, prepare_customer_response, request_human_approval
│   │   └── registry.py          # READ_TOOLS (bound to the LLM) / ACTION_TOOLS (executor nodes only)
│   │
│   ├── guardrails/              # Deterministic guardrails — never call an LLM
│   │   ├── rules.py             # Business rules R1–R7 as pure functions (no LangChain imports)
│   │   ├── severity.py          # LOW / MEDIUM / HIGH / CRITICAL classification (no LangChain imports)
│   │   ├── draft_policy.py      # R8: content policy for the LLM's customer reply draft (no LangChain imports)
│   │   └── middleware.py        # VerifiedIdMiddleware (wrap_tool_call) for the investigator agent
│   │
│   ├── repositories/            # Data access (repository pattern) — used by tools and guardrails node
│   │   ├── data_store.py        # Loads data/*.json (read-only operational data)
│   │   ├── action_store.py      # In-memory store for created tickets, notifications, approval requests
│   │   └── tickets.py           # find_tickets(): sample + created tickets (duplicate detection needs both)
│   │
│   ├── memory/                  # Agent memory only
│   │   └── checkpointer.py      # LangGraph InMemorySaver with a serde allowlist of our state types (pause/resume)
│   │
│   ├── utils/
│   │   ├── logging.py           # Structured logging + request_id
│   │   ├── ids.py               # ID regexes + extract_ids(text): shared by validate_input, tools, middleware
│   │   ├── dates.py             # days_late(): shared by get_order and guardrails
│   │   └── errors.py            # Error types and structured tool errors
│   │
│   └── web/
│       └── app.py               # Streamlit demo UI: submit request, show result, approve / reject
│
├── data/
│   ├── orders.json
│   ├── customers.json
│   ├── support_tickets.json
│   └── subscriptions.json
│
├── test/
│   ├── conftest.py              # Fixtures, fake chat model (scripted LLM responses — no OpenAI / LangSmith calls)
│   ├── test_tools.py
│   ├── test_guardrails.py
│   └── test_agent.py
│
├── specs/
│   └── specification.md
│
├── .python-version
├── pyproject.toml
└── README.md
```

Layer responsibilities and allowed dependencies:

| Layer | Responsibility | May import |
|---|---|---|
| `web` | Streamlit demo UI | `agents` (via `service.py`), `common`, `config`, `utils` |
| `api` | HTTP contract, request validation, error mapping | `agents` (via `service.py`), `common`, `config`, `utils` |
| `agents` | LangGraph graph: LLM reasoning, tool calls, guardrails, execution, approval | `llm`, `tools`, `guardrails`, `repositories`, `memory`, `prompts`, `common`, `config`, `utils` |
| `llm` | Chat model factory (`init_chat_model`) | `config`, `utils` |
| `prompts` | Prompt `.md` files + loader | — |
| `tools` | Deterministic tool functions (read + simulated actions) | `repositories`, `common`, `utils` |
| `guardrails` | Deterministic risk, severity, and authorization decisions | `common`, `utils` (pure functions over data) |
| `repositories` | Sample data loading and in-memory action state | `common`, `config`, `utils` |
| `memory` | Agent memory (LangGraph checkpointer) | `common` (state types for the serde allowlist) |
| `common` | Shared Pydantic schemas and enums: no logic, no I/O | — (imports nothing from `src`) |

`guardrails` and `tools` must never import `llm`. This keeps AI reasoning separate from deterministic business rules (see Section 11). Schemas used by more than one layer live in `common/schemas`, so layers never import each other just to share a model.

Do not add unnecessary infrastructure. `docker-compose.yml` is optional and only worth adding if it is a single service.

---

# 20. Technology Stack

| Area | Choice | Package(s) |
|---|---|---|
| Language / tooling | Python 3.14, managed with uv | — |
| LLM | OpenAI models via LangChain v1 (`init_chat_model("openai:<model>")`) | `langchain`, `langchain-openai` |
| Agent | LangChain `create_agent` + `ToolStrategy` structured output + call-limit middleware | `langchain` |
| Orchestration / HITL | LangGraph (`StateGraph`, `interrupt()`, `Command(resume=...)`, `InMemorySaver`) | `langgraph` |
| Prompts | Versioned Markdown files with YAML frontmatter | `pyyaml` |
| Tracing | LangSmith | `langsmith` |
| Demo UI | Streamlit | `streamlit` |
| REST API | FastAPI (thin wrapper) | `fastapi`, `uvicorn` |
| Validation / config | Pydantic v2, pydantic-settings, python-dotenv | `pydantic`, `pydantic-settings`, `python-dotenv` |
| Testing | pytest | `pytest` |

```bash
uv add langchain langchain-openai langgraph langsmith streamlit fastapi uvicorn pydantic-settings python-dotenv pyyaml
uv add --dev pytest
```

## 20.1 Configuration

All configuration lives in `src/.env/.env` (template: `src/.env/.env.example`):

```text
OPENAI_API_KEY=
OPENAI_MODEL=                     # set explicitly; never hard-code the model name in code

LANGSMITH_TRACING=true
LANGSMITH_API_KEY=
LANGSMITH_PROJECT=opspilot-demo

HIGH_VALUE_THRESHOLD=500
REFERENCE_DATE=                   # optional fixed "today" so delay calculations stay deterministic in the demo
```

At startup, load `src/.env/.env` into the process environment (`load_dotenv(ENV_FILE)`, with the path built from `__file__` in `src/config/settings.py`, not from the current working directory). LangChain and LangSmith read `OPENAI_API_KEY` and `LANGSMITH_*` directly from environment variables, and pydantic-settings alone does not export them.

## 20.2 Constraints

* Do not use other agent frameworks (OpenAI Agents SDK, CrewAI, etc.) alongside LangGraph.
* Avoid introducing unnecessary technologies. For the demo, local JSON data is sufficient (no database).

---

# 21. Reliability Requirements

The implementation should prioritize reliability over cleverness.

The system should:

* Use structured outputs (`create_agent(..., response_format=ToolStrategy(<PydanticModel>))`)
* Validate LLM output with Pydantic
* Validate tool arguments (typed `@tool` signatures / Pydantic `args_schema`)
* Handle tool errors
* Handle missing data
* Handle malformed requests
* Avoid hallucinating database records
* Separate recommendation from execution
* Log important decisions

If the LLM fails to produce a valid structured response, return a safe error rather than executing an action.

---

# 22. Observability

Observability has two complementary parts.

## 22.1 Tracing — LangSmith

LangSmith traces every LangGraph run automatically once `LANGSMITH_TRACING=true` and `LANGSMITH_API_KEY` are set (Section 20.1). Each trace shows nodes, LLM calls, tool calls, inputs/outputs, latency, and token usage.

* Pass the `request_id` in the run config (`config={"configurable": {"thread_id": ...}, "metadata": {"request_id": ...}, "tags": [...]}`) so a log line can be matched to its trace.
* Name graph nodes clearly (Section 9.2), because the node names are what the reviewer sees in the trace tree.
* Tracing must be disabled in tests (`LANGSMITH_TRACING=false`).
* Traces contain user input and data. This is acceptable only because all demo data is fictional. Mention it under Known Limitations.

## 22.2 Application Logs

Add lightweight structured logging for decisions that matter outside LangSmith (especially deterministic guardrail decisions).

For each request, log:

```text
request_id
user_input
detected_intent
tools_called
tool_results
severity
recommended_actions
guardrail_decisions
executed_actions
approval_requests
```

Example:

```text
[INFO] request_id=req-123
[INFO] intent=refund_request
[INFO] tool=get_order
[INFO] order_id=ORD-1007
[INFO] severity=HIGH
[INFO] guardrail=refund_requires_approval
[INFO] action=create_support_ticket
[INFO] action=request_human_approval
```

Do not log secrets.

---

# 23. Testing

At minimum, implement tests for:

### Test 1

Valid order lookup.

### Test 2

Invalid order lookup.

### Test 3

Missing order ID.

### Test 4

Refund requires approval.

### Test 5

High-value order requires approval.

### Test 6

Duplicate support ticket prevention.

### Test 7

Safe action can execute automatically.

### Test 8

Malformed LLM output cannot trigger an action.

Tests must not call OpenAI or LangSmith. Inject a fake chat model with scripted responses into the graph (via `src/llm/client.py`), and test guardrails and tools as plain functions.

```bash
uv run pytest                                              # all tests
uv run pytest test/test_guardrails.py::test_refund_requires_approval   # single test
```

---

# 24. Evaluation Criteria

Design the solution as if it will be evaluated on:

## Architecture — 25%

Is the system modular?

Are AI reasoning, business rules, tools, and actions separated?

---

## Reliability — 25%

Does the system safely handle:

* Missing data?
* Invalid IDs?
* Tool failures?
* Hallucination?
* Uncertain cases?

---

## Agent Design — 20%

Does the agent:

* Select appropriate tools?
* Reason about the issue?
* Produce structured output?
* Use context correctly?

---

## Guardrails — 20%

Does the system prevent risky autonomous actions?

Does it support human approval?

---

## Code Quality — 10%

Is the implementation:

* Simple?
* Readable?
* Testable?
* Well structured?

---

# 25. README Requirements

The README MUST contain:

## 1. Problem

Explain the business problem.

## 2. Solution

Explain how OpsPilot solves it.

## 3. Architecture

Include an architecture diagram.

Example:

```text
                    ┌─────────────────┐
                    │   User Request  │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │ Input Validator │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │  AI Operations  │
                    │      Agent      │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
          Order Tool    Ticket Tool    Customer Tool
              │              │              │
              └──────────────┼──────────────┘
                             ▼
                    ┌─────────────────┐
                    │ Decision / Risk │
                    │    Engine       │
                    └────────┬────────┘
                             │
                   ┌─────────┴─────────┐
                   ▼                   ▼
             Safe Action          High Risk
                   │                   │
                   ▼                   ▼
              Auto Execute       Human Approval
```

## 4. Key Design Decisions

Explain why:

* LLM reasoning is separated from deterministic rules
* High-risk actions require approval
* Tools never fabricate data
* External communication is not automatically sent

## 5. How to Run

Provide exact commands.

Example:

```bash
uv sync
cp src/.env/.env.example src/.env/.env                   # then fill in OPENAI_API_KEY, OPENAI_MODEL, LANGSMITH_API_KEY

uv run python -m streamlit run src/web/app.py     # demo UI (run from repo root)
uv run uvicorn src.main:app --reload              # REST API (optional)
uv run pytest                                     # tests
```

Use `python -m streamlit` rather than the bare `streamlit` command. Run that way, the repo root is on `sys.path`, so `import src...` works inside `src/web/app.py`.

## 6. Demo Examples

Provide the five required scenarios.

## 7. Known Limitations

Be honest.

Example:

* Sample data is local
* Actions are simulated
* No real Slack integration
* No production authentication
* No persistent production database
* Limited evaluation dataset
* Human approval is simulated; pending approvals live in memory (`InMemorySaver`) and are lost on restart
* LangSmith traces contain request text (acceptable only because demo data is fictional)

## 8. Production Improvements

Explain what you would change for a production system.

---

# 26. Production Discussion

In the README and Loom video, explain how the architecture could evolve.

Potential improvements:

* Real database
* Authentication / authorization
* RBAC
* Real ticketing integration
* Slack integration
* Persistent approval workflow (durable LangGraph checkpointer, e.g. Postgres, instead of `InMemorySaver`)
* Audit logs
* Retry policies
* Rate limiting
* Observability (metrics, alerting on top of LangSmith traces)
* Evaluation framework (LangSmith datasets + evaluators run on every prompt/model change)
* Prompt/version management
* Model fallback
* PII protection
* Secrets management
* Idempotency
* Event-driven architecture

Do NOT implement all of these.

Only explain them.

---

# 27. Important Scope Constraint

This is a 2–4 hour coding challenge.

Prioritize:

1. Working agent
2. Tool calling
3. Deterministic guardrails
4. Human approval
5. Safe error handling
6. Clear architecture
7. Tests
8. README

Do NOT spend significant time on:

* UI polish
* Authentication
* Cloud deployment
* Kubernetes
* Terraform
* Real Slack integration
* Complex databases
* Advanced frontend
* Multi-agent architecture

The demo should remain small and easy to understand.

---

# 28. Coding Principles

Follow these principles:

### Principle 1

Prefer deterministic code for deterministic decisions.

### Principle 2

Use the LLM where natural-language understanding and reasoning provide value.

### Principle 3

Never allow the LLM alone to authorize a high-risk action.

### Principle 4

Never invent missing operational data.

### Principle 5

When uncertain, ask for clarification or request human approval.

### Principle 6

Every action should be traceable.

### Principle 7

Keep the architecture simple enough to explain in a 3–5 minute Loom video.

---

# 29. Final Deliverables

The final repository MUST contain:

* Working source code
* Sample data
* Tests
* README
* `src/.env/.env.example`
* Architecture diagram
* Demo scenarios

The final demo MUST show:

1. Normal operational request
2. Delayed order
3. Refund request
4. Human approval for risky action
5. Existing ticket / duplicate prevention
6. Invalid order
7. Missing order ID
8. Safe handling of incomplete information

---

# 30. Final Success Criteria

The project is successful if a reviewer can understand within a few minutes:

> "This developer knows how to build an AI agent that can reason about operational data, use tools, make recommendations, execute safe actions, and stop when an action is risky or uncertain."

The system should demonstrate:

```text
Business Problem
       ↓
AI Reasoning
       ↓
Tool Calling
       ↓
Evidence
       ↓
Deterministic Rules
       ↓
Risk Assessment
       ↓
Safe Automation
       ↓
Human Approval
```

The implementation should favor **reliability and clarity over complexity**.
