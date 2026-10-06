"""FastAPI entry point: ``uv run uvicorn src.main:app --reload``."""

from fastapi import FastAPI

from src.config.settings import get_settings
from src.utils.logging import configure_logging


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(title="OpsPilot", version="0.1.0", summary="AI operations automation agent (demo)")

    @app.get("/healthz", tags=["health"], summary="Liveness check")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
