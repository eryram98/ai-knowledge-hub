# AGENTS.md: working rules for AI Knowledge Hub

Capstone (BUAN/MIS 6399, Fall 2026) for sponsor MSE Technology. It is a governed,
shared knowledge layer, not a chatbot: the Streamlit UI, the REST API and the
routing Knowledge Agent all consume the same layer. Team: Ethan (Member A, LLM and
backend) and Erynn (Member B, repo owner, sponsor contact) write code. Benson and
Nityanand are non-technical PMs.

- `docs/SPEC.md` is the source of truth: goal, stack, constraints, architecture,
  feature list with "Done when", and milestone checklists.
- `docs/PROGRESS.md` is the running log: task status, current feature, decisions,
  deviations, known issues, open questions, evaluation numbers, AI-written code.
- If SPEC.md and anything else disagree, SPEC.md wins. If SPEC.md looks wrong, say so
  and ask. Don't silently work around it.

## Session start (every session, before changing anything)

1. Read `AGENTS.md`, `docs/SPEC.md` and `docs/PROGRESS.md` (kept under 150 lines: Now,
   features, current decisions, known issues, open questions, AI-written code).
   - Don't read `docs/PROGRESS_ARCHIVE.md` (full session logs, older decision detail)
     unless you need that detail. Then Grep it and read only the matching lines.
2. Run `git status`. Then, if the branch has an upstream, run `git pull --ff-only`;
   otherwise run `git fetch` and say the branch is local-only.
3. Run the checks (see Commands).
4. Report the branch, any uncommitted changes, and any check failure before you
   touch code. Don't fix a pre-existing failure without saying so first.

## Commands (Windows, PowerShell, repo root)

- Python is 3.11 in the project `.venv`. Always call it explicitly:
  `.venv\Scripts\python`.
- Install dependencies: `.venv\Scripts\python -m pip install -r requirements.txt`
- Checks (all must pass):
  - Tests: `.venv\Scripts\python -m unittest discover -s backend\tests`
  - UI tests, including the Streamlit smoke test (the app starts headless):
    `.venv\Scripts\python -m unittest discover -s ui\tests`
  - Lint (Ruff, rules E and F, config in `ruff.toml`): `.venv\Scripts\python -m ruff check backend ui`
- PowerShell has no `<` redirection. Pass files as arguments.
- Run commands non-interactively and with a timeout. Only kill processes you
  started.

## Git

- Branches are named `ethan/<feature>`. Until the stack merges into `main`, base
  each new branch on the newest branch in the stack listed in PROGRESS.md.
- Never commit to `main`. Never force-push. Never push, merge or open a PR without
  asking first.
- Never commit Ethan's uncommitted edits or anyone else's. If the working tree has
  changes you didn't make, stop and ask.
- Commit messages use conventional prefixes (`feat:`, `fix:`, `test:`, `docs:`,
  `chore:`), unless Ethan dictates the exact message.
- Commit at the end of every feature. If you have to stop early, commit as
  `wip: ...` and write in PROGRESS.md exactly what's done, what isn't, and the next
  step.

## Two work modes

**Plumbing: just build it.** This covers API handlers, wiring the worker, persistence,
embedding and index plumbing, the LLM provider, upload and status UI, config, error
handling, scripts and tests.

**Coach mode.** Ethan must defend these in the graded oral Q&A:
- the Table Challenge approach
- the chunking and indexing strategy recommendation
- the hybrid merge (RRF) and re-ranking
- query routing in the Knowledge Agent

**Pause (decided by Ethan, 2026-10-22, because of time):** coach mode is paused for
query routing (`route()`) and all remaining MVP work (F4-F6) until after the Oct 27
progress report. Until then Claude builds those pieces like plumbing and lists them in
PROGRESS.md's AI-written code list. After Oct 27, coach mode resumes for F7-F9 (re-ranking,
the Table Challenge, the strategy recommendation), and Ethan reviews and may rewrite
`route()`. `docs/ROUTER_EXPLAINED.md` is his starting point for that.

For a coach-mode piece:
- Never write the implementation, even if asked casually mid-task. If a request
  would implement one of these, point that out and offer coaching instead.
- Explain options (with a comparison table: retrieval quality, index size, latency,
  cost, laptop feasibility), review Ethan's code, point out bugs, ask guiding
  questions, and suggest test cases.
- Write interfaces (signatures, docstrings, `raise NotImplementedError`) and tests
  around them only when Ethan explicitly asks, or when SPEC.md's feature
  description explicitly asks for them (F3 merge interface, F4 router interface).
- Give hints only when Ethan asks for them.
- When a choice is made, record it with `/decide`. After the piece is done, ask
  Ethan one likely professor or interviewer question about it.

## Feature workflow

1. One feature at a time, in the order in SPEC.md.
2. Before coding, add a short plan for the feature to PROGRESS.md under "Current
   feature": the files to touch and the risks.
3. Build it with tests. Add tests with every feature.
4. Done means every check passes, and you ran them yourself. Fix failures yourself.
5. Finish with `/finish-feature`. It updates PROGRESS.md, commits, and prints the
   end-of-session summary.

## Quality rules

- No placeholders, no TODO stubs, no UI element that does nothing.
- Never break an existing feature.
- Never delete or weaken a test without asking. If you change a test, explain why
  it is no weaker.
- Errors use the canonical codes in `backend/app/ingestion/ingestion_error_model.py`.
  Don't invent new error formats. A new code goes in that module.
- Lifecycle states come only from `ingestion_status_constants.py`.
- Keep `PdfTextExtractor` (plain pypdf) and `FixedSizeCharChunker` as the Table
  Challenge baseline. New extractors and chunkers register beside them on the
  dispatcher or by chunker name. They never replace them.
- Tests that open SQLite must use `with closing(sqlite3.connect(path)) as conn, conn:`.
  Otherwise Windows can't delete the temp database (WinError 32).
- Imports inside the backend use `from ingestion.<module> import ...` (and the same
  pattern for new packages), with `backend/app` on `sys.path`. Each test file adds
  `backend/app` to `sys.path`.
- `requirements.txt` (repo root) lists direct dependencies only. Never paste a full
  `pip freeze`.
- Streamlit is a pure HTTP client of the FastAPI backend. It must never import
  backend modules.
- Erynn wrote the modules from tasks 1-3 (config, errors, metadata contract, queue,
  worker, status repository and service, upload service). You may change them when a
  feature needs it, but list every such change in the summary so Ethan can tell her.

## Ask before

- adding a dependency (including dev tools)
- any schema change (SQLite tables or columns) or vector-store change (collection
  layout, embedding model, distance metric). There are no migrations: a schema change
  means deleting the git-ignored dev DB, so say so.
- changing an agreed prompt
- destructive actions (deleting files or data, resetting branches, dropping the DB or
  the Chroma directory)
- expensive decisions that are hard to undo either way
- any run that makes more than 20 LLM calls. Give an estimate of calls, tokens and
  cost first.
- sending personal information to any external service

For smaller calls: decide, log the call in the PROGRESS.md decision log, and mention it
in the summary.

## Data, secrets and cost

- Keys live in `.env` (git-ignored). Keep `.env.example` committed and current.
- Never commit `data/corpus/` files (only `data/corpus/MANIFEST.md`), extracted text,
  embeddings, the Chroma directory, or SQLite files.
- All documents are public. No sponsor documents.
- Cost target is $0 (Gemini free tier), with a hard cap of about $10 for the semester.
- Tests never call a real LLM or a network service. Mock the LLM provider in every
  test.

## UI changes

If a screenshot tool is available, screenshot the UI and check it yourself. Otherwise,
tell Ethan exactly what to click and what he should see.

## Keep PROGRESS.md current

- Newest first, and under 150 lines. Decisions are one line each. Session log entries,
  measurements and full decision reasoning go at the top of the "Session log (archived)"
  section of `docs/PROGRESS_ARCHIVE.md`. Move superseded decisions and resolved issues
  there too.
- Keep the "AI-written code" list current: every file or function you write or
  substantially change goes in it.
- Record decisions, deviations from SPEC.md, known issues and evaluation numbers as
  they happen.

## End-of-session summary (use this format every session)

1. Updated task list with finished items marked
2. What's done, with commits and branch
3. Checks run with exact results, plus evaluation numbers if they changed
4. What changed in behavior, in plain language
5. Deviations from the spec, and test changes with reasons
6. Decisions that need Ethan or Erynn, numbered, each with your recommendation
7. What's unverified, and what Ethan should try by hand
8. Coach-mode items waiting for Ethan, with hints only if he asked

Be precise: say what you measured, what you assumed and what you couldn't verify.
List any changes to Erynn's modules under item 2.
