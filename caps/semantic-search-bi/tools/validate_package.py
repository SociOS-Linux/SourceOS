#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import json
import sys

def ok(msg: str) -> None:
    print("OK:", msg)

def fail(msg: str) -> None:
    print("ERR:", msg, file=sys.stderr)
    sys.exit(2)

def read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except Exception as e:
        fail(f"unable to read {p}: {e}")
        raise

def try_parse_yaml(p: Path) -> None:
    # YAML parse is optional: we attempt it if PyYAML exists; otherwise we do presence/non-empty checks.
    s = read_text(p).strip()
    if not s:
        fail(f"{p} is empty")
    try:
        import yaml  # type: ignore
        yaml.safe_load(s)
        ok(f"yaml parses: {p.as_posix()}")
    except ModuleNotFoundError:
        ok(f"yaml present (PyYAML not installed; parse skipped): {p.as_posix()}")
    except Exception as e:
        fail(f"yaml parse failed for {p}: {e}")

def parse_json_schema(p: Path) -> None:
    try:
        obj = json.loads(read_text(p))
    except Exception as e:
        fail(f"json parse failed for {p}: {e}")
    if "$schema" not in obj or "type" not in obj:
        fail(f"{p} does not look like a JSON Schema (missing $schema/type)")
    ok(f"json schema parses: {p.as_posix()}")

def main() -> None:
    # Locate package root relative to this script so it can be run from anywhere.
    here = Path(__file__).resolve()
    pkg = here.parent.parent

    required_dirs = ["capd", "docs", "rpc", "schemas", "tools", "topics"]
    for d in required_dirs:
        if not (pkg / d).is_dir():
            fail(f"missing dir: {d}")

    ok("package structure looks sane")

    capd = pkg / "capd" / "capability.yaml"
    if not capd.exists():
        fail("missing capd/capability.yaml")
    try_parse_yaml(capd)

    # Minimal semantic checks on capd (only if YAML parsing available)
    try:
        import yaml  # type: ignore
        cap = yaml.safe_load(read_text(capd))
        capinfo = (cap or {}).get("capability", {})
        if capinfo.get("kind") != "contract-only":
            fail("capability.kind must be 'contract-only'")
        if not capinfo.get("name") or not capinfo.get("version"):
            fail("capability.name and capability.version are required")
        req = (cap or {}).get("requires", {})
        for k in ("trirpc_bus", "policy_guard", "evidence_emission"):
            if req.get(k) is not True:
                fail(f"requires.{k} must be true")
        ok("capd semantics validated")
    except ModuleNotFoundError:
        ok("capd semantic validation skipped (PyYAML not installed)")
    except Exception as e:
        fail(f"capd semantic validation failed: {e}")

    rpc = pkg / "rpc" / "semantic.search.v0.yaml"
    if not rpc.exists():
        fail("missing rpc/semantic.search.v0.yaml")
    try_parse_yaml(rpc)

    topics = pkg / "topics" / "semantic.search.topics.v0.yaml"
    if not topics.exists():
        fail("missing topics/semantic.search.topics.v0.yaml")
    try_parse_yaml(topics)

    schemas_dir = pkg / "schemas"
    schemas = sorted(schemas_dir.glob("*.schema.json"))
    if not schemas:
        fail("no schemas/*.schema.json found")
    for s in schemas:
        parse_json_schema(s)

    ok("capability package validates")

if __name__ == "__main__":
    main()
