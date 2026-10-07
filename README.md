# OpsPilot: AI Operations Automation Agent

OpsPilot helps a support and operations team handle customer requests for a fictional e-commerce company. Customers talk to a **chatbot**. OpsPilot looks up the order data, explains the issue with evidence, handles safe tasks itself, **reports every case to the team in Slack**, and sends **every refund to a human** for approval.

> **Core idea:** the AI *investigates and recommends*, business rules *decide*, and a human *approves* anything involving money.

---

## 1. Problem

Support teams handle delayed or missing orders, cancellations, refund requests, and subscription problems. For every request, someone has to read the message, look up the order, customer, past tickets, and subscription, judge how serious it is, check for an existing ticket, decide what to do, and write a reply. This is **slow, repetitive, and inconsistent**.

Handing the whole job to an AI is **risky**: it can invent data, issue a refund on its own, or promise the customer something nobody approved.

## 2. Solution

OpsPilot works like a new team member who prepares the case file: it does the research, handles small safe tasks itself, and **escalates money decisions to a person**.

**Example (Scenario 2):** *"My order ORD-1007 is 15 days late. I want a refund."*

1. The **Investigate Agent** looks up the data: Alex Johnson's order, $249.99, 15 days late, no open ticket.
2. The **Guardrails** rate it **HIGH**: the ticket and the reply draft run automatically, and the refund waits for approval.
3. The chatbot tells the customer the refund request is being reviewed. It never promises a refund.
4. The full report is posted to Slack, tagging the team.
5. A manager clicks **Approve** on the **Operation Admin** page: the (simulated) refund is issued, Slack gets a thread reply, and the chatbot tells the customer the outcome.

**Who does what**

| Part | Role |
|---|---|
| **Investigate Agent** (AI) | Understands the request, looks up data with read-only tools, and writes a summary, evidence, recommended actions, and a reply draft |
| **Guardrails** (business rules) | Re-check the data, set the severity, and decide for each action: automatic, needs approval, or blocked |
| **Workflow** | Runs only the allowed actions: ticket, reply draft, Slack report |
| **Human** | Approves or rejects refunds on the Operation Admin page |

**Business rules**

| Rule | Meaning |
|---|---|
| R1 Refunds need approval | Every refund waits for a human, whatever the amount |
| R2 High-value orders ($500+) | Severity becomes CRITICAL; the ticket and alert are marked critical |
| R3 No direct customer messaging | The customer only sees the checked reply and the decision notice |
| R4 No duplicate tickets | An open ticket for the same issue blocks a new one |
| R5 Missing information | Without an order ID, the agent asks; nothing runs |
| R6 Order not found | OpsPilot says so; nothing runs |
| R7 Unverified ID | The AI mentions an ID nobody wrote: treated as invented; nothing runs |
| R8 Safe replies | A reply that promises a refund or compensation, or leaks internal details, is replaced by a safe message |

Guiding principle: **when uncertain, do less rather than more.**

## 3. Architecture

### System architecture

An editable version of this diagram is in [`docs/architecture.drawio`](docs/architecture.drawio) (open it at [app.diagrams.net](https://app.diagrams.net)).

```mermaid
flowchart TB
    subgraph clients["Clients"]
        customer(["Customer"])
        admin(["Ops admin"])
        apiclient(["API client"])
    end

    subgraph presentation["Presentation layer"]
        chat["Streamlit · Chat page"]
        adminpage["Streamlit · Operation Admin<br>Cases · Tickets · Approve/Reject"]
        api["FastAPI<br>POST /api/v1/agent/analyze"]
    end

    subgraph application["Application layer"]
        service["Agent service<br>run_agent · resume_agent · get_case · list_cases · list_tickets"]
    end

    subgraph orchestration["Agent orchestration · LangGraph StateGraph"]
        direction LR
        validate["validate_input"] --> investigate["investigate<br>(LLM)"] --> guard["guardrails"] --> execute["execute_actions"] --> notify["notify_operations"] --> approval["human_approval<br>interrupt()"] --> respond["respond"]
    end

    subgraph investigator["Investigator · LangChain create_agent"]
        prompts["Versioned prompts (.md)"]
        middleware["Middleware: VerifiedId · PII · call limits"]
        proposal["AgentProposal (structured output)"]
    end

    subgraph guardrails["Guardrails · deterministic"]
        rules["Rules R1–R8"]
        severity["Severity table"]
    end

    subgraph tools["Tools · LangChain @tool"]
        readtools["Read tools (LLM)<br>get_order · get_customer<br>get_support_tickets · get_subscription"]
        actiontools["Action tools (graph nodes only)<br>create_support_ticket · prepare_customer_response<br>request_human_approval · issue_refund<br>send_operations_notification"]
    end

    subgraph data["Data layer (demo: JSON + in-memory)"]
        opsdata[("Operational data · JSON<br>orders · customers · tickets · subscriptions")]
        actionstore[("Action store<br>tickets · approvals · refunds · drafts · notifications")]
        casestore[("Case store<br>one CaseRecord per request")]
        checkpointer[("Checkpointer<br>InMemorySaver · thread_id = request_id")]
    end

    subgraph external["External services"]
        openai{{"OpenAI"}}
        slack{{"Slack"}}
        langsmith{{"LangSmith"}}
    end

    customer --> chat
    admin --> adminpage
    apiclient --> api
    chat -- "run_agent · poll get_case" --> service
    adminpage -- "resume_agent · list_cases" --> service
    api -- "run_agent" --> service
    service --> validate
    service -- "save / read" --> casestore
    investigate --> investigator
    investigator -- "LLM calls" --> openai
    middleware -- "verified tool calls" --> readtools
    guard --> guardrails
    execute -- "allowed actions" --> actiontools
    notify -- "approvals + report" --> actiontools
    approval -- "issue_refund if approved" --> actiontools
    readtools -- "read" --> opsdata
    readtools -. "created tickets (R4)" .-> actionstore
    actiontools -- "write" --> actionstore
    actiontools -- "chat.postMessage · thread reply" --> slack
    approval -- "pause / resume" --> checkpointer
    orchestration -. "traces" .-> langsmith
```

### Agent workflow

![OpsPilot LangGraph flow](docs/langgraph-flow.png)

Purple: the Investigate Agent, the only AI step. Green: plain code. Orange: human approval. Dashed lines are early exits when something is wrong or missing. Diagram source: [`docs/langgraph-flow.mmd`](docs/langgraph-flow.mmd).

<details>
<summary>Text version with more detail</summary>

```text
                        ┌──────────────────────┐
                        │   Customer request   │  Chat page (Streamlit) · REST API
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
                               │  │   execute_actions    │  ticket · reply draft (R8-checked)
                               │  └──────────┬───────────┘
                               │             ▼
                               │  ┌──────────────────────┐
                               │  │  notify_operations   │  approval requests + full report → Slack
                               │  └──────────┬───────────┘  (tags the ops team; simulated if unset)
                               │             ▼
                               │  ┌──────────────────────┐
                               │  │    human_approval    │  interrupt(): pauses for refunds, resumes on
                               │  └──────────┬───────────┘  Approve / Reject in Operation Admin → Slack thread
                               ▼             ▼
                        ┌──────────────────────┐
                        │       respond        │  structured AnalyzeResponse
                        └──────────────────────┘
```

</details>

### Where things live

| Path | Contents |
|---|---|
| `src/agents/` | The workflow, the Investigate Agent, and the service used by the UI and the API |
| `src/guardrails/` | Business rules R1–R8 and the severity table (plain code, no AI) |
| `src/tools/` | Read tools for the agent; action tools for the workflow |
| `src/prompts/` | Versioned prompt files |
| `src/repositories/`, `src/memory/` | Sample data access, in-memory records, saved workflow state |
| `src/web/`, `src/api/` | Streamlit pages (Chat, Operation Admin) and the REST API |
| `src/integrations/` | Slack |
| `data/` | Fictional sample data: 15 orders, 12 customers, 8 tickets, 10 subscriptions |
| `docs/`, `specs/`, `plans/` | Diagrams, demo script, business overview, specification, build plan |

## 4. Key Design Decisions

- **AI and rules are separate.** Only the Investigate Agent uses the AI. Severity, approvals, and duplicate checks are plain code with their own tests. The agent's output has no field for severity or approval, so it cannot make those decisions.
- **The AI can only read.** It gets four read-only tools. Tickets, Slack reports, approvals, and refunds are run by the workflow, and only after the guardrails allow them. If the AI's output is invalid, nothing runs.
- **Two layers of guardrails.** During the investigation, the agent cannot look up an ID the customer never wrote, and customer emails are hidden from the AI. After it, the business rules make the decisions.
- **Human approval pauses the workflow.** The workflow stops and saves its state; Approve or Reject resumes it. The refund tool itself refuses to run without an approval.
- **Customer text is controlled.** Replies pass the R8 check. The notice after an approval decision uses a fixed template, not AI text, so amounts and references are exact.
- **Prompts are versioned files**, and every run is traced in LangSmith with the prompt versions. Logs record message length and IDs, not the customer's text.

**Decisions on points the spec left open**

| ID | Decision |
|---|---|
| D1 | "Today" is fixed at 2026-10-10 so delays are reproducible; Scenario 3 uses ORD-1008 |
| D2 | Only refunds need approval; high-value orders raise the priority instead |
| D3 | Severity comes from a fixed table; the highest matching level wins |
| D4 | The agent writes the reply from an example template; R8 checks it |
| D5 | When information is missing, the agent asks in its own words and continues with the earlier messages |
| D6 | Client request: the chatbot shows the checked reply to the customer (changes spec Rule 3) |
| D7 | Client request: real Slack reports that tag the team; simulated when Slack is not configured |
| D8 | Approvals live on a separate Operation Admin page, never in the customer chat |
| D9 | Slack is notified only when the guardrails allow it |
| D10 | Client request: after Approve or Reject, the chatbot tells the customer the outcome |

## 5. How to Run

Requirements: [uv](https://docs.astral.sh/uv/) (installs Python 3.14), an OpenAI API key, and optionally LangSmith and Slack.

```bash
uv sync
cp src/.env/.env.example src/.env/.env      # set OPENAI_API_KEY, OPENAI_MODEL (e.g. gpt-4.1-mini); LANGSMITH_*, SLACK_* optional

uv run python -m streamlit run src/web/app.py     # demo UI → http://localhost:8501 (Chat + Operation Admin)
uv run uvicorn src.main:app --reload              # REST API → http://localhost:8000/docs
uv run pytest                                     # tests (offline, no OpenAI or Slack calls)
```

Run commands from the repository root.

**Slack (optional):** create a Slack app with the `chat:write` bot scope, invite the bot to a channel, and set `SLACK_BOT_TOKEN`, `SLACK_CHANNEL_ID`, and `SLACK_MENTION_USER_IDS` (people to tag). Without them, reports are only logged.

**API example:**

```bash
curl -X POST localhost:8000/api/v1/agent/analyze -H 'Content-Type: application/json' \
  -d '{"message": "Please check order ORD-9999."}'
```

## 6. Demo Examples

Use the scenario buttons on the **Chat** page, then open **Operation Admin** to see each case, the tickets, and pending refunds.

| # | Customer message | What happens |
|---|---|---|
| 1 | My order ORD-1001 is two days late. Can you check what is happening? | **MEDIUM**: ticket and reply run automatically. Send it twice: the second ticket is blocked as a duplicate |
| 2 | My order ORD-1007 is 15 days late. I want a refund. | **HIGH**: ticket and reply run; the refund waits for approval |
| 3 | Please help with my delayed order ORD-1008. | New ticket blocked: open ticket TCK-2001 already exists; the team is asked to follow up |
| 4 | Please check order ORD-9999. | "Not found"; no invented data, nothing runs |
| 5 | My order hasn't arrived and I want a refund. | The agent asks for the order ID. Reply "It's ORD-1007." and it continues |
| 6 | My order ORD-1015 is delayed. Please refund the order. | **CRITICAL** ($1,200); the refund waits for approval |

All scenarios were verified end to end with `gpt-4.1-mini` and a real Slack workspace.

## 7. Known Limitations

- Sample data is local JSON; tickets and refunds are simulated (Slack is real).
- Cases, approvals, and paused workflows live in memory and are lost on restart.
- No login: anyone who can open the Operation Admin page can approve a refund.
- The customer sees AI-written replies. R8 blocks promises, but the wording can vary between runs.
- Slack reports and LangSmith traces contain customer names and messages (acceptable only because the data is fictional).
- There is no automated AI evaluation suite, and duplicate detection depends on the agent classifying the issue type consistently.

## 8. Production Improvements

| Area | Change |
|---|---|
| Data | Real databases, and durable workflow storage (e.g. Postgres) so paused approvals survive restarts |
| Integrations | Real ticketing (e.g. Zendesk, Jira) and payments, with idempotency keys |
| Security | Login and roles (who may approve which refunds), secrets in a secret manager |
| Approvals | An approval queue with assignees, SLAs, an audit trail, and an API |
| Reliability | Retries, timeouts, rate limits, and a fallback model |
| Quality | LangSmith evaluation datasets run on every prompt or model change |
| Observability | Metrics and alerts (approval time, block rate, AI errors), and PII redaction in logs and traces |

---

**Tech stack:** Python 3.14 · uv · LangChain · LangGraph · OpenAI · LangSmith · Pydantic · Streamlit · FastAPI · pytest · ruff · mypy.
