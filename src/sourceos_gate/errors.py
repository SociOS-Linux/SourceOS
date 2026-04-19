"""Error types for SourceOS gate components."""

from __future__ import annotations


class GateError(Exception):
    """Base error for gate operations."""


class ReplayError(GateError):
    """Raised when a token+nonce pair has already been seen."""


class ExpiredGrantError(GateError):
    """Raised when a grant has expired."""


class BaselineMissingError(GateError):
    """Raised when nft baseline objects are missing."""


class PermissionError(GateError):
    """Raised when operation requires elevated privileges."""


class NftError(GateError):
    """Raised when nft operations fail."""


class ValidationError(GateError):
    """Raised when request payload is invalid."""
