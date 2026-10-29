# S03 × S05: Evidence-Constrained Event Discovery & Evaluation Factory

> Design status: offline experimental implementation. The current production
> event tables, exports, dashboard, and stable event identifiers are unchanged.

## 1. Why the old event graph is not trustworthy

The historical export contains a 331-of-386 article connected component; its
size is a symptom, not a measured event-accuracy statistic. The old rule links
articles that share a topic within seven days, then takes transitive closure.
A--B and B--C can be linked by different topical features without A and C
belonging to one real-world event. As a result, cluster meaning can collapse.

**Coverage is not importance**. The corpus is a single broadcaster's selection
of reports. Same person/topic does not establish same event or causal relations.

## 2. Architecture and boundaries

Data/news_items.jsonl (read-only)
 -> parse_articles (unique IDs, valid dates)
 -> candidate blocking (indexed uncommon topics/actors/organizations/grams)
 -> pair evidence: lexical, keyword, entity and topic overlaps
 -> conservative gates (exclude generic digest titles; no shared generic topic alone)
 -> constrained clustering (all cross-members require qualified pair edges by default)
 -> preview event assignment (preview IDs are NOT stable real-world identities)
 -> evaluation diagnostics + optional independently annotated gold metrics.

There are deliberately NO external API calls, mutable database writes, model
weights, or new runtime dependencies in the initial version. Production event
identity merging/splitting and cross-day event continuity are NOT implemented.

## 3. Ablations

| Variant | Definition | Expected weakness |
|---|---|---|
| B0 / legacy | Reproduce top-three-topic exclusion and connected components | Topic-induced giant component |
| B1 / connected | Score candidate pairs, then transitive connected components | Bridge/chain false merges |
| B2 / constrained | Same scored pairs; require every cross-pair to pass before merging | Conservative fragmentation; weaker recall |

The baseline excludes three highest-frequency topics calculated from the chosen
snapshot, not from stale denormalized database counters. The candidate blocking
uses rare topics, persons, organizations and Chinese character bigrams. Scores
are *heuristics*, not probability estimates. Current coefficients and default
score (0.34) have NOT been calibrated by a real gold set.

In B2, sorted edges are merged deterministically. Merge checks also require
a maximum 30-day cluster span, which is a configurable experimental safeguard,
not an assertion about real-world event duration. Full pairwise validation
is quadratic in proposed cluster sizes and should be benchmarked before
scaling the corpus. The 150-item posting-list guard and rare-index filters
can miss true event pairs: evaluate blocking recall separately.

## 4. Run commands

No API credentials are necessary:

    python -m unittest tests.test_event_clustering_v3 -v
    python eval/run_event_ablations.py --fixture eval/datasets/synthetic_event_gold.json
    python eval/run_event_ablations.py --input data/news_items.jsonl
    python eval/run_event_ablations.py --input data/news_items.jsonl --output /tmp/event-ablations.json
    python eval/make_annotation_queue.py --input data/news_items.jsonl --output /tmp/event-pair-review.jsonl --limit 100

Historical JSONL is unlabeled. Only concentration, membership completeness,
cluster duration and counts can be calculated. Pairwise/B-Cubed quality values
must remain null for historical data until independent labels are provided.

The synthetic fixture contains hand-authored fictional scenarios. Its accuracy
is a regression result, not evidence that the detector performs well on
actual broadcasts.

## 5. Annotation protocol (mandatory before production switch)

1. Freeze an immutable input snapshot, model/prompt settings, and annotation
   guideline version. Select training/validation/test splits by **date** with
   no leakage across the test time window.
2. Independently annotate 100--200 initial *pairs*, covering same event, same
   topic/different event, same actor/different event, continuing events and
   topical bridges. Explicitly sample both model-positive and model-negative
   pairs; the current queue deliberately stratifies model matches, topical nonmatches
   and random controls, but still requires population-aware weighting to
   estimate overall real-world performance.
3. Use labels: SAME_EVENT, RELATED_NOT_SAME, DIFFERENT_EVENT, UNSURE.
   Reviewers must distinguish event *identity* from topic correlation. Require
   exact source headline and preferably source excerpts/URLs for decision;
   the queue currently has headlines and overlap summaries but must be
   enriched with raw source evidence before final human review.
4. Have two reviewers label each pair blindly. Keep a disagreement log,
   adjudicator, annotator version and confidence.
5. Create transitive-consistent gold event partitions, not just pairs. Check
   that each partition's labels are consistent (A=B and B=C requires A=C).
6. Hold out a final set of weeks and never tune B2 thresholds on it.
7. Measure candidate **recall**, pairwise precision/recall/F1, B-Cubed F1,
   false-merge case studies, fragmentation, group size, event-time consistency,
   and compute/token costs. Bootstrap confidence intervals by **event/day**.
8. Define an explicit promotion gate before running the final held-out test:
   B2 should materially reduce false merges without unacceptable recall loss.
   Do not set an arbitrary largest-cluster threshold as the sole quality gate.

A 100--200 pair starter queue is NOT enough for a statistically strong final
performance claim. Expand to a cluster-level benchmark and diverse eras.

## 6. Integration and publication strategy

A recommended future integration has two independent axes:

- detector variant: legacy / candidate_connected / constrained / learned;
- publication mode: preview / shadow / publish.

Default stays legacy + publish until actual approved quality gates. In shadow
mode, compare the experimental candidates to published events, log the model
version and snapshots, but do not change the live tables. Real publication
requires a persistent EventIdentity registry with stable UUIDs and explicit
merge/split/correction history; preview membership hashes must never become
official Event IDs.

The existing staged SQLite publication mechanism from S01 should remain the
single publication boundary. The experimental code must not call it.

## 7. Remaining engineering tasks

- Real manually reviewed gold partitions and reliable source evidence spans.
- Alias/identity resolution and geo/event-argument role typing.
- Learned pair classifier and optional embeddings, each evaluated separately.
- Persistent event identity, attachment and merge/split audit trail.
- Efficient bounded candidate retrieval for multiyear corpora.
- Event status semantics separating report recency from real-world resolution.
- Calibration, uncertainty reporting, drift monitoring, and transparent
  review queues for low-confidence candidates.
- Test against a clean regenerated historical snapshot, not just committed
  static exports.

## 8. Reproducibility and quality rules

Never report synthetic gold F1 as production accuracy. Never infer causal
connections from co-occurrences. Report historical snapshot dates and known
missing source URLs. Keep all experimental outputs in user-chosen files;
do not commit regenerated data/*.json or silently publish experiments.


## 9. Candidate recall and reviewer sampling

The ablation output now explicitly separates:
- candidate_blocking.gold_retrieval: upstream blocking recall;
- variants.connected.edge_retrieval: accepted pair-edge recall;
- variants.*.gold_pairwise and gold_bcubed: post-clustering partition quality.

Historical unlabeled data returns null for these gold scores. If recall is poor,
first inspect **candidate blocking** instead of only tuning cluster thresholds.

`eval/make_annotation_queue.py` uses seed-stable sampling from three
strata (model-positive, topical-unmatched, random-control). All review labels
start null. Two independent reviewers plus adjudication are represented in
the queue schema, but no annotation is performed automatically. Do not
equate "topical_unmatched" with a known true negative.

Use `--start` and `--end` to isolate a temporal holdout for review.
