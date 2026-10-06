"""Thin HTTP adapter over ``src.agents.service``. No business logic, LLM calls, or tool calls here."""

from fastapi import APIRouter

from src.agents.service import run_agent
from src.api.schemas import AnalyzeRequest, ErrorEnvelope
from src.common.schemas import AnalyzeResponse

health_router = APIRouter(tags=["health"])
agent_router = APIRouter(prefix="/api/v1", tags=["agent"])


@health_router.get("/healthz", summary="Liveness check")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@agent_router.post(
    "/agent/analyze",
    response_model=AnalyzeResponse,
    summary="Analyze a customer request",
    description=(
        "Runs the OpsPilot pipeline on one customer message. Every business outcome is a 200 with a `status`: "
        "`completed`, `awaiting_approval` (a refund waits for a human; decide it in the demo UI), "
        "`needs_more_info` (reply with the answer and the earlier messages in `history`), `not_found`, or `error`."
    ),
    responses={500: {"model": ErrorEnvelope, "description": "Unexpected failure; no action was taken."}},
)
def analyze(body: AnalyzeRequest) -> AnalyzeResponse:  # sync: FastAPI runs it in a threadpool
    return run_agent(body.message, body.history)
