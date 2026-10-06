# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**OpsPilot**: a small demo AI agent for a customer-support/operations team (2–4 hour coding-challenge scope). It analyzes a customer request, investigates local sample data with tools, recommends actions, auto-runs safe internal ones (ticket, ops notification, reply draft), and sends **refunds, the only action that needs approval**, to a human. It never sends messages to customers; it only drafts them.

`specs/specification.md` is the source of truth for requirements, architecture, and scope. If a skill or habit conflicts with it, the spec wins. Demo scenarios (spec §16) are tied to the sample data in `data/` and `REFERENCE_DATE=2026-10-10`. Changing either can break scenarios and `test/test_data.py`.

Status: Phases 1–5 done (setup; sample data + shared schemas; repositories + tools; deterministic guardrails; LLM investigator in `src/agents/investigator.py` with prompts in `src/prompts/`). Agent features are built phase by phase following `plans/` (`plans/00-overview.md` tracks progress).

## Stack

Python 3.14 + uv · OpenAI via LangChain v1 (`create_agent`, `init_chat_model("openai:<model>")`) · LangGraph (outer pipeline, `interrupt()` for approval) · LangSmith tracing · Streamlit demo UI · thin FastAPI API · Pydantic v2 · pytest. Sample data is local JSON in `data/`, with no database.

## Commands

```bash
uv sync                                            # install deps from pyproject.toml
cp src/.env/.env.example src/.env/.env             # then set OPENAI_API_KEY, OPENAI_MODEL, LANGSMITH_*

uv run python -m streamlit run src/web/app.py      # demo UI (run from repo root)
uv run uvicorn src.main:app --reload               # REST API: POST /api/v1/agent/analyze

uv run pytest                                      # all tests
uv run pytest test/test_guardrails.py::test_name   # single test
```

Use `python -m streamlit`, not bare `streamlit`. The `-m` form puts the repo root on `sys.path`, so `import src...` works.

## Architecture

```text
validate_input → investigate → guardrails → execute_actions → human_approval → respond
    (code)      (LLM: create_agent)  (code)        (code)        (interrupt())     (code)
```

- **Only `investigate` uses the LLM.** It is a `create_agent` limited to **read-only tools** (`get_order`, `get_customer`, `get_support_tickets`, `get_subscription`), and it must return a Pydantic `AgentProposal` via `ToolStrategy`. If the output is invalid or a call limit is hit, the request ends with a safe error and no action runs.
- **Everything else is deterministic code.** `src/guardrails/` computes severity, applies the spec's Rules 1–7, and decides per action: auto, approval, or blocked. `AgentProposal` deliberately has no severity, risk, or approval fields.
- **Guardrails run in two layers** (spec §12.7):
  1. LangChain middleware inside the investigator: `VerifiedIdMiddleware` in `src/guardrails/middleware.py` blocks tool lookups of IDs the customer never wrote; `PIIMiddleware` redacts emails from tool results; call-limit middleware bounds the loop.
  2. The `guardrails` graph node, built from pure functions in `rules.py` / `severity.py`, makes the business decisions.

  Business rules never go into middleware: the LLM never calls action tools, and `HumanInTheLoopMiddleware` cannot express data-dependent rules.
- **The LLM never calls action tools.** `create_support_ticket`, `send_operations_notification`, `prepare_customer_response`, and `request_human_approval` are invoked only by graph nodes after the guardrails decide. All actions are simulated.
- **Human approval** uses `interrupt()` in the outer graph, with `InMemorySaver` and `thread_id = request_id`, and resumes via `Command(resume=...)`. Streamlit and FastAPI both call `src/agents/service.py` (`run_agent` / `resume_agent`). Neither embeds graph logic.
- **Layering:** `web`/`api` → `agents` → `llm` / `tools` / `guardrails` / `repositories` / `memory` / `prompts` → `common` / `config` / `utils`. `guardrails` and `tools` never import `llm`.
  - `common/schemas/` holds every Pydantic model or enum shared across layers (domain records, `AgentProposal`, `GuardrailDecision`, `AnalyzeResponse`). It contains no logic or I/O and imports nothing from `src`.
  - `repositories/` holds data access: the JSON `data_store` and the in-memory `action_store`.
  - `memory/` is agent memory only (the LangGraph checkpointer).

## Prompts

Every instruction sent to the LLM is a Markdown file in `src/prompts/<name>.md`, with YAML frontmatter (`name`, `version`, `description`, `variables`), loaded by `src/prompts/loader.py`. Don't put prompt text in `.py` files. Bump `version` on every edit. Details are in the `llm-engineering` skill.

## Gotchas

- `src/.env` is a **directory**: secrets are in `src/.env/.env`, and the template is `src/.env/.env.example`. `get_settings()` loads it with `load_dotenv(ENV_FILE)`, where `ENV_FILE` is built from `__file__`, not the cwd. This is required because LangChain and LangSmith read `OPENAI_API_KEY` / `LANGSMITH_*` from the process environment, and pydantic-settings alone does not export them.
- `.gitignore` ignores the whole `src/.env/` directory except `.env.example`, which must stay committed (spec deliverable).
- Code before `interrupt()` re-runs when the graph resumes. Keep it idempotent.
- `langgraph.prebuilt.create_react_agent` is legacy. Use `langchain.agents.create_agent`.
- `GenericFakeChatModel.bind_tools` raises `NotImplementedError`. Tests use `FakeChatModel` from `test/fakes.py`, which overrides it; script model turns with `fake_model(...)` and `tool_call(...)`. Tests never call OpenAI or LangSmith (`LANGSMITH_TRACING=false`).
- `.claude/` is gitignored, so project skills are not committed.

## Project skills

Load the matching skill from `.claude/skills/` before working in that area:

- `llm-engineering`: agent, prompts, tools, structured output, HITL, LangSmith, fake model
- `python-engineering`: layout, layering, settings / `src/.env/.env`, data stores, errors
- `api-design`: thin FastAPI layer and the shared `AnalyzeResponse` contract (status values)
- `testing`: the 8 required tests, fake model, interrupt/resume tests
- `logging-observability`: LangSmith run metadata + key=value decision-trail logs
- `code-quality`: ruff/mypy and the done checklist
