# OpsPilot — Implementation Plan Overview

Source of truth: `specs/specification.md`. Conventions: `CLAUDE.md` + `.claude/skills/`.

Total budget: **~3.5–4 hours** (spec §27: 2–4 h). Each phase ends with tests passing, `ruff` clean, and one commit.

## Phases

| # | Phase | File | Est. | Depends on | Status |
|---|---|---|---|---|---|
| 1 | Setup & foundation | [01-setup-foundation.md](01-setup-foundation.md) | 20 min | — | ✅ |
| 2 | Sample data & scenarios | [02-sample-data-scenarios.md](02-sample-data-scenarios.md) | 25 min | 1 | ✅ |
| 3 | Tools & stores | [03-tools-and-stores.md](03-tools-and-stores.md) | 30 min | 2 | ✅ |
| 4 | Guardrails & severity | [04-guardrails-severity.md](04-guardrails-severity.md) | 35 min | 3 | ✅ |
| 5 | LLM investigator + guardrail middleware | [05-llm-investigator.md](05-llm-investigator.md) | 40 min | 3 | ✅ |
| 6 | Graph, service & human approval | [06-graph-service-hitl.md](06-graph-service-hitl.md) | 40 min | 4, 5 | ✅ |
| 7 | Streamlit UI & REST API | [07-ui-api.md](07-ui-api.md) | 30 min | 6 | ✅ |
| 8 | Observability, README & demo | [08-observability-readme-demo.md](08-observability-readme-demo.md) | 30 min | 7 | ☐ |

Phases 4 and 5 are independent and can be done in either order.

```text
1 → 2 → 3 ─┬─→ 4 ─┬─→ 6 → 7 → 8
           └─→ 5 ─┘
```

## Decisions to confirm before Phase 2

These are proposals. The spec leaves them open, but guardrails and tests depend on them.

| ID | Decision | Proposal | Where |
|---|---|---|---|
| D1 ✅ | Scenario order IDs & reference date | **Confirmed.** `REFERENCE_DATE=2026-10-10`. Scenario 2 uses ORD-1007 with **no** open ticket. Scenario 3 uses **ORD-1008** with open ticket TCK-2001. Update spec §7 and §16 to match. | Phase 2 |
| D2 ✅ | Which actions need human approval | **Confirmed: only `issue_refund`.**<br>• Rule 2 (orders of $500 or more) adds no approval step. It sets ticket priority and notification severity to `critical`, and feeds CRITICAL severity.<br>• `send_customer_message` is removed: the agent only drafts, so Rule 3 holds because sending is impossible (proposed → blocked).<br>• README must explain this interpretation of spec Rule 2. | Phases 3, 4, 6 |
| D3 ✅ | Severity rules & precedence | **Confirmed.** Deterministic table in Phase 4. When several rules match, the **highest** severity wins. Severity drives display, notification severity, and ticket priority, not approval. | Phase 4 |
| D4 ✅ | Customer response draft | **Confirmed (revised).** The **LLM writes** `customer_response_draft`, following an example template in `src/prompts/customer_response_example.md` (injected into the system prompt). **Code enforces** a deterministic draft policy: no refund or compensation promises, no internal details. A violating draft is replaced by a safe fallback. The draft is never sent. | Phases 3, 4, 5 |
| D5 ✅ | No ID in the message | **Confirmed (revised).** The **LLM asks** the user for the specific missing information (`missing_fields` + `clarification_question`). **Code enforces**: `VerifiedIdMiddleware` blocks guessed lookups, and guardrail R5 forces `needs_more_info` and blocks all actions. The user's reply is sent with the conversation `history`. | Phases 4, 5, 6, 7 |

## Global definition of done

- [ ] All 8 spec tests (§23) pass, plus phase-specific tests: `uv run pytest`
- [ ] `uv run ruff check . && uv run ruff format --check .`
- [ ] Five required scenarios (+ optional high-value) work in Streamlit with a real OpenAI key
- [ ] LangSmith shows one trace per request with `request_id` metadata
- [ ] README has every section required by spec §25
- [ ] No secrets committed; `src/.env/.env.example` is committed
