# Loom Demo Script (3–5 minutes)

Goal (spec §30): in a few minutes the reviewer should see an agent that reasons about operational data, uses tools, recommends actions, runs safe actions, and **stops** when an action is risky or uncertain.

## Before recording

```bash
uv run python -m streamlit run src/web/app.py
```

- Open the UI, and in another tab, the LangSmith project (`LANGSMITH_PROJECT`, default `opspilot-demo`).
- Click **Reset demo data** in the sidebar so ticket and approval IDs start fresh.
- Have `src/guardrails/rules.py` and `README.md` (architecture diagram) open in the editor.

## 1. Problem and architecture (≈ 30 s)

- "Support teams triage requests by hand. Letting an LLM act on its own is risky: it can invent orders, issue refunds, or promise things to customers."
- Show the README diagram: "Only one step uses the LLM: it investigates with **read-only** tools and recommends. Deterministic guardrails decide what may run. Refunds always wait for a human, and nothing is ever sent to a customer."

## 2. Scenarios in Streamlit (≈ 2.5 min)

| Order | Click | Point out |
|---|---|---|
| 1 | **1 · Delayed order** | MEDIUM; evidence comes from the data ("2 days late"); ticket, ops alert, and draft all ran **automatically** |
| 2 | **2 · Refund request** | HIGH; the decisions table shows `issue_refund` → ⏸️ human approval (`refund_requires_approval`); draft says the refund "is being reviewed" and is labelled *not sent*. **Click Approve live**; the simulated refund `RFD-…` appears in Executed actions |
| 3 | **3 · Existing ticket** | `create_support_ticket` → ⛔ blocked (`duplicate_ticket`, TCK-2001); the ops alert still goes out with "Follow up on existing ticket TCK-2001" |
| 4 | **4 · Unknown order** | Not found; no invented data; no actions |
| 5 | **5 · Missing order ID** | The agent **asks** for the order ID in its own words; no tool or action ran. Reply "It's ORD-1007." to show it continues with full context |
| 6 | **6 · High-value refund** | CRITICAL ($1,200); refund still needs approval; ticket and alert escalated to `critical` |

## 3. Under the hood (≈ 1 min)

- LangSmith: open the latest `opspilot` trace. Show the node tree (`validate_input → investigate → guardrails → execute_actions → human_approval`), the read tools inside `investigator`, the separate `guardrails.evaluate` span, and the `request_id` / `prompt_versions` metadata.
- Editor: scroll `src/guardrails/rules.py`, showing plain functions with rule IDs (R1–R7), no LLM.
- Mention the two guardrail layers: middleware blocks guessed IDs **during** the investigation; rules decide **after** it.

## 4. Limitations and production path (≈ 30 s)

- "Data and actions are simulated, approvals live in memory, and there is no auth yet."
- "For production: a durable checkpointer and approval queue, real ticketing/Slack/payment integrations with idempotency keys, RBAC on approvals, an audit log, and LangSmith evals gating every prompt change." (See README §8.)
