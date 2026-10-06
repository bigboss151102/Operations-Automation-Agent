"""FastAPI entry point: ``uv run uvicorn src.main:app --reload`` (docs at /docs)."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.api.routes import agent_router, health_router
from src.api.schemas import ErrorBody, ErrorEnvelope
from src.config.settings import get_settings
from src.utils.logging import configure_logging, get_logger, get_request_id

_log = get_logger("api")


def _unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    _log.exception("api_unhandled_error path=%s", request.url.path, exc_info=exc)
    request_id = get_request_id()
    body = ErrorEnvelope(
        error=ErrorBody(
            code="internal_error",
            message="The request could not be processed. No action was taken.",
            request_id=None if request_id == "-" else request_id,
        )
    )
    return JSONResponse(status_code=500, content=body.model_dump())


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="OpsPilot",
        version="0.1.0",
        summary="AI operations agent: investigates support requests, applies deterministic guardrails, "
        "and routes refunds to human approval.",
    )
    app.include_router(health_router)
    app.include_router(agent_router)
    app.add_exception_handler(Exception, _unexpected_error)
    return app


app = create_app()
