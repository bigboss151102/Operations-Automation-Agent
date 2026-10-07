# Loom Demo Script (3–5 minutes)

Goal (spec §30): in a few minutes the reviewer should see an agent that reasons about operational data, uses tools, recommends actions, runs safe actions, and **stops** when an action is risky or uncertain.

## Before recording

```bash
uv run python -m streamlit run src/web/app.py
```

- Open **three windows** side by side:
  1. the Streamlit **Chat** page (the customer);
  2. the Streamlit **Operation Admin** page in a second tab (the operations team);
  3. the Slack channel (`#operations-alerts`).
- Keep LangSmith (`opspilot-demo`) open in another tab.
- On Operation Admin, click **Reset demo data** so ticket and approval IDs start fresh.
- Have `src/guardrails/rules.py` and the README architecture diagram open in the editor.

## 1. Problem and architecture (≈ 30 s)

- "Support teams triage requests by hand. Letting an LLM act on its own is risky: it can invent orders, issue refunds, or promise things to customers."
- Show the README diagram: "Only one step uses the LLM. It investigates with **read-only** tools and recommends. Deterministic guardrails decide what may run, every case is reported to the team in Slack, and refunds always wait for a human."

## 2. The customer chat → Slack → admin loop (≈ 2.5 min)

| Order | Do | Point out |
|---|---|---|
| 1 | Chat: **2 · Refund request** | The bot replies like a person; the refund is "being reviewed", never promised. **Switch to Slack**: a tagged 🟠 HIGH report with evidence, guardrail decisions (`issue_refund` → ⏸️ human approval), the executed ticket, and the pending approval |
| 2 | Operation Admin: open the case → **Approve** | The simulated refund `RFD-…` appears in Executed actions. **Switch to Slack**: "✅ Refund approved…" in the thread. **Switch to Chat**: within ~3 s the bot tells the customer the refund was approved, with the `RFD-…` reference |
| 3 | Chat: **3 · Existing ticket** | Slack/Admin: `create_support_ticket` → ⛔ blocked (`duplicate_ticket`, TCK-2001); the report asks the team to follow up on the existing ticket |
| 4 | Chat: **4 · Unknown order** | The bot says it can't find ORD-9999; no invented data; **nothing posted to Slack** |
| 5 | Chat: **5 · Missing order ID** | The bot **asks** for the order ID in its own words; no tool ran, no Slack post. Reply "It's ORD-1007." → it continues with full context |
| 6 | Chat: **6 · High-value refund** | Slack: 🔴 CRITICAL ($1,200), ticket/alert escalated to critical; the refund still waits in Admin |

## 3. Under the hood (≈ 1 min)

- LangSmith: open the latest `opspilot` trace. Show the node tree (`validate_input → investigate → guardrails → execute_actions → notify_operations → human_approval`), the read tools inside `investigator`, the separate `guardrails.evaluate` span, and the `request_id` / `prompt_versions` metadata.
- Editor: scroll `src/guardrails/rules.py`, showing plain functions with rule IDs (R1–R7), no LLM.
- Mention the two guardrail layers: middleware blocks guessed IDs **during** the investigation; rules decide **after** it. The reply shown to the customer passes the R8 content policy.

## 4. Limitations and production path (≈ 30 s)

- "Data and actions are simulated except Slack; approvals and cases live in memory; there is no auth yet."
- "For production: a durable checkpointer and approval queue, real ticketing/payment integrations with idempotency keys, RBAC on the admin page, an audit log, and LangSmith evals gating every prompt change." (See README §8.)
