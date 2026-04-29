"""Source adapters for compiler inputs."""

from vcse.adapters.base import SourceAdapter
from vcse.adapters.registry import ADAPTERS, get_adapter

__all__ = ["SourceAdapter", "ADAPTERS", "get_adapter"]
