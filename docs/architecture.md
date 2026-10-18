# Architecture

```
            ┌──────────── Dashboard (static HTML/JS, :8080) ────────────┐
            │ calls the three APIs directly from the browser (CORS on)  │
            ▼                         ▼                                  ▼
   Knowledge Brain :8001      Inbox Agent :8002                 Meeting→SOW :8003
   ingest/sync, BM25 search   classify → retrieve → draft       analyst → consultant → estimator
   chat, expert tasks         review, feedback, auto-send       → scope → proposal → validator
   SQLite kb.sqlite3          SQLite inbox.sqlite3              SQLite sow.sqlite3
            ▲                         │ HTTP /api/v1/search              │ HTTP /api/v1/search
            └─────────────────────────┴──────────────────────────────────┘
        shared/tech_common: KnowledgeBrainClient (timeout+retry), AIClient (demo/live), JSON logging
```
Data flow: customer email → Task 2 asks Task 1 for evidence → draft + evidence + review flags → human approves/edits/rejects → feedback row →
(only if rules allow) simulated outbound row. Transcript → Task 3 asks Task 1 per requirement → estimate/scope/proposal version → human approval (internal).
Each service owns its own SQLite file; there is no shared database.
