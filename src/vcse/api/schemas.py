"""FastAPI/Pydantic schemas for the VCSE API adapter."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Message(BaseModel):
    role: str
    content: str | dict[str, Any] | list[Any]


class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str = "vcse-vrm-1.9"
    messages: list[Message] = Field(default_factory=list)
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None


class ResponsesRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str = "vcse-vrm-1.9"
    input: Any | None = None
    messages: list[Message] = Field(default_factory=list)
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ResponseMessage(BaseModel):
    role: Literal["assistant"] = "assistant"
    content: str


class Choice(BaseModel):
    index: int = 0
    message: ResponseMessage
    finish_reason: Literal["stop"] = "stop"


class ChatCompletionResponse(BaseModel):
    id: str
    object: Literal["chat.completion"] = "chat.completion"
    choices: list[Choice]
    usage: Usage
    vcse_debug: dict[str, Any] | None = None


class ResponsesAPIResponse(BaseModel):
    id: str
    object: Literal["response"] = "response"
    output_text: str
    usage: Usage
    vcse_debug: dict[str, Any] | None = None
