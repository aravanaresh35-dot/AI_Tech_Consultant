# DESIGN

## 1. Business problem (plain English)
A small agency answers the same product questions by email, spends hours turning meetings into scopes and quotes, and keeps product knowledge in
people's heads. The system gives them (1) a **single source of product truth** that cites its sources and admits when it doesn't know, (2) an
**email assistant** that drafts replies from that truth and learns from the reviewer's edits, and (3) a **meeting-to-proposal assistant** that checks
whether the product already does what the client asks before estimating custom work. A human decides everything that leaves the building.

## 2. Architecture and data flow
See `docs/architecture.md` for the diagram. Four processes: three FastAPI services (Python 3.12, one SQLite file each) and a static dashboard.
Task 2 and Task 3 reach Task 1 **only** through `shared/tech_common/kb_client.py` (`POST /api/v1/search`, `/health`) – configurable URL, 10 s timeout,
2 retries with backoff, and a typed `KnowledgeBrainUnavailable` error. Nobody re-implements retrieval.
* **Email flow:** `POST /emails` → classify → search Task 1 → draft → `needs_human_review` + reasons → reviewer approves / edits / replaces / rejects →
  `feedback` row (original draft, final text, diff, category, model, prompt version, time) → streak tracker → *simulated* outbound row only if eligible and enabled.
* **Meeting flow:** transcript → Analyst → Product Consultant (Task 1 per requirement) → Estimator → Scope builder → Proposal → Validator → stored as
  version *n*. A follow-up transcript merges with the previous requirements, produces version *n+1* and a comparison; version *n* is never modified.

## 3. Key feature choices (and why)
* **BM25 keyword retrieval, no embeddings.** Works offline with no credentials, is explainable to a junior engineer, and every passage keeps its article
  link. Trade-off: weaker on paraphrases. Evidence is graded `supported / partial / insufficient` from query-term coverage (thresholds configurable).
* **Escalate instead of guessing.** Insufficient evidence → no sources, honest answer, and a pending expert task. An expert's answer is stored as a
  first-class article and outranks crawled text, so the same question is answered next time.
* **Soft deletion.** Articles removed from the sitemap become inactive and can never be cited (tested). Sync skips unchanged `lastmod`/content hash and is safe to retry.
* **Demo mode as a first-class path.** Deterministic, labelled `DEMO` in every response; live mode is selected only when key **and** model id are set.
* **Sequential agents, not a framework.** Each step has a pydantic contract (`schemas.py`, `sow-v1`), so each is testable alone.
* **Versioned everything.** Prompt versions (`sow-prompts-v1`, per-service draft prompts) and schema version are stored with every output.
* **SQLite per service.** Zero setup, persistent across restarts (tested), adequate for one reviewer. Not for concurrent multi-user load.

## 4. Features intentionally dropped
Embeddings/vector store (needs credentials; BM25 chosen instead) · authentication/roles (demo scope) · real email sending and real proposal dispatch
(unsafe without authorisation) · model fine-tuning (the "learning" is stored examples + versioned prompts, **not** weight training) · PDF/Word export of proposals ·
streaming UI · a TypeScript Inbox Agent (Python used – the assignment's permitted fallback – to keep one reliable toolchain).

## 5. Agent responsibilities
| Agent | Input → Output | Notes |
|---|---|---|
| Transcript Analyst | transcript (+ prior requirements) → `AnalystOutput` (requirements, open questions, conflicts, dependencies, acceptance criteria, input status) | Demo: cue-phrase heuristics. Live: Claude with JSON schema. Transcript is untrusted data. |
| Product Consultant | requirements → `KBFinding[]` | Calls Task 1. Says "may be covered… to be confirmed" only with evidence; never asserts absence. KB down → `unavailable`, not a guess. |
| Estimation Agent | requirements + findings → `Estimate` | Demo: transparent per-feature base hours (not expert estimates), existing-feature items ≈ 3 h; total always recomputed from tasks. |
| Proposal Agent | scope + estimate → `Proposal` | Price only if `HOURLY_RATE` set, labelled illustrative. |
| Validator | everything → `ValidationReport` | Errors block approval (e.g. feature claimed without evidence, totals mismatch, empty section). |

## 6. API contracts (real routes)
**Task 1 :8001** `GET /health` · `POST /api/v1/chat {question, conversation_id?}` → `{answer, sources[], evidence_status, confidence, needs_human_review, task_id, mode, model}` ·
`POST /api/v1/search {query, top_k}` · `GET /api/v1/articles` · `POST /api/v1/ingest` · `POST /api/v1/sync` · `GET /api/v1/ingest/status` ·
`GET|POST /api/v1/tasks` · `POST /api/v1/tasks/{id}/answer {answer, expert_name}`.
**Task 2 :8002** `POST|GET /api/v1/emails` · `GET /emails/{id}` · `POST /emails/{id}/draft|approve|replace|reject|feedback` · `GET /api/v1/feedback` ·
`GET /api/v1/automation-status` · `POST /api/v1/automation/evaluations` · `GET /api/v1/outbound`.
**Task 3 :8003** `POST|GET /api/v1/meetings` · `POST /meetings/{id}/analyze|follow-up|approve` · `GET /meetings/{id}/scope|estimate|proposal|comparison|versions`.
Full schemas: each service's `/docs` (OpenAPI). Errors: 404 unknown id, 409 wrong state, 413 oversized, 422 invalid, 5xx generic message (details only in logs).

## 7. Auto-send eligibility (Task 2) – precise rules
* **Same category** = the email's *final* category (the AI's, or the one a human corrected).
* **Eligible draft** = category not refund/complaint, evidence `supported` where needed, no sensitive keyword (legal, GDPR, fraud, …), no injection signal, not ambiguous, Knowledge Brain reachable.
* **Unchanged** = human approved and text equals the draft after whitespace normalisation. Corrected category counts as a change.
* **Streak** = consecutive eligible drafts of a category approved unchanged. An eligible draft that is edited, replaced or rejected resets it to 0; ineligible drafts neither count nor reset.
* **Eligible category** = streak ≥ 20 (configurable). **Revoked** by an edited/rejected eligible draft, a `bad` feedback outcome, or a failed evaluation; restarts from 0.
* Refunds and complaints are **never** eligible. Even when eligible and `AUTO_SEND_ENABLED=true`, "sending" writes a row to a simulated outbound queue.

## 8. Model selection
Claude is the primary model via the Anthropic SDK; the model id comes from `ANTHROPIC_MODEL` (nothing hard-coded, since availability varies by account).
`AIClient` centralises timeout, bounded retries, token/latency logging, and cost only when prices are configured. `scripts/benchmark_models.py` compares two model ids
on the same 56-email classification set; **no comparison has been run** (no credentials in the build environment).

## 9. Human approval and safety
Drafts and proposals are suggestions. Reviewers approve/edit/reject in the dashboard; proposal approval is internal and returns `dispatched_to_client: false`.
Emails and transcripts are scanned for injection patterns and are passed to the model as quoted data; flagged emails require review. Secrets only via environment; logs are JSON lines containing no keys.

## 10. Failure handling
KB down → Task 2 drafts a safe holding reply flagged for review; Task 3 marks findings `unavailable` and warns. Scrape failures and image failures are recorded per page without aborting ingest;
ingest resumes from stored progress; crawling honours robots.txt, delays, and retries. Empty/short/truncated transcripts are flagged, not invented. Live-model errors fall back to the demo path with a visible label.

## 11. Known limitations
Keyword heuristics miss paraphrased requirements and can add spurious ones (e.g. "we still need to see designs" in sample 1 becomes a requirement); a rephrased change in a follow-up
can be classified "added" instead of "modified". Demo hours are illustrative only. Not verified: live Claude, live-site crawl, image understanding, Docker. No auth, single-node SQLite.

## 12. Future improvements
Embeddings + hybrid retrieval; reviewer authentication; export to Word/PDF; calibrated estimates from past projects; per-category evaluation datasets for auto-send revocation; richer evaluation of live drafts.
