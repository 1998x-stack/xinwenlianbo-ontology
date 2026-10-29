#!/usr/bin/env python3
"""Opt-in offline embedding export for B3 semantic event recall.

Requires optional sentence-transformers. No model downloads unless explicitly
allowed. Keep vectors outside Git, record the exact source and model revision.
"""

import argparse
import json
import os
import re
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from db.semantic_recall_b3 import _validate_vectors, input_sha256
from db.event_clustering_v3 import parse_articles


def make_text(row):
    """Fixed title + excerpt template. Use one identical recipe per evaluation."""
    title = row["title"].strip()
    excerpt = (row.get("excerpt") or "").strip()
    # Excerpts may be model-generated summaries, not verified source evidence.
    return f"标题：{title}\n内容摘要：{excerpt[:240]}"


def build_model_vectors(rows, *, model_name, revision, batch_size=16,
                        allow_network=False, device="cpu"):
    if not allow_network:
        os.environ["HF_HUB_OFFLINE"] = "1"
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError(
            "Install optional dependency: python -m pip install sentence-transformers"
        ) from exc
    model = SentenceTransformer(model_name, revision=revision, device=device,
                                trust_remote_code=False)
    ids = [item["news_id"] for item in rows]
    output = model.encode(
        [make_text(row) for row in rows], batch_size=batch_size,
        show_progress_bar=False, normalize_embeddings=True,
    )
    vectors = {nid: vec.tolist() if hasattr(vec, "tolist") else list(vec)
               for nid, vec in zip(ids, output)}
    validated, dim = _validate_vectors(parse_articles(rows), vectors)
    return {nid: list(vec) for nid, vec in validated.items()}, dim


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, required=True, help="Exact input JSONL")
    p.add_argument("--output", type=Path, required=True, help="Versioned vectors JSON")
    p.add_argument("--model", default="BAAI/bge-small-zh-v1.5")
    p.add_argument("--revision", required=True, help="Pinned model revision / commit")
    p.add_argument("--batch-size", type=int, default=16)
    p.add_argument("--device", default="cpu")
    p.add_argument("--allow-network", action="store_true")
    args = p.parse_args()
    if args.input.resolve() == args.output.resolve():
        p.error("refusing to replace input data")
    if args.batch_size < 1:
        p.error("batch-size must be positive")
    if not re.fullmatch(r"[0-9a-fA-F]{40}", args.revision):
        p.error("revision must be an immutable 40-character model commit SHA")
    with args.input.open(encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh if line.strip()]
    parse_articles(rows)
    vectors, dim = build_model_vectors(
        rows, model_name=args.model, revision=args.revision,
        batch_size=args.batch_size, allow_network=args.allow_network, device=args.device,
    )
    payload = {
        "format_version": 1,
        "model_id": args.model,
        "revision": args.revision,
        "input_sha256": input_sha256(args.input),
        "text_template": "title_plus_excerpt_240:v1",
        "dimension": dim,
        "vectors": vectors,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(args.output)
    print(json.dumps(
        {"items": len(vectors), "dimension": dim, "input_sha256": payload["input_sha256"],
         "model_id": args.model, "revision": args.revision, "output": str(args.output)},
        ensure_ascii=False,
    ))


if __name__ == "__main__":
    main()
