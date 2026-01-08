# Semantic Search Capability Contract (Contract-Only)

This directory explains the **Semantic Search** capability contract in plain English.

## What this is
This package defines a **contract-only capability**: it specifies *interfaces* (schemas, RPC surface, topics, governance hooks),
but **does not ship an implementation**. It’s like a “power outlet standard” — vendors can build compatible devices, but the
contract itself isn’t the device.

## Why we do it this way
We want capabilities that are:
- **Composable**: other capabilities can depend on this one without importing a specific engine.
- **Auditable**: every call can be policy-guarded and emits evidence events.
- **Replaceable**: Xapian/FAISS/AtomSpace/etc. are optional implementations behind the same stable interface.
- **Linux-first** and open-source-only.

## What’s in the contract package
The capability contract is defined by these folders:

- `capd/` (if present): Capability descriptor (identity, version, requirements, compatibility rules).
- `rpc/`: triRPC method surface (what methods exist, request/response schema bindings).
- `schemas/`: JSON Schemas for requests, responses, and evidence events.
- `topics/`: PubSub topics (events, indexing progress, query telemetry).
- `tools/validate_package.py`: A local validator that ensures the contract package is structurally sane.

## Governance requirements (non-negotiable)
Every implementation of this contract MUST:
1) Enforce **policy guards** (default deny) for ingest/query/delete.
2) Emit **evidence events** for every meaningful action (ingest accepted/rejected, query executed, results delivered, deletes).
3) Support **quota + identity hooks** (caller identity / tenant / namespace).
4) Be compatible with triRPC request/response schema validation.

## How to read the contract
Start at:
- `rpc/semantic.search.v0.yaml` — the canonical RPC surface
- `schemas/query_request.schema.json` and `schemas/query_response.schema.json`
- `schemas/evidence_event.schema.json` — what we log as auditable evidence
- `topics/semantic.search.topics.v0.yaml` — pubsub surfaces

## “BI” naming note
If the folder is `caps/semantic-search-bi`, “bi” should mean *behavioral indexing* (or whatever we intended),
not “business intelligence”. If that’s not what we mean, we should rename now while it’s early.

