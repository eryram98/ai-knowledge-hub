# AI Knowledge Hub

Capstone project (BUAN/MIS 6399, Fall 2026) for sponsor MSE Technology. A shared,
governed knowledge layer, not a chatbot: the chat UI, a REST API, MCP and a routing
Knowledge Agent all consume the same layer.

Team: Ethan and Erynn write code. Erynn owns this repo and is the sponsor contact.

## What the demo must show (sponsor minimum)

1. Two separate, independently searchable knowledge bases (KBs) built from public PDF, TXT and MD files.
2. A displayed chunking and indexing strategy recommendation per document.
3. One working Table Challenge approach, measured against the naive baseline.
4. Hybrid retrieval: keyword (BM25) plus vector search, merged (for example Reciprocal Rank Fusion), then re-ranked.
5. A routing Knowledge Agent that picks the right KB or KBs without the user choosing.
6. Grounded answers with visible sources.
7. Later milestones: certified questions, a Judge Agent, provenance, a freshness indicator, and token and cost visibility.

Out of scope (document as future work, do not build): graph retrieval, SQL or spreadsheet
querying, RBAC, Azure deployment, production security.

## Repo layout

- `backend/app/ingestion/`: pipeline modules. Imports use `from ingestion.<module> import ...`, with `backend/app` on `sys.path`.
- `backend/tests/`: `unittest` tests. Each test file adds `backend/app` to `sys.path`.
- `requirements.txt` (repo root): direct dependencies only. Do not paste a full `pip freeze`.
- `docs/tasks.md`: the task list. It is the source of truth for progress.
- `docs/decisions.md`: decision log.

## Commands (Windows, PowerShell, from the repo root)

- Run tests: `python -m unittest discover -s backend\tests`
- Install dependencies: `pip install -r requirements.txt`
- PowerShell has no `<` redirection. Pass files as arguments.

## Conventions

- One branch per feature (`feat/...`, `fix/...`, `chore/...`). Never commit directly to `main`.
- Use conventional commit messages: `feat:`, `fix:`, `test:`, `docs:`, `chore:`.
- All tests must pass before every commit. Add tests with every feature.
- Tests that open SQLite must close the connection with `with closing(sqlite3.connect(path)) as conn, conn:`. Otherwise Windows can't delete the temp database (WinError 32).
- Return errors as the canonical codes in `ingestion_error_model.py`. Do not invent new error formats.
- Lifecycle states come only from `ingestion_status_constants.py`.
- Keep `PdfTextExtractor` (plain pypdf) as the Table Challenge baseline. Add table-aware extraction as a separate extractor registered on the dispatcher. Do not replace the baseline.
- Secrets go in `.env`, which is git-ignored. Keep `.env.example` updated.

## Two work modes

**Plumbing: just build it.** This covers API handlers, wiring the worker to the pipeline,
persistence, upload and status UI, config, error handling and tests.

**Core pieces: coach mode.** Ethan must be able to defend these in the graded oral Q&A:
- The Table Challenge approach
- The chunking and indexing strategy recommendation
- Hybrid merge and re-ranking
- KB routing in the Knowledge Agent

For a core piece:
1. Explain two or three options in a comparison table: retrieval quality, index size, latency, cost, laptop feasibility.
2. Wait for Ethan to choose, then record the choice with `/decide`.
3. Write the interface skeleton (signatures, docstrings, `raise NotImplementedError`) and the tests first.
4. Ethan writes the core logic. Review his code, point out bugs, and explain any line he asks about.
5. Afterwards, ask him one likely professor or interviewer question about the choice.

## Open decisions: ask, never default

KB topics, embedding model, vector store, local or hosted LLM, and front-end
framework (the Phase 1 deck commits to a JavaScript UI, so don't default to Streamlit).
If a task needs one of these, stop and ask. Then record the answer with `/decide`.

## Finishing a feature

When a top-level task in `docs/tasks.md` is complete, run `/finish-feature`.
