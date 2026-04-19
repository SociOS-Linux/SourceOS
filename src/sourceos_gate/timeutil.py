"""Time helpers."""

from __future__ import annotations

import time


def now_epoch() -> int:
    return int(time.time())


def now_iso_utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
