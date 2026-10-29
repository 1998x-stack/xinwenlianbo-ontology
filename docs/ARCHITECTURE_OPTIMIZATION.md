# Full Architecture Audit & Optimization Roadmap

Baseline: master @ bdca6f5 (2026-10-29). This document is a proposed roadmap, not a statement that every stage has been implemented.

## Mission and boundaries

Transform CCTV Xinwen Lianbo broadcasts into versioned, evidence-backed news knowledge. The dataset represents **coverage by one broadcaster**, not neutral measures of societal importance, proof of causal relations or independent verification of events. Represent source observations, algorithmic inferences and human verification separately.

## Target processing layers

1. Source adapters and immutable source snapshots: source URL, captured_at, source hash, collection status and usage terms.
2. Parsing, normalization and data-quality checks: structured news items, completeness, error pages, source revisions, deduplication.
3. AI extraction: versioned schema, model ID, prompt version, selected taxonomy and source-grounded evidence spans.
4. Canonical entity registry: IDs, aliases, entity-resolution decisions and corrections.
5. Event identity service: candidate retrieval, pairwise matching, constrained clustering, timeline and merge/split history.
6. Ontology and evidence: typed claims, named relations, temporal scopes, provenance and review status.
7. Serving: SQLite/FTS5 with optional RDF/graph view, versioned JSON exports, API and static dashboard.
8. Cross-cutting evaluation: quality metrics, dataset splits, costs, regression and fault-injection tests.

## Main risks by priority

| Priority | Problem | Target |
|---|---|---|
| P0 | Database setup omitted event schema | Idempotent setup/migration for v1 and v2 |
| P0 | Live event tables cleared before rebuilding | Stage privately, validate, atomically publish |
| P0 | Historic event cluster contains 331 of 386 segments | Evaluate semantic matching and coherence constraints |
| P0 | Crawl output drops source URL | Preserve source metadata and evidence |
| P0 | Some SQLite writers do not enable foreign keys | Uniform connection policies and insert order |
| P1 | Person aliases create duplicate IDs | Canonical ID registry and alias links |
| P1 | AI output has no typed contract | Validate or quarantine; never silently invent |
| P1 | Event lifecycle depends on current wall clock | Explicit as-of broadcast date for replay |
| P1 | N+1 and LIKE scans grow with corpus | Batch joins and benchmarked Chinese FTS5 trigram |
| P1 | JSON snapshots are written separately | Version manifest, stable publication pointer |
| P2 | Claims have no per-assertion evidence | Claim/Evidence/Provenance model |
| P2 | PageRank blends mentions, topics and co-occurrence | Typed graph semantics and separated analytics |

## Recommended object model

| Object type | Key fields | Purpose |
|---|---|---|
| SourceDocument | source_id, url, captured_at, raw_hash, license | Immutable provenance |
| NewsSegment | news_id, source_id, broadcast_date, order, revision | Versioned news |
| Entity | UUID, type, canonical_name | Person/Org/Location/Policy identity |
| EntityAlias | entity_id, alias, locale, source | Disambiguation |
| Mention | news_id, entity_id, start/end offset | Grounded mentions |
| Event | stable UUID, event type, observed interval | Event identity |
| EventMembership | event_id, news_id, score, evidence, run_id | Versioned membership |
| Claim | subject, predicate, object, status, temporal scope | Typed relationship |
| Evidence | claim_id, news_id, text offsets, source hash | Auditable support |
| PipelineRun | run_id, input hash, model, prompt, config, status | Reproducibility |
| Publication | version, manifest hash, active pointer | Atomic visibility |

Distinguish broadcast date, underlying event date, source published time and extraction time. A mention does not imply participation, and co-occurrence never establishes causation.

## Stage S01: data/runtime integrity (P0)

Implemented in the companion PR: apply both SQL schema generations on setup; enable foreign keys for CLI and model enhancement connections; insert organizations before people; preserve source URL in Markdown and importer; reject known error-page titles; stage event rebuild in private SQLite snapshot and publish all event tables in a single live transaction; evaluate historical event scores as of the latest ingested broadcast. Add fault injection tests.

Exit criteria: empty database setup works twice; URL backfill preserves original text and enrichments; failed stage leaves old events intact; success replaces complete generation.

Remaining S01 work: consistent export snapshot/manifest, all SQLite writers, retry policy, source revision reconciliation and complete CLI/browser E2E.

## Stage S02: extraction contracts (P1)

Add versioned Pydantic JSON schemas for topic, person, organization, location, policy signal, named claim and evidence span. Check schema, entity IDs, allowed topic labels and source text offsets before writing. Support abstention and human-review flags. Stamp each extraction with model version, prompt hash and taxonomy hash.

Exit: invalid outputs quarantined; evidence offsets verified; idempotent reruns keyed by content and pipeline versions.

## Stage S03: semantic event engine (P0)

Build candidate recall from time windows, specific topic anchors, canonical actors, named organizations, headline similarity and embeddings. Score pairwise same-event vs merely related-topic separately. Constrain agglomeration by temporal range, event anchor consistency and cohort coherence, and retain event identity across new membership.

A core failure case is the historical 331/386 mega-component. Do not replace it with arbitrary cluster-size caps alone: caps hide rather than solve false merges. Promote a new algorithm only after gold-set evaluation. Event statuses should describe observed reporting state, not claim an external event has objectively ended.

Exit: held-out human-labeled pairs plus complete event clusters, reported overmerge and split errors.

## Stage S04: ontology and serving (P1/P2)

Implement a typed predicate registry, support relation evidence and temporally valid assertions, optionally export provenance via W3C PROV-O and validate RDF through SHACL. Benchmark SQLite FTS5 trigram for Chinese substring queries; compare against LIKE on real queries, including 1- and 2-character searches where trigram may not help. Add retrieval explanations and source citations to query output.

Exit: multi-hop results have explicit claim types and source evidence; graph edges obey type constraints.

## Stage S05: evaluation factory (P1)

- Scraping: date coverage, bad-page rate, duplicate rate, parsing regressions.
- Extraction: span exact match, entity micro/macro P/R/F1 and confidence calibration.
- Entity linking: resolution accuracy, false-merge rate and abstention.
- Topic classification: per-label precision/recall/F1.
- Events: pairwise P/R/F1, B-Cubed F1, overmerge, fragmentation and temporal continuity.
- Policy signals: novelty precision checked against earlier documents and authoritative policy sources.
- QA/GraphRAG: evidence sufficiency, unsupported-claim rate and citation accuracy.
- Operations: rollback success, rerun consistency, p95 latency and cost per 1,000 articles.

Use temporal and source-stratified train/dev/test data; report uncertainty and model/prompt input versions. Initial gold set: 100–200 manually labeled event pairs, including generic-title, same-topic/different-event, chain-bridge and long-running-event traps.

## Event algorithm ablations

| Variant | Change | Hypothesis |
|---|---|---|
| B0 | Current topic+time connected components | Baseline overmerge |
| B1 | Generic-topic frequency filtering | Reduce super-connectors |
| B2 | B1 + canonical entity anchors | Improve precision |
| B3 | B2 + title/semantic embeddings | Improve recall |
| B4 | B3 + pairwise event classifier | Improve pair quality |
| B5 | B4 + coherence-constrained clustering | Eliminate chain bridges |
| B6 | B5 + versioned temporal updates | Preserve identity over time |

Evaluate on identical held-out examples; publish error reports with illustrative counterexamples before promotion.

## Stage S06: operations and analysis products (P2)

Incrementally ingest late-arriving/corrected broadcasts, audit pipeline runs, preserve last good snapshot and publish one versioned manifest. Dashboard should show coverage windows, data revision, verified vs inferred statements, source links, event timelines and policy phrasing comparisons. Consider GraphRAG and live API only after evidence and event evaluation meet quality gates.

## Proposed code layout (future)

- src/xinwenlianbo/ingest: sources, fetch, parse, quality
- src/xinwenlianbo/store: connection, migrations, repository, publication
- src/xinwenlianbo/extraction: contracts, prompts, models, runs
- src/xinwenlianbo/identity: entities, aliases, resolver
- src/xinwenlianbo/events: candidates, similarity, clustering, lifecycle
- src/xinwenlianbo/ontology: types, claims, evidence, validators
- src/xinwenlianbo/serving: queries, API, exports
- eval: datasets, metrics, runners, reports
- tests: unit, integration, contracts, browser, fault injection
- docs: design decisions, schema versions, operator runbooks

Only move the current working modules once behavioral-parity tests exist.

## Release acceptance checks

Validate all published foreign keys, entity/claim types, event-member references, evidence spans, stable source identity, source hashes and snapshot dates. Inject an AI network failure, invalid JSON, SQLite lock and partially missing publication files; the previous published generation must remain usable. Pin third-party dependencies, review content redistribution terms, protect API keys and publish a reproducibility manifest.

## References

- SQLite foreign keys: https://www.sqlite.org/foreignkeys.html
- SQLite FTS5: https://www.sqlite.org/fts5.html
- W3C PROV-O: https://www.w3.org/TR/prov-o/
- W3C SHACL: https://www.w3.org/TR/shacl/
