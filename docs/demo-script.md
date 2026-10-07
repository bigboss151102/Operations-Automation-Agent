# Loom Demo Script (≈ 5 minutes)

The brief asks the video to show **how the demo works**, **why it is designed this way**, and **what would change for production**, and to show how a business problem becomes a **practical, testable AI system**.

## Before recording

```bash
uv run python -m streamlit run src/web/app.py
```

- Restart Streamlit so the latest prompt is loaded.
- Open side by side: the **Chat** page (the customer), the **Operation Admin** page in a second tab (the operations team), and the **Slack** channel.
- On Operation Admin, click **Reset demo data** so IDs start fresh (TCK-2009, RFD-0001).
- **Do a full dry run first** (LLM output varies between runs), then reset again.
- Prepare so the recording never waits:
  - send **1 · Delayed order** twice, so the **Tickets** tab already shows 🆕 TCK-2009 and the second ticket blocked as a duplicate;
  - run `uv run pytest` in a terminal (237 passed);
  - open `src/guardrails/rules.py` in the editor and one `opspilot` trace in LangSmith.
- Do **not** click "New conversation" while a refund is pending: the chat would not receive the decision.

## Timeline

| Time | Screen | Say | Do |
|---|---|---|---|
| **0:00–0:30** Problem | README, Problem Statement | "Support teams look up four or five systems per request. Letting an AI act alone is risky: it can invent data or issue refunds. OpsPilot automates the research but keeps money decisions with a person." | Scroll the README |
| **0:30–1:40** Architecture | README diagrams | See **Architecture talk track** below | Point at the diagrams |
| **1:40–1:55** Demo: chat | Chat | "It talks like a person, in the customer's language." | Type **"Bạn có thể giúp tôi những gì"** |
| **1:55–3:05** Demo: main loop | Chat → Slack → Admin → Chat | "Refund request: the bot says it's *being reviewed*, never promised. The team gets a tagged report in Slack, severity HIGH. The manager approves… and the customer is told automatically, with the refund reference." | Click **2 · Refund request** → show Slack → Admin **Approve** → back to Chat, wait ~3 s |
| **3:05–3:30** Demo: safety | Chat + Admin | "Unknown order: it says *not found*, invents nothing, posts nothing to Slack. Same request twice: the second ticket is blocked as a duplicate." | Click **4 · Unknown order**; show the **Tickets** tab and the blocked ticket prepared earlier |
| **3:30–4:10** Testable | Editor + terminal + LangSmith | "Business rules are plain functions, not prompts, so they're testable. 237 tests run offline with a scripted fake model, with no OpenAI or Slack calls. Every run is traced in LangSmith with the prompt version." | `rules.py` → `uv run pytest` output → one trace |
| **4:10–5:00** Production | README, Production Improvements (AI agent, then Platform) | "For production, on the AI side: **memory** per customer so conversations carry over, a **knowledge base** to answer common policy questions with sources, **cost tracking** per request with budgets and a smaller model for small talk, and evaluations on every prompt change. On the platform side: durable storage so paused approvals survive restarts, real ticketing and payments, and login and roles for approvers." | Scroll the table |

## Architecture talk track (≈ 70 s)

### 1. The big picture (≈ 15 s), System architecture diagram

> "Here's the whole system. Customers use the **chat**, the operations team uses the **Operation Admin** page, and there's also a **REST API**. All three go through one **agent service**, so there is a single place where the logic lives. Underneath is a LangGraph **workflow**, read-only **tools** over the order data, and three external services: **OpenAI** for reasoning, **Slack** for team alerts, and **LangSmith** for tracing."

Point top to bottom: users → interfaces → agent service → workflow → tools and data → external services.

### 2. One request through the workflow (≈ 35 s), Agent workflow image

> "Each request goes through seven steps.
> **Input check** rejects empty or oversized messages.
> The **Investigate Agent** is the *only* step that uses AI. It reads the order, customer, tickets, and subscription, and returns a structured proposal: what happened, the evidence, and recommended actions.
> Then **guardrails**, plain code, decide for each action: run automatically, needs a human, or blocked.
> Safe actions run: a ticket and a reply draft, and the **ops team is notified** in Slack.
> If there's a refund, the workflow **pauses** here and waits for a manager; Approve or Reject resumes it.
> Dashed lines are early exits: missing information, an unknown order, or invalid AI output stop the run *before* anything happens."

Point at the purple box (AI), the green boxes (code), the orange box (human), then trace the dashed lines.

### 3. Why it is designed this way (≈ 20 s)

> "Three design choices.
> **One: the AI recommends, code decides.** The agent's output has no field for severity or approval, so it *can't* make those decisions, and the rules are testable functions, not prompt instructions.
> **Two: the AI can only read.** It never calls a tool that changes anything, and it can't look up an order ID the customer didn't write, so it can't invent data.
> **Three: money always needs a person.** Every refund pauses for approval, whatever the amount. When in doubt, the system does less, not more."

Speak slowly here: this is what Architecture (25%) and Guardrails (20%) are scored on. If the video runs long, shorten part 1 to one sentence ("all interfaces go through one service") and keep parts 2 and 3.

## Likely follow-up questions

| Question | Short answer |
|---|---|
| Why not one agent that does everything? | A free agent is hard to control and to test. Splitting AI reasoning from rule-based decisions makes each part testable and every decision explainable. |
| Why LangGraph? | The steps are explicit in code and in traces, and it has built-in **pause and resume** (`interrupt()` + checkpointer), which human approval needs. |
| What are the two guardrail layers? | Layer 1 runs **during** the investigation: no lookups of IDs the customer never wrote, and customer emails are hidden from the AI. Layer 2 runs **after** it: rules R1–R8 re-read the real data and decide. |
| What if the AI is wrong? | Invalid output stops the run with no action. A reply that promises a refund is replaced by a safe one (R8). An invented ID blocks every action (R7). |
| Can the customer get a wrong message? | The customer only sees replies that passed the content check. The approval-decision notice is a fixed template, not AI text, because it states a financial outcome. |
| How would you handle memory? | Today the chat re-sends earlier messages only while a question is open. In production: per-session state in a durable checkpointer with summarization, plus a long-term per-customer store (past issues, language) with retention limits. |
| How would you control cost? | Track tokens and cost per request and step in LangSmith with budgets and alerts; a smaller model for small talk and routing; a static system prompt so provider prompt caching applies; call limits already cap each run. |
| What about common questions like the refund policy? | A help-center knowledge base answered with retrieval and cited sources, cached for the most frequent questions, routed past the full investigation. |
| How do you test an AI system? | 237 offline tests with a scripted fake model: no OpenAI calls, no Slack posts. Real-model runs of the scenarios were checked manually. |

## Tips

- Use the sidebar scenario buttons for operational cases to avoid typos; type the small-talk message by hand.
- Each AI reply takes about 5–10 seconds: keep talking ("it's now looking up the order, the customer, and past tickets…") or cut the wait when editing.
- Leave Scenarios 3, 5, 6 and the Reject flow out of the video; the README covers them.
- Reply drafts for orders are in English even when the customer writes Vietnamese, on purpose: the content check covers English. Mention it as an improvement if asked.
- If the AI answers oddly, say so: "this is why the guardrails exist". Nothing unsafe can run.
