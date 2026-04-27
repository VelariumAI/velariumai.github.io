"""FastAPI server assembly."""

from __future__ import annotations

from fastapi import FastAPI

from vcse.api.config import API_VERSION
from vcse.api.middleware import install_error_handlers
from vcse.api.routes import router


def create_app() -> FastAPI:
    app = FastAPI(title="VCSE API Adapter", version=API_VERSION)
    app.include_router(router)
    install_error_handlers(app)
    return app
