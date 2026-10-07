# OpsPilot: AI Operations Automation Agent

OpsPilot helps a support and operations team handle customer requests for a fictional e-commerce company. Customers talk to a **chatbot**. OpsPilot looks up the order data, explains the issue with evidence, handles safe tasks itself, **reports every case to the team in Slack**, and sends **every refund to a human** for approval.

> **Core idea:** the AI *investigates and recommends*, business rules *decide*, and a human *approves* anything involving money.

---

## 1. Problem Statement

### Business context

**The company** is a fictional **direct-to-consumer (DTC)** e-commerce business. It sells to consumers through its own website and also offers **subscription** plans (recurring orders).

**The users** are the **Customer Support and Operations** team. Every day they receive a large volume of customer requests:

- Delayed or missing orders
- Cancelled orders and address changes
- Refund requests
- Subscription problems (failed payments, paused plans)

### The problem today

For every request, a team member works through the same steps by hand:

1. Read the message and work out what the customer wants.
2. Open several systems to look things up: orders, customers, past tickets, subscriptions.
3. Judge how serious the issue is, and each person judges differently.
4. Check whether a ticket already exists, to avoid duplicate work.
5. Decide what to do next: create a ticket, alert the operations team, issue a refund.
6. Write a reply to the customer.

This is **slow, repetitive, and inconsistent**: customers wait, serious cases are not escalated fast enough, and two people can end up working on the same case.

### Why not let an AI do it all?

Handing the whole job to an AI is **dangerous**. An AI can:

- **invent data**, for example say an order is on its way when the order does not exist;
- **issue a refund on its own**, causing direct financial loss;
- **send the wrong message to a customer**, for example promise a refund nobody approved.

**The goal:** automate the research and the routine work so the team gets a ready case file, while keeping every money decision with a person and never letting the AI act on data it has not verified.

## 2. Solution

OpsPilot works like a new team member who prepares the case file: it does the research, handles small safe tasks itself, and **escalates money decisions to a person**.

**Example:** *"My order ORD-1007 is 15 days late. I want a refund."*

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
| D1 | "Today" is fixed at 2026-10-10 so delays computed from the sample data are reproducible |
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

## 6. Known Limitations

- Sample data is local JSON; tickets and refunds are simulated (Slack is real).
- Cases, approvals, and paused workflows live in memory and are lost on restart.
- No login: anyone who can open the Operation Admin page can approve a refund.
- The customer sees AI-written replies. R8 blocks promises, but the wording can vary between runs.
- Slack reports and LangSmith traces contain customer names and messages (acceptable only because the data is fictional).
- There is no automated AI evaluation suite, and duplicate detection depends on the agent classifying the issue type consistently.

## 7. Production Improvements

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
