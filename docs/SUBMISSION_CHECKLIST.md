# GitHub submission checklist (manual steps – nothing has been pushed)
1. Unzip `dist/ai-tech-consultant.zip`; `cd ai-tech-consultant`. It contains `.git` with the commit history.
2. Confirm no secrets: `git grep -nE "sk-ant|api[_-]?key *= *[A-Za-z0-9]" -- . ':!*.example' ':!docs'` should print nothing; `ls -a | grep '^.env$'` should print nothing.
3. Run `./run.sh --install` (needs Python 3.10+), open http://localhost:8080, then in another terminal `python scripts/smoke_test.py` → all PASS.
4. Run `python scripts/run_evals.py` → 111 passed expected (36 + 36 + 39). Commit the refreshed `reports/eval_results.json` if numbers changed.
5. If you have a Claude key: copy `.env.example` → `.env`, set `ANTHROPIC_API_KEY` and a model id you have verified; restart; confirm the header shows LIVE. Optionally run `scripts/benchmark_models.py` and add the real results to `EVALS.md`. If not, leave "PENDING" as is.
6. If Docker is installed: `docker compose up --build` and check :8080 – then update README/EVALS from "not tested" to the real outcome.
7. Add your own prompts/decisions for Task 1 and 2 sessions to `AI_LOG.md` if you have them.
8. Create the GitHub repo yourself (private first), `git remote add origin <url>`, `git push -u origin HEAD`.
9. Submit the repo link plus the demo video.
