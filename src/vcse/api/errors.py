"""API error models."""

from __future__ import annotations


class APIError(ValueError):
    def __init__(
        self,
        error_type: str,
        message: str,
        code: str,
        status_code: int = 400,
    ) -> None:
        super().__init__(f"{error_type}: {message}")
        self.error_type = error_type
        self.message = message
        self.code = code
        self.status_code = status_code


def error_payload(error_type: str, message: str, code: str) -> dict[str, dict[str, str]]:
    return {
        "error": {
            "type": error_type,
            "message": message,
            "code": code,
        }
    }
