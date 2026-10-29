# Stage B4-prep — Real Embeddings, Review Packet and Gold Validation

## Status and boundaries

This work is stacked on PR #4, which in turn depends on PR #3.
No production event IDs, SQLite event tables, or static site exports change.

The only **real model inference** in this stage runs in the dedicated
GitHub Actions workflow \`real-embedding-shadow.yml\`, using the pinned
Chinese embedding model \`BAAI/bge-small-zh-v1.5\` revision
\`7999e1d3359715c523056ef9478215996d62a620\`. Fixed
Torch/transformers/sentence-transformers versions and exact input SHA
are recorded. Output is ephemeral Actions artifact, not committed data.

**A real model does not constitute real gold labels.** The 386 historical
articles are still unreviewed. No production accuracy, pairwise F1 or B-Cubed
F1 is claimed from their unlabeled data.

## Full workflow

    frozen historical JSONL
       │
       ├── real pinned sentence-transformer inference on CPU
       │       └── validated vector manifest (ID coverage, dimensions, input hash)
       │                  └── B2 vs B3 shadow comparison + manifest report
       │
       └── date-stratified 12-item review selection (2026-06-07..09)
                     └── ALL 66 item-pair review tasks (labels null)
                             └── independent review #1
                             └── independent review #2
                             └── adjudicate conflict/UNSURE
                             └── validate exhaustive consistency
                                     └── human_reviewed gold fixture
                                             └── B2/B3 metrics on this subset

## Run and retrieve

Actions automatically starts on PR for relevant code changes. It can be
re-triggered by workflow_dispatch once the workflow is on the default branch.
The PR CI run creates an Actions artifact named \`real-bge-shadow-<sha>\`:
- \`embeddings-bge-small-zh-v1.5.json\` (real model vectors)
- \`model-provenance.log\`
- \`b3-real-shadow.json\` (diagnostics with gold metrics null)
- \`summary.json\` (compact run report)
- \`review-selected-ids.json\`
- \`review-pairs-UNLABELED.jsonl\`
- \`review-validation.json\`

If the Hugging Face hub is unreachable, **do not invent** model results or
pretend an oracle demo is real. Re-run with network access or local cached
weights. Model inference is not required for source and gold validation tests.

For a local repeat:

    python -m pip install sentence-transformers==3.3.1 transformers==4.46.3 huggingface-hub==0.27.1
    python eval/build_embeddings_b3.py --input data/news_items.jsonl --output /tmp/vectors.json --model BAAI/bge-small-zh-v1.5 --revision 7999e1d3359715c523056ef9478215996d62a620 --allow-network
    python eval/run_b3_experiment.py --input data/news_items.jsonl --vectors /tmp/vectors.json --output /tmp/real-shadow.json

## Human gold annotation guide

The generated packet is **not reviewed**. Each of its 66 pairs must be
judged independently by two real people using:

- SAME_EVENT: both specifically refer to the same occurrence, not merely one
  visit/storyline, person or subject.
- RELATED_NOT_SAME: same broader development/subject but distinct atomic events.
- DIFFERENT_EVENT: no same atomic event identity.
- UNSURE: not enough evidence; seek original source before adjudication.

Reviewers must not see each other's decisions before submission. The JSONL
format holds both reviewer results but does not itself enforce blindness.

Reviewers must inspect available original transcript/source (not just
model-generated summaries), cite evidence, and record explicit reason for
adjudication. Missing historical source URLs require retrieval/verification;
otherwise a pair may remain UNSURE. Do not fabricate evidence.

A finished subset requires exhaustive pair coverage (12 choose 2 = 66),
two distinct reviewer IDs for every pair, and compatible transitive labels.
There is no automatic promotion of model predictions into ground truth.

After independent reviews:

    python eval/validate_annotations.py /tmp/review-pairs.jsonl
    python eval/build_reviewed_gold.py \
      --input data/news_items.jsonl \
      --reviews /tmp/review-pairs.jsonl \
      --selection /tmp/review-selected-ids.json \
      --guideline-version news-atomic-event-v1 \
      --output /tmp/human-reviewed-subset.json

Then execute separate B2/B3 trials on that *frozen* subset; regenerate
embeddings for the exact fixture input (embedding hash binding prevents reuse
of the full source JSONL vectors with a different input file). The raw
reviewed-pair statistics and full partition metrics answer different
questions. Evaluate only held-out, un-tuned dates for final model selection.

## Report acceptance

- Model SHA and exact input byte SHA are recorded; no missing/NaN vectors.
- Exact source ID coverage, no input mutation, and B2/B3 run on same corpus.
- Real embedding similarity is reported separately from verified event identity.
- Historical metrics of precision/recall remain null without gold.
- 12-article review queue has precisely 66 unlabeled pairs.
- Double-review, temporal consistency and transitivity are validated.
- Workflows preserve all currently published event rows and JSON exports.

## Caveats

The initial selected dates are a convenience set, not a representative
held-out benchmark. For defensible statistics expand beyond this 12-article
subset to multiple independent time windows and report cluster-block bootstrap
confidence intervals. The initial model is CPU-friendly but uses explicit
geographic/action filters that may reject semantically valid same-event pairs.
Review both false merges and false splits before changing the guards.
