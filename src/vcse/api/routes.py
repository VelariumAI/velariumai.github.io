"""API route handlers."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from fastapi import APIRouter, Query

from vcse.api.config import API_VERSION, MODEL_ID, MODEL_OWNER
from vcse.api.errors import APIError
from vcse.api.schemas import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    Choice,
    ResponseMessage,
    ResponsesAPIResponse,
    ResponsesRequest,
    Usage,
)
from vcse.api.translator import translate_user_input

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": API_VERSION}


@router.get("/v1/models")
def models() -> list[dict[str, str]]:
    return [{"id": MODEL_ID, "object": "model", "owned_by": MODEL_OWNER}]


@router.post("/v1/chat/completions")
def chat_completions(
    request: ChatCompletionRequest,
    debug: bool = Query(False),
) -> ChatCompletionResponse:
    if request.model != MODEL_ID:
        raise APIError("INVALID_REQUEST", f"Unknown model: {request.model}", "MODEL_NOT_FOUND", 400)
    prompt = _extract_last_user_message(request.messages)
    translated = translate_user_input(prompt, enable_debug=debug)
    completion_id = _stable_id("chatcmpl", request.model, prompt, translated.content)
    return ChatCompletionResponse(
        id=completion_id,
        choices=[
            Choice(
                index=0,
                message=ResponseMessage(role="assistant", content=translated.content),
                finish_reason="stop",
            )
        ],
        usage=Usage(prompt_tokens=0, completion_tokens=0, total_tokens=0),
        vcse_debug=translated.debug if debug else None,
    )


@router.post("/v1/responses")
def responses(
    request: ResponsesRequest,
    debug: bool = Query(False),
) -> ResponsesAPIResponse:
    if request.model != MODEL_ID:
        raise APIError("INVALID_REQUEST", f"Unknown model: {request.model}", "MODEL_NOT_FOUND", 400)
    prompt = _extract_prompt_from_responses_request(request)
    translated = translate_user_input(prompt, enable_debug=debug)
    response_id = _stable_id("resp", request.model, prompt, translated.content)
    return ResponsesAPIResponse(
        id=response_id,
        output_text=translated.content,
        usage=Usage(prompt_tokens=0, completion_tokens=0, total_tokens=0),
        vcse_debug=translated.debug if debug else None,
    )


def _extract_last_user_message(messages: list[Any]) -> str:
    if not messages:
        raise APIError("INVALID_REQUEST", "messages must contain at least one user message", "INVALID_MESSAGES", 400)
    for item in reversed(messages):
        role = getattr(item, "role", None)
        if role == "user":
            content = getattr(item, "content", "")
            if isinstance(content, str):
                return content
            return json.dumps(content, sort_keys=True)
    raise APIError("INVALID_REQUEST", "No user message provided", "INVALID_MESSAGES", 400)


def _extract_prompt_from_responses_request(request: ResponsesRequest) -> str:
    if request.messages:
        return _extract_last_user_message(request.messages)
    if request.input is None:
        raise APIError("INVALID_REQUEST", "responses request requires input or messages", "INVALID_INPUT", 400)
    if isinstance(request.input, str):
        return request.input
    return json.dumps(request.input, sort_keys=True)


def _stable_id(prefix: str, model: str, prompt: str, content: str) -> str:
    digest = hashlib.sha1(f"{model}|{prompt}|{content}".encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{digest}"
