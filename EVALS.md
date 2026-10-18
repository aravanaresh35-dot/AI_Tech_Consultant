# EVALS

## Methodology
All automated cases are deterministic: DEMO mode, SQLite in a temp dir or memory, Knowledge Brain stubbed with `httpx.MockTransport` (Tasks 2–3) or the offline demo site (Task 1).
No network, no paid API. One command reproduces everything: `python scripts/run_evals.py` → `reports/eval_results.json`.
`scripts/smoke_test.py` (11 checks) and `scripts/ui_test.js` (12 click-through checks, jsdom) run against live local services.

## Measured results (run on 2026-10-18, DEMO mode, Python 3.12)
| Suite | Cases (pytest items) | Passed | Failed |
|---|---|---|---|
| Task 1 Knowledge Brain | 36 | 36 | 0 |
| Task 2 Inbox Agent | 36 | 36 | 0 |
| Task 3 Meeting→SOW | 39 | 39 | 0 |
| **Total** | **111** | **111** | **0** |

Smoke test (3 services over real HTTP): 11/11 PASS. Dashboard click-through (jsdom, real services): 12/12 PASS (this is not a real-browser test).
Pass rate = passed ÷ collected. A passing case means the assertion held; it does not certify answer quality.

## Cases by task (≥ 20 each)
* **Task 1:** supported answer + correct citation, unknown question, partial evidence, expert answer outranks crawl, update, removal never cited, duplicate ingestion/sync retry,
  scrape failure, image failure keeps article, images not analysed in demo, 5 invalid-input cases + malformed JSON, escalation creates one task, expert answer re-ingested, task errors,
  HTTP timeout, 503 retry recovery, 5 retrieval-relevance queries, no unsupported claims/injection, persistence across restart, robots.txt, sitemap index + malformed sitemap,
  lastmod skip, resume after partial run, scheduler only when configured, live path with unsupported model/outage, health.
* **Task 2:** dataset ≥ 50 and all categories, classification accuracy on dataset, first sample of each of 8 categories, grounded product answer, technical issue, refund (no invented terms),
  complaint, quote (no price), new project, follow-up with history, ambiguous, missing details/invalid input, no facts without evidence, prompt injection, KB unavailable, draft quality,
  human edit + diff, rejection queues nothing, feedback + streak persist, 20-consecutive threshold, edit resets streak, revocation paths, refund never auto, outbound simulated / auto needs explicit enable,
  ineligible drafts ignored, approved-reply memory, edit-rate by prompt version, workflow errors, live-path fallback.
* **Task 3:** health + KB-down health, complete transcript, scope sections, ambiguity, missing acceptance criteria, unresolved statements, dependencies, stated acceptance criterion, existing feature found,
  not found, no claim without evidence, KB queried per requirement, KB unavailable, estimate structure, existing-feature cheaper, proposal completeness / no invented price, illustrative price, phase-2 exclusion,
  follow-up versioning (v1 preserved), added/removed/modified/out-of-scope, hours delta + client-approval list, removed not estimated, first version has no comparison, empty / short / truncated / oversized / long transcripts,
  malformed requests, state errors, conflicting requirements, injection in transcript, approval internal-only, approval per version, persistence across restart, sample transcripts present.

## Metrics and scoring
| Metric | Definition | Status |
|---|---|---|
| Test pass rate | passed ÷ collected | **Measured**: 111/111 |
| Classification accuracy | exact match of rule-based classifier vs author-written label, 56 emails | **Measured**: 55/56 = 0.982. Miss: E056 (two issues in one email, expected `technical_issue`, got `product_how_to`). Caveat: rules and labels were written by the same author, so this likely overstates real-world accuracy. |
| Citation / evidence correctness | asserted per test (URL matches expected article; removed articles never cited) | Measured as pass/fail cases only; no percentage claimed |
| Draft edit rate | share of reviewed eligible drafts not approved unchanged | Implemented (`/automation-status`, `/feedback`); **no real reviewer data yet** |
| Scope / estimate completeness | required sections non-empty; totals = Σ tasks (Validator) | Measured as pass/fail per transcript |
| Latency | per-agent `timings_ms` stored with each version | Recorded; demo timings are milliseconds and say nothing about live models |
| Token usage / cost | `AIClient.usage`; cost only if price env vars set | **Unavailable** – no live calls were made |

## Model comparison methodology and status
`scripts/benchmark_models.py` sends the same 56 emails to `BENCH_MODEL_A` and `BENCH_MODEL_B` with an identical system prompt, scores exact category match,
and records latency, tokens and (if prices supplied) cost to `reports/benchmark_results.json`. **Status: PENDING / NOT RUN** – no API key was available. No second-model results exist and none are claimed.
Limitations when run: one task, one pass, author-written labels, network-dependent latency.

## Failure cases and limitations
* E056 misclassified (above). Demo Analyst can create spurious requirements and may label a heavily reworded change "added" (see DESIGN §11); tests use transcripts that avoid asserting on those artefacts.
* Demo estimates are keyword heuristics, so "reasonable hour estimates" is tested as structural sanity (sums, bounds, existing-feature < custom), not accuracy.
* Not measured: Claude answer/draft quality, image understanding, live-site crawl, Docker, load/concurrency.
