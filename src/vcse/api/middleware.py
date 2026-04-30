"""API middleware and exception handlers."""

from __future__ import annotations

import asyncio
import logging
import uuid
from time import perf_counter

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from vcse.api.errors import APIError, error_payload
from vcse.perf import stage


_LOG = logging.getLogger("vcse.api")


def install_error_handlers(app: FastAPI, *, max_request_bytes: int = 1_000_000, timeout_seconds: float = 30.0) -> None:
    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = uuid.uuid4().hex
        request.state.request_id = request_id
        started = perf_counter()

        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > max_request_bytes:
                    return JSONResponse(
                        status_code=413,
                        content=error_payload(
                            "REQUEST_TOO_LARGE",
                            "Request body exceeds configured limit",
                            "REQUEST_TOO_LARGE",
                        ),
                        headers={"X-Request-ID": request_id},
                    )
            except ValueError:
                pass

        try:
            with stage("api.request"):
                response = await asyncio.wait_for(call_next(request), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            return JSONResponse(
                status_code=504,
                content=error_payload("REQUEST_TIMEOUT", "Request timed out", "REQUEST_TIMEOUT"),
                headers={"X-Request-ID": request_id},
            )

        duration_ms = (perf_counter() - started) * 1000
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time-ms"] = f"{duration_ms:.3f}"
        _LOG.info(
            "request complete",
            extra={
                "request_id": request_id,
                "path": request.url.path,
                "method": request.method,
                "status_code": getattr(response, "status_code", 200),
                "duration_ms": duration_ms,
            },
        )
        return response

    @app.exception_handler(APIError)
    async def handle_api_error(request: Request, exc: APIError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(exc.error_type, exc.message, exc.code),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content=error_payload("INVALID_REQUEST", "Malformed request payload", "INVALID_REQUEST"),
        )

    @app.exception_handler(Exception)
    async def handle_generic_error(request: Request, exc: Exception) -> JSONResponse:
        _LOG.exception(
            "unhandled api error",
            extra={
                "path": request.url.path,
                "method": request.method,
            },
        )
        return JSONResponse(
            status_code=500,
            content=error_payload("INTERNAL_ERROR", "Internal server error", "INTERNAL_ERROR"),
        )
