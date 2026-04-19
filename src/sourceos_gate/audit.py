"""Append-only NDJSON audit log writer."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .timeutil import now_iso_utc


@dataclass(frozen=True)
class AuditLog:
    root: Path

    def path_for(self, stream: str) -> Path:
        # Store by day for easy rotation.
        day = now_iso_utc()[:10]
        return self.root / "audit" / "events" / day / f"{stream}.ndjson"

    def append(self, stream: str, record: dict) -> None:
        p = self.path_for(stream)
        p.parent.mkdir(parents=True, exist_ok=True)
        rec = dict(record)
        rec.setdefault("ts", now_iso_utc())
        line = json.dumps(rec, sort_keys=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
