"""FastAPI server assembly."""

from __future__ import annotations

from fastapi import FastAPI

from vcse.api.config import API_VERSION
from vcse.api.middleware import install_error_handlers
from vcse.api.routes import router
from vcse.config import load_settings, Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    runtime_settings = settings or load_settings()
    app = FastAPI(title="VCSE API Adapter", version=API_VERSION)
    app.state.settings = runtime_settings
    app.include_router(router)
    install_error_handlers(
        app,
        max_request_bytes=runtime_settings.api_max_request_bytes,
        timeout_seconds=runtime_settings.api_timeout_seconds,
    )
    return app
