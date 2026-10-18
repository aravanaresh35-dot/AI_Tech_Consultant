# AI Tech Consultant

Three connected services that help a small software agency: **Task 1 – Knowledge Brain** answers product questions from a help center
(with citations, expert escalation and change sync); **Task 2 – Inbox Agent** classifies customer emails and drafts replies grounded in Task 1,
with human review and a conservative auto-send rule; **Task 3 – Meeting to Scope of Work** turns meeting transcripts into a scope, hour estimate and
proposal, checking Task 1 for existing features first. A dashboard ties them together. Tasks 2 and 3 call Task 1 **only over HTTP**.

```
Dashboard :8080 ──► Knowledge Brain :8001 ◄── Inbox Agent :8002   (all Python / FastAPI / SQLite)
                         ▲
                         └──────────────── Meeting→SOW :8003
```

**Prerequisites:** Python 3.10+ (tested 3.12), `pip`. Optional: Docker, Node 18+ (UI test only).

**Run (one command, no Docker):**
```bash
cp .env.example .env      # optional; defaults work
./run.sh --install        # installs deps, starts 4 processes, loads demo knowledge base
```
Open **http://localhost:8080** (API docs: :8001/docs, :8002/docs, :8003/docs). Ctrl+C stops everything. Logs: `logs/`.
Docker alternative: `docker compose up --build` (**written but not tested** – see limitations).

**Tests:** `python scripts/run_evals.py` (runs all three suites + dataset accuracy, writes `reports/eval_results.json`; offline, no API key).
With services running: `python scripts/smoke_test.py` (end-to-end over HTTP). Details in `EVALS.md`.

**Demo mode vs live AI.** With no `ANTHROPIC_API_KEY`/`ANTHROPIC_MODEL` the system runs in **DEMO mode**: deterministic rules and templates, labelled
"DEMO" in every API response and in the dashboard header. No model is called and nothing is presented as Claude output. Set both variables
(a model id *you* have verified; none is hard-coded) to enable **LIVE** mode, where Claude is the primary model. Live mode has **not been tested** here.

**Safety defaults:** no email is ever sent (outbound is a simulated queue); proposals are never sent (approval is internal only); no price is invented
(set `HOURLY_RATE` for an *illustrative* figure); transcripts/emails are treated as untrusted data.

**Known limitations:** retrieval is BM25 keyword search (no embeddings); demo-mode estimates and requirement extraction are keyword heuristics, not
expert judgement; Task 2 is Python (the permitted fallback), not TypeScript; real-site crawling, image understanding, live Claude, benchmark comparison and
Docker are untested; the daily sync runs only if `SYNC_SCHEDULE_ENABLED=true`; no authentication (local/demo use only).
Docs: `DESIGN.md`, `EVALS.md`, `AI_LOG.md`, `docs/`.
