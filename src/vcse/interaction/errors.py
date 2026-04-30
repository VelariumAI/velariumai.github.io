"""Interaction layer errors."""


class InteractionError(Exception):
    """Base error for interaction layer."""


class ParseError(InteractionError):
    """Failed to parse input into frames."""

    def __init__(self, reason: str, status: str = "FAILED") -> None:
        super().__init__(reason)
        self.reason = reason
        self.status = status


class ClarificationError(InteractionError):
    """Cannot proceed without user clarification."""

    def __init__(self, request: "ClarificationRequest") -> None:
        super().__init__(request.user_message)
        self.request = request


# Forward reference for type checker
class ClarificationRequest:
    """Request for user clarification."""
    pass
