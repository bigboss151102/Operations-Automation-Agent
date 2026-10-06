# Phase 1 — Setup & Foundation

**Goal:** an installable, importable project skeleton with settings, logging, and a test harness, so every later phase only adds features.

**Depends on:** nothing · **Estimate:** 20 min · **Skills:** `python-engineering`, `code-quality`, `logging-observability`

## Deliverables

| File | Content |
|---|---|
| `pyproject.toml` | Dependencies, pytest and ruff config |
| `src/__init__.py` + `__init__.py` in every subpackage | Make `src.*` importable |
| `src/guardrails/`, `src/repositories/`, `src/common/schemas/` | New packages (in spec §19, not yet on disk) |
| `src/config/settings.py` | `Settings`, `get_settings()`, `SRC_DIR`, `ENV_FILE`, `today()` helper |
| `src/utils/logging.py` | `configure_logging()`, `request_id` ContextVar, `log_event()` |
| `src/utils/errors.py` | `AppError`, `DataError`, `LLMError` |
| `src/.env/.env.example` | Template from spec §20.1 |
| `src/main.py` | Replace placeholder: `create_app()` with `GET /healthz` only |
| `test/conftest.py` | Test env vars set before importing `src` |
| `test/test_settings.py` | Smoke test |

## Tasks

- [ ] Install dependencies:
  ```bash
  uv add langchain langchain-openai langgraph langsmith streamlit fastapi uvicorn pydantic-settings python-dotenv pyyaml
  uv add --dev pytest httpx ruff mypy
  ```
- [ ] `pyproject.toml`: set `description`, add `[tool.pytest.ini_options]` (`testpaths = ["test"]`) and `[tool.ruff]` (see the `code-quality` skill).
- [ ] Create the `__init__.py` files: `src/`, `agents/`, `api/`, `common/`, `common/schemas/`, `config/`, `guardrails/`, `llm/`, `memory/`, `prompts/`, `repositories/`, `tools/`, `utils/`, `web/`.
- [ ] `settings.py` as in the `python-engineering` skill. Fields: `env`, `openai_api_key`, `openai_model`, `llm_timeout_s`, `high_value_threshold`, `reference_date`, `data_dir`, `log_level`. Add `today(settings) -> date` (`reference_date or date.today()`).
- [ ] `logging.py`:
  - format `[%(levelname)s] request_id=<id> %(message)s`
  - `log_event(event, **fields)` renders `event=<e> k=v`
  - `set_request_id()` / `get_request_id()` via `ContextVar`
- [ ] `src/.env/.env.example`:
  ```text
  OPENAI_API_KEY=
  OPENAI_MODEL=
  LANGSMITH_TRACING=true
  LANGSMITH_API_KEY=
  LANGSMITH_PROJECT=opspilot-demo
  HIGH_VALUE_THRESHOLD=500
  REFERENCE_DATE=2026-10-10
  LOG_LEVEL=INFO
  ```
- [ ] Fill in your local `src/.env/.env` (real key + model). Never commit it.
- [ ] `test/conftest.py`: at module top, set `os.environ` defaults (`OPENAI_API_KEY=test`, `OPENAI_MODEL=test-model`, `LANGSMITH_TRACING=false`, `REFERENCE_DATE=2026-10-10`) before any `src` import. Clear the `get_settings` cache between tests.

## Acceptance criteria

- `uv run pytest` passes `test_settings.py`: settings load, `today()` returns the reference date, and `ENV_FILE` points to `src/.env/.env` regardless of cwd.
- `uv run uvicorn src.main:app` starts, and `curl localhost:8000/healthz` returns `{"status": "ok"}`.
- `uv run ruff check .` is clean.
- `git status` shows `src/.env/.env.example` as trackable and `src/.env/.env` as ignored.

## Out of scope

Agent and business logic, data files, the UI.
