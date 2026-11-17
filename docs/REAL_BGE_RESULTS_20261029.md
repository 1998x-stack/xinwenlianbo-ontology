# Real Chinese Embedding Shadow Experiment — 2026-10-29

## Provenance

- Repository: 1998x-stack/xinwenlianbo-ontology
- Feature branch: feat/real-embedding-gold-evaluation-20261029
- Main input: data/news_items.jsonl, 386 news items (historical snapshot, 2026-05-12 to 2026-06-09)
- Model: BAAI/bge-small-zh-v1.5
- Immutable Hugging Face revision: 7999e1d3359715c523056ef9478215996d62a620
- Pipeline: sentence-transformers==3.3.1, transformers==4.46.3, huggingface-hub==0.27.1, torch==2.5.1+cpu
- Verified real-model run: https://github.com/1998x-stack/xinwenlianbo-ontology/actions/runs/40832986744
- Independent Python/CI run: https://github.com/1998x-stack/xinwenlianbo-ontology/actions/runs/40832986841
- All 7 regular CI jobs plus the real model job: **passed**.
- Generated vectors, full shadow JSON, model log and unlabeled review packet are retained temporarily as a GitHub Actions artifact.
- **No published production event rows, data/*.json, or online dashboard files changed.**

## Results — *unlabeled historical data*

| Metric | B2 constrained | B3 centroid with **only B2 rule candidates** | B3 centroid with rule + real semantic candidates |
|---|---:|---:|---:|
| News items | 386 | 386 | 386 |
| Event clusters | 356 | 322 | 321 |
| Singleton clusters | 336 | 294 | 292 |
| Largest cluster | 4 | 7 | 7 |
| Largest cluster share | 1.0363% | 1.8135% | 1.8135% |
| Max within-cluster reported span | 7 days | 22 days | 22 days |
| Gold pairwise F1 | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE |
| Gold B-Cubed F1 | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE |

Candidate attribution:

| Retrieval count | Value |
|---|---:|
| B2 blocked candidates | 5,588 pairs |
| Real cosine Top-K semantic candidates | 159 pairs |
| Unique semantic candidates *not* present in B2 blocking | **2 pairs** |
| Union of both candidate sets | 5,590 pairs |

**Interpretation:** B2 to centroid-only reduces singleton count from 336 to 294 (42 fewer).
Adding real semantic candidates with the *same centroid algorithm* reduces it from
294 to 292 (2 fewer). This observational change should not be described as
increased accuracy, and the singleton delta may include both legitimate
recoveries and false merges. In this run the primary difference is clustering
semantics rather than unique embedding candidate recall.

The max within-cluster broadcast span rises to 22 days. That demands review:
long-running storylines are not necessarily the same *atomic* event.
The large number of B2 blocked candidates (5,588) also indicates that
blocking was broad relative to B3's conservative semantic filters; prioritize
candidate quality and event identity, not just expanding k.

## Review packet

The run generated a 12-article date-stratified subset (2026-06-07 to 2026-06-09)
and all 66 unordered article pairs. Every reviewer label is NULL at creation.
The review validator verifies 0 ready definitive pairs. Two real independent
reviewers must examine the underlying source text and record explicit evidence,
then adjudicate disagreements and verify transitive event identity before
running the gold promotion command. A generated review queue is *not* a gold set.

## Scientific limitations

1. The entire 386-item historical dataset lacks independently verified
   event clusters. Therefore **no real precision/recall/F1 claims are valid**.
2. The embedding text template uses headline plus up to 240 characters
   of a potentially model-generated excerpt. It is useful for retrieval
   but not a source-grounded factual statement.
3. A 12-article sample is not representative or statistically powered.
   It is an initial **annotation workflow demonstration**.
4. The current centroid algorithm uses hand-crafted action, location,
   institution and cosine thresholds; a 22-day span may be a false merge.
5. Re-run on multiple disjoint date windows and verify real gold before
   adjusting thresholds or switching published event detection.
6. Candidate recall measured against manually verified event identities
   remains unavailable. The two new semantic candidates may or may not
   be true positive event pairs.

## Acceptance and next gate

- [x] Real pinned model generated corpus embeddings.
- [x] Exact input hash and model metadata checked.
- [x] Same input used for B2 and both B3 factorial variants.
- [x] CI and real-model Actions jobs completed successfully.
- [x] Exhaustive, entirely unlabeled human review packet generated.
- [x] Gold builder enforces two reviewer IDs, evidence, exhaustive within-subset
  labeling, and transitivity.
- [ ] Complete actual human review and adjudication.
- [ ] Calculate real blocking and pairwise gold metrics.
- [ ] Inspect added B3 event merges for false positives.
- [ ] Measure time-heldout performance and uncertainty.
- [ ] Only after those gates, consider shadow promotion to production.

**Promotion remains blocked.** This document reports what actually ran; it does
not infer event truth from a small/no-gold dataset.
