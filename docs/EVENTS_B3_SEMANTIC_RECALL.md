# Stage B3 — Semantic Event Recall + Event-Centroid Shadow Evaluation

> Depends on PR #3 (S03/S05 foundation). B3 is a **stacked Draft PR** and a
> **read-only experimental preview**. No existing production event is changed.

## Goal

B0 topic connected components over-merge (historical largest cluster >85%
of the corpus). B2 constrained clustering is conservative (336 singleton
clusters out of 386 items). On the synthetic gold fixture the S03 candidate
blocker recovers only 7/10 gold-positive pairs, motivating a separate semantic
candidate branch. This is a *synthetic* diagnostic, not a real-world recall.

### Architecture

    historical JSONL --------------┐
      (exact input file hash)       │
           |                        |
      optional local encoder        |
      (pinned model revision)       |
           |                        v
       vectors.json       B2 baseline (unmodified)
           |
        validate IDs, dimension, finiteness,
        source hash and model metadata
           |
       cosine top-k (temporal window)
           |
       action + location + org compatibility
           |
      union B2 blocking and B3 semantic candidates
           |
       event-centroid assignment:
          - has candidate edge to cluster
          - no pair contradiction to any member
          - minimum member cosine
          - centroid cosine / max time span
           |
       independent evaluation: candidate recall,
          cluster Pairwise / B-Cubed if gold exists,
          reviewed-pair comparison and error audit
           |
       SHADOW JSON ONLY; NO DB/EXPORT MUTATION

The first version intentionally uses O(N^2) exact cosine comparisons and
bounded local windows; do not deploy on multiyear data without benchmarking
or adding a vector index. B3 is heuristic, **not** a trained classifier.
Cosine is not calibrated probability. An event center in this module is a
dynamic vector average, not a durable EventId.

## Optional embedding model

A practical starting baseline is the Chinese embedding model
`BAAI/bge-small-zh-v1.5` (512 dimensions). The model is optional: CI
runs entirely with mock vectors, not downloaded weights. Compare against
a stronger multilingual model later if coverage demands it.

Install locally, obtain a specific model commit/revision, and explicitly
allow model downloading when required:

    python -m pip install sentence-transformers
    python eval/build_embeddings_b3.py \
      --input data/news_items.jsonl \
      --output /tmp/xwl-embeddings.json \
      --model BAAI/bge-small-zh-v1.5 \
      --revision YOUR_PINNED_MODEL_COMMIT \
      --device cpu --allow-network

The default is offline. If the model files already exist locally, omit
`--allow-network`. The output manifest records the input byte hash,
model ID/revision, dimension and a fixed title+excerpt template. Historical
excerpts can contain LLM-generated summaries, so semantic similarity is *not*
evidence of underlying source facts. Do not commit model files or embeddings.
Only use model weights and texts under their applicable terms.

## Running experiments

    # B2 vs B3 with real locally computed vectors, no published mutations:
    python eval/run_b3_experiment.py \
      --input data/news_items.jsonl \
      --vectors /tmp/xwl-embeddings.json \
      --output /tmp/b3-shadow.json

    # Synthetic pipeline smoke test: intentionally leaks gold labels:
    python eval/run_b3_experiment.py \
      --fixture eval/datasets/synthetic_event_gold.json \
      --oracle-demo --output /tmp/b3-oracle-smoke.json

    # Optional reviewed-pair quality comparison after independent review:
    python eval/run_b3_experiment.py \
      --input data/news_items.jsonl \
      --vectors /tmp/xwl-embeddings.json \
      --reviews /tmp/event-pair-review.jsonl \
      --output /tmp/b3-reviewed.json

The oracle demo **manufactures** vectors using synthetic event labels. It is
a plumbing test and can never be used to report real embedding accuracy.
The historical report has **null** gold clustering metrics until independent
annotations are available. Reviewed-pair scores evaluate only actually
reviewed pairs in the stratified queue and are not population performance.

## Identity and anti-merge safeguards

- Generic digest titles are not atomic event identities.
- Disjoint named organizations without a common named person are a
  conservative contradiction in this prototype, not a universal semantic law.
- Conflicting explicit event action and location hints block a pair.
- A centroid attachment must be backed by a candidate edge, compatible
  with all cluster members, and pass member/centroid cosine gates.
- A fixed 7-day *pair candidate window* is distinct from the configurable
  maximum 30-day observed event span. Long-running issue/storyline membership
  needs a separate layer; it is not an excuse to conflate different meetings.

These Chinese action/location rules are intentionally simple; they may
incorrectly reject synonyms and same event coverage across regions. Record
those as false negative cases in the real gold set before relaxing guards.

## Evaluation gates before any publish

1. Freeze input snapshot and model commit hash, text recipe, parameters.
2. Obtain two-reviewer/adjudicated labels, include model-positive and negative
   candidates, and hold out whole weeks.
3. Measure blocker Recall@K, semantic candidate recall, union recall,
   pairwise P/R/F1, B-Cubed, false merges, fragmentation and abstention.
4. Report per-stratum confusion, uncertainty and reviewer agreement.
5. Compare B2 and B3 on the *same* held-out weeks. Do not tune test set.
6. Shadow execute on multiple dates; validate no mutation to SQLite, data/*.json
   or source URL maps, and inspect representative mistakes.
7. Introduce stable Event UUIDs and audited split/merge history before
   production integration. Keep existing S01 atomic publication boundary.

## Known limitations (not hidden)

- Embeddings are not generated or benchmarked in GitHub Actions.
- The provided synthetic fixture is small and may encode ambiguous event
  granularity (e.g. project initiation versus later test operation).
- Candidate and centroid constraints are not yet calibrated or learned.
- The historical corpus remains unlabeled; concentration is not correctness.
- Pairwise reviewed samples with stratified selection require design-based
  weighting before claims about full-population accuracy.

## Source material

- BAAI small Chinese embedding model: https://huggingface.co/BAAI/bge-small-zh-v1.5
- Prior S03/S05 protocol: EVENTS_S03_EVAL_S05.md
- Existing production rollback mechanism: db/event_engine.py
