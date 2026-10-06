# Phase 8 — Observability, README & Demo

**Goal:** make the system explainable to a reviewer in a few minutes. That means verified LangSmith traces, a decision-trail log, a README covering spec §25, and a rehearsed Loom script.

**Depends on:** Phase 7 · **Estimate:** 30 min · **Skills:** `logging-observability`, `code-quality`

## Deliverables

| File | Content |
|---|---|
| `README.md` | All sections required by spec §25 |
| `docs/architecture.md` (optional) | Only if the README diagram gets too long |
| `plans/00-overview.md` | Status column updated |

## Tasks

### Observability check

- [ ] With `LANGSMITH_TRACING=true`, run scenarios 1–6. In LangSmith verify:
  - one trace per request named `opspilot`;
  - the node tree reads `validate_input → investigate (investigator → tools) → guardrails → execute_actions → human_approval → respond`;
  - `request_id` and `prompt_versions` appear in the metadata.
- [ ] Logs contain every spec §22 field (`request_id`, intent, tools called, severity, guardrail decisions with rule, executed actions, approval requests). No message text or secrets at INFO.
- [ ] Take 2–3 screenshots (trace tree, guardrail span) for the README/Loom.

### README (spec §25)

1. **Problem**: support/ops team, manual triage, risk of unsafe automation.
2. **Solution**: OpsPilot in one paragraph: LLM investigates, deterministic rules decide, humans approve risky actions.
3. **Architecture**: diagram (spec §25.3, adapted to the real node names), plus a "where things live" table (`src/agents`, `guardrails`, `tools`, `prompts`, …).
4. **Key design decisions**:
   - LLM vs deterministic rules split
   - only read tools for the LLM
   - guardrails re-read data
   - approval via `interrupt()`
   - prompts as versioned `.md`
   - no fabricated data
   - no external messages without approval
   - decisions D1–D5
5. **How to run**: exact commands (`uv sync`, copy `src/.env/.env.example`, Streamlit, API, pytest).
6. **Demo examples**: the scenario table with inputs and expected outcomes.
7. **Known limitations**: spec list, plus in-memory approvals/checkpointer, LangSmith traces contain request text (fictional data only), and a small evaluation set.
8. **Production improvements**: spec §26 list, mapped to concrete changes:
   - Postgres checkpointer
   - real ticketing/Slack integrations
   - RBAC
   - LangSmith datasets/evals on prompt changes
   - model fallback
   - PII redaction
   - idempotency keys
   - audit log

### Final quality gate

- [ ] `uv run ruff format --check . && uv run ruff check . && uv run pytest`
- [ ] Fresh-clone check: clone to a temp dir, `uv sync`, copy env, run Streamlit + one scenario.
- [ ] `git status`: no `src/.env/.env`; `src/.env/.env.example` present.
- [ ] Update `CLAUDE.md` "Status" (no longer scaffold-only).

### Loom script (3–5 min, spec §28 Principle 7)

1. 30 s: the problem + architecture diagram.
2. 2.5 min: Streamlit scenarios in order 1 → 2 (approve live) → 3 → 4 → 5 → 6.
3. 1 min: LangSmith trace and the `guardrails` rule names; open `src/guardrails/rules.py` briefly.
4. 30 s: limitations and production path.

## Acceptance criteria

The global definition of done in `00-overview.md` is fully checked.
