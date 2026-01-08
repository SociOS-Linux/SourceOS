# semantic.search — Contract Only

This package defines contracts for a semantic search capability:
- triRPC service surface (rpc/semantic.search.v0.yaml)
- topic taxonomy for event bus integration (topics/*.yaml)
- JSON Schemas for payload validation (schemas/*.json)
- a local validator (tools/validate_package.py)

## Non-goals
This package does **not** ship any runtime implementation.
Implementations live in separate packages and MUST:
1) enforce a policy guard (default deny)
2) emit governance evidence events
3) speak triRPC for all method surfaces

## Optional backends
Implementations MAY provide:
- Lexical inverted index (e.g., Xapian)
- Vector ANN index (e.g., FAISS/HNSW)
- Symbolic graph store (e.g., AtomSpace)

But contract conformance does not require any backend beyond the triRPC surface.
