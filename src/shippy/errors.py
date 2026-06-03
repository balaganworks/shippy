"""Domain errors raised by Shippy."""

from __future__ import annotations


class ShippyError(RuntimeError):
    """Base error for user-facing Shippy failures."""


class CommandError(ShippyError):
    """Raised when a required external command fails."""


class ConfigError(ShippyError):
    """Raised when Shippy configuration is missing or invalid."""


class OllamaError(ShippyError):
    """Raised when Ollama cannot generate a response."""
