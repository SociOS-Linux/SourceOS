"""Unix-socket JSON protocol for the egress gate daemon.

Protocol: one JSON object per line (NDJSON framing).

Request:
{
  "id": "<client request id>",
  "method": "health|snapshot|grant.install|prune|apply|verify",
  "params": { ... }
}

Response:
{
  "id": "<same id>",
  "ok": true|false,
  "result": {...} | null,
  "error": {"code": "...", "message": "..."} | null
}

Notes:
- Authentication is by socket filesystem permissions (deployment responsibility).
- We do not attempt network auth or remote access.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .errors import (
    BaselineMissingError,
    ExpiredGrantError,
    GateError,
    NftError,
    ReplayError,
    ValidationError,
)


@dataclass(frozen=True)
class RpcError:
    code: str
    message: str

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message}


def ok_response(req_id: str | None, result: Any) -> dict:
    return {"id": req_id, "ok": True, "result": result, "error": None}


def err_response(req_id: str | None, err: RpcError) -> dict:
    return {"id": req_id, "ok": False, "result": None, "error": err.to_dict()}


def map_error(e: Exception) -> RpcError:
    if isinstance(e, ReplayError):
        return RpcError("replay", str(e) or "replay detected")
    if isinstance(e, ExpiredGrantError):
        return RpcError("expired", str(e) or "grant expired")
    if isinstance(e, BaselineMissingError):
        return RpcError("baseline_missing", str(e) or "nft baseline missing")
    if isinstance(e, NftError):
        return RpcError("nft", str(e) or "nft error")
    if isinstance(e, ValidationError):
        return RpcError("invalid", str(e) or "invalid request")
    if isinstance(e, GateError):
        return RpcError("gate", str(e) or "gate error")
    return RpcError("internal", f"{type(e).__name__}: {e}")


def require_fields(obj: dict, fields: list[str]) -> None:
    for f in fields:
        if f not in obj:
            raise ValidationError(f"missing field: {f}")
