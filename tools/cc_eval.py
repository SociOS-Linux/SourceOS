#!/usr/bin/env python3
import argparse, hashlib, json, lzma, time, zlib

def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def read_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()

def compress_sizes(b: bytes):
    return {"zlib": len(zlib.compress(b)), "lzma": len(lzma.compress(b))}

def novelty_and_redundancy(baseline: bytes, artifact: bytes):
    sB = compress_sizes(baseline)
    sX = compress_sizes(artifact)
    sBX = compress_sizes(baseline + b"\n" + artifact)

    novelty_terms = []
    redundancy_terms = []
    detail = {}

    for k in sorted(sB.keys()):
        nov = (sB[k] + sX[k] - sBX[k])
        novelty_terms.append(nov)

        raw_ratio = sX[k] / max(1, len(artifact))
        red = 1.0 / max(1e-12, raw_ratio)
        redundancy_terms.append(red)

        detail[k] = {
            "compressed_baseline": sB[k],
            "compressed_artifact": sX[k],
            "compressed_concat": sBX[k],
            "novelty_term": nov,
            "redundancy_term": red,
        }

    novelty = float(sum(novelty_terms) / max(1, len(novelty_terms)))
    redundancy = float(sum(redundancy_terms) / max(1, len(redundancy_terms)))

    estimator_set = {
        "estimators": ["zlib", "lzma"],
        "detail": detail,
        "definition": {
            "novelty": "avg(|C(B)| + |C(X)| - |C(B+X)|) over compressors",
            "redundancy": "avg(1/(|C(X)|/|X|)) over compressors",
        },
    }
    return novelty, redundancy, estimator_set

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--producer", default="unknown")
    ap.add_argument("--intent", default="")
    args = ap.parse_args()

    artifact = read_bytes(args.artifact)
    baseline = read_bytes(args.baseline)

    novelty, redundancy, estimator_set = novelty_and_redundancy(baseline, artifact)

    out = {
        "version": 0,
        "module": "compression-commons",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "artifact": {
            "artifact_id": sha256_bytes(artifact),
            "content_hash": sha256_bytes(artifact),
            "producer": args.producer,
            "volume": float(len(artifact)),
            "declared_intent": (args.intent or None),
        },
        "baseline": {
            "snapshot_id": sha256_bytes(baseline),
            "corpus_root_hash": sha256_bytes(baseline),
        },
        "metrics": {
            "metric_id": sha256_bytes((sha256_bytes(baseline) + sha256_bytes(artifact)).encode("utf-8")),
            "novelty": novelty,
            "redundancy": redundancy,
            "estimator_set": estimator_set,
        },
    }

    print(json.dumps(out, indent=2, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
