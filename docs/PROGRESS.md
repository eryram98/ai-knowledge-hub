# PROGRESS: running log

Newest first. Old detail gets summarized. Scope and "Done when" live in `docs/SPEC.md`.

## Now

- **Branch stack (unmerged, oldest first):** `feat/text-extraction` → `chore/claude-code-setup`
  → `feat/kb-id` → `feat/pipeline-baseline` → `ethan/project-setup` → `ethan/f1-api`.
  Base new branches on `ethan/f1-api` until the stack merges into `main`.
- **Current feature:** none. F1 (HTTP API) is done on `ethan/f1-api`.
- **Next concrete step:** start F2 (indexing) on `ethan/f2-indexing`, based on
  `ethan/f1-api`. First ask Ethan to approve the F2 dependencies (`sentence-transformers`,
  `chromadb`, `rank-bm25`) with exact pins, and settle the BM25 library (still open).
- **Ethan by hand:**
  - Your `.env` already has `it_policies,hw_datasheets`. Only its comment on line 11
    still points at the deleted `docs/decisions.md`.
  - Download public documents into `data/corpus/it_policies/` and
    `data/corpus/hw_datasheets/`, and list each one in `data/corpus/MANIFEST.md`.
  - Try the API by hand (see the session summary): start it, open `/docs`, upload a file.

## Countdown and risk (as of 2026-10-20)

- **7 days to the progress demo (2026-10-27). 49 days to the final demo (2026-12-08).**
- At risk:
  1. F1 is done. That leaves five one-session features (F2-F6) in 7 days, with no
     slack. If a day is lost, cut F6's eval script down to routing accuracy only, not
     the demo itself.
  2. F3 and F4 depend on Ethan's coach-mode code (the RRF merge and the router). The
     `/ask` endpoint can't be demoed until both exist. Start thinking about both
     designs now.
  3. F2 downloads bge-small (about 130 MB) and installs torch through
     sentence-transformers. That's a large first install on the demo laptop.
  4. The corpus doesn't exist yet: `data/corpus/` is empty, and F2 manual testing and
     F6 need real documents.
  5. Gemini free-tier quotas during rehearsal and the demo (see the SPEC fallbacks).

## Features

| # | Feature | Status | Branch | Commit |
|---|---|---|---|---|
| F0 | Project setup: AGENTS.md, SPEC.md, PROGRESS.md | Done | `ethan/project-setup` | `f8be5c7` |
| F1 | HTTP API (+ Ruff, slim FastAPI, real KB IDs) | Done | `ethan/f1-api` | `1693e82`, `f077c3c`, `4e7eae5` (chores), this commit |
| F2 | Indexing: bge-small, Chroma and BM25 per KB | Next | | |
| F3 | Retrieval plumbing + merge interface (RRF by Ethan, coach) | To do | | |
| F4 | `/ask`: routing (Ethan, coach), grounded Gemini answer, sources | To do | | |
| F5 | Streamlit UI: Documents and Ask pages | To do (Erynn likely) | | |
| F6 | Demo readiness: seed, eval set and script, demo script, fallbacks | To do | | |
| F7 | Re-ranking (coach) | After Oct 27 | | |
| F8 | Table Challenge (coach) | After Oct 27 | | |
| F9 | Strategy recommendation (coach) | After Oct 27 | | |
| F10 | Duplicate handling | After Oct 27 | | |
| F11 | Certified questions and Judge Agent | After Oct 27 | | |
| F12 | Token and cost tracking | After Oct 27 | | |
| F13 | Provenance and freshness indicator | After Oct 27 | | |

### Done before this log (carried over from the old docs/tasks.md)

| Work | Who | Branch | Commits | Tests after |
|---|---|---|---|---|
| Tasks 1-3: lifecycle states, config, error model, metadata and stage contracts, upload intake and validation, queue, worker, status repository and service, failure isolation (old 1.1-1.5, 2.1-2.5, 3.1-3.6, 6.1, 6.4, 8.5) | Erynn | `main` (PR #1) | `294b052`, `f10217f`, `07ddd77` | 66 |
| Text extraction: dispatcher, TXT (encoding-safe), MD (raw), pypdf PDF baseline, normalized payloads, canonical extraction errors (old 4.1-4.6) | Ethan | `feat/text-extraction` | `ee39d42` | |
| Windows fix: tests close SQLite connections | Ethan | `feat/text-extraction` | `2faa164` | 92 |
| Claude Code setup: CLAUDE.md, `/decide`, `/finish-feature`, task list, decision log | Ethan | `chore/claude-code-setup` | `2649814` | 92 |
| `kb_id` in metadata, SQLite (indexed) and upload intake; `unknown_kb` code; `@abstractmethod` fix in stage contracts; WAL mode (old 1.6, 1.7, 2.6) | Ethan | `feat/kb-id` | `2e44595`, `a4de6dc` | 112 |
| Fixed-size char chunker (baseline), full-text and chunk persistence (idempotent, keyed by chunker), `DocumentProcessor` in the worker, `empty_content` code, `error_code` on failures, end-to-end TXT/MD/PDF test (old 5.1, 5.2, 6.2, 6.5; 6.3 and 8.3 partial) | Ethan | `feat/pipeline-baseline` | `4feb83c` | 142 |

### Where the open items from the old task list went

| Old task | Now |
|---|---|
| 8.1 API contracts, 8.2 HTTP upload, 8.3 enqueue accepted uploads + real worker entrypoint, 8.4 inventory and status endpoints, 8.10 consistent API errors, 8.13 KB inventory | F1 (8.13's enable/disable is deferred: not in the MVP) |
| 5.3 embeddings, 5.4 BM25 per KB, 5.5 links between documents, chunks and indexes, 5.7 vector index per KB, 6.3 embedding and index references | F2 |
| 8.6 retrieve with embeddings and keywords, 8.6a merge (RRF, coach) | F3 |
| 8.7 grounded answers, 8.8 question endpoint with sources, 8.9 no-answer path, 8.12 routing (coach) | F4 |
| 9.1-9.11 UI | F5 |
| 8.6b re-ranking (coach) | F7 |
| 4.7 table-aware extractor, 5.6 table-safe chunker, 10.1-10.3 Table Challenge test | F8 |
| 4.8 strategy recommendation, 9.12 show it in the UI | F9 |
| 7.1, 7.2, 7.4 duplicates (7.3, 7.5, 7.6 stay deferred) | F10 |
| M6: certified questions, Judge Agent, provenance, freshness | F11, F13 |
| M7: token and cost per query and per KB | F12 |
| 8.11 manual retry hooks | Deferred, not scheduled |

## Session log

- **2026-10-20 · Ethan + Claude · `ethan/f1-api` · F1.**
  - Chores: added Ruff (rules E and F, line length 120, E402 ignored in tests) and
    fixed what it flagged with no behavior change; slimmed FastAPI dependencies
    (verified in a fresh venv built only from requirements.txt); replaced the
    placeholder KB IDs.
  - F1: new `backend/app/api/` package (app factory, lifespan worker, upload storage,
    canonical errors), five endpoints, and re-enqueue of queued documents on startup.
  - Tests: 178 OK (142 before plus 36 new) in `.venv` and in the slim scratch venv. Ruff
    is clean.
  - Manual checks: the documented uvicorn command starts and `/kbs` answers. Under
    real uvicorn on a temp DB, a TXT, MD and PDF reached `success`, a body over the
    cap got 413 in 0.22 s, and a graceful shutdown left no worker thread.
- **2026-10-20 · Ethan + Claude · `ethan/project-setup` · F0.**
  - Audited the repo and ran the checks: 142 tests OK, under both the global Python
    3.11.9 and `.venv`.
  - Added AGENTS.md, SPEC.md and this file. CLAUDE.md is now `@AGENTS.md`.
  - Updated `/decide` and `/finish-feature`, and deleted `docs/tasks.md` and
    `docs/decisions.md`.
  - Git-ignored `data/corpus/` (except MANIFEST.md), SQLite files and Chroma.
  - No backend code changed.

## Decision log

Newest first. The 2026-10-20 decisions were made by Ethan in the setup session
unless marked "(Claude, small call)".

| Date | Decision | Choice | Alternatives ruled out (why) | Owner |
|---|---|---|---|---|
| 2026-10-20 | Paths in API responses | `temp_file_path` is stripped from every API response. It stays in the service-layer result for the worker. A test checks that no response contains it or the local upload path. | Return it unchanged (it leaks an absolute local path) | Ethan |
| 2026-10-20 | Re-enqueue on startup | Documents still `queued` in SQLite are re-enqueued when the app starts, oldest first. A queued row with no stored file is skipped with a warning. | No re-enqueue (why: not recorded) | Ethan |
| 2026-10-20 | `POST /documents` status code | 202 with per-file results whenever the request itself is valid, even if every file was rejected. Request-level errors (unknown KB, batch limit, body over the cap) return the canonical error. | Return the shared code's status (for example 413) when no file is accepted, which drops the per-file list (why: not recorded) | Ethan |
| 2026-10-20 | Upload size enforcement | ASGI middleware caps the whole request body while it streams in (413 when over `max_files_per_batch × max_size + 1 MB`), plus a per-file chunked copy that stops at the limit and deletes the partial file | Own streaming multipart parser with python-multipart for a true per-file streaming limit (why: not recorded) | Ethan |
| 2026-10-20 | F1 dependencies | `fastapi==0.142.2`, `uvicorn==0.54.0`, `python-multipart==0.0.32`, `httpx==0.28.1` (TestClient), `ruff==0.17.1`. Verified in a scratch venv; `.venv` left alone. | Also uninstall the `[standard]` extras from `.venv` (why: not recorded) | Ethan |
| 2026-10-20 | Ruff line length | 120. E402 is ignored in `backend/tests/*` because of the required `sys.path` insert. | 88 (default): 203 long-line hits to rewrap (Claude, small call) | Ethan |
| 2026-10-20 | Not-found error code | New canonical code `not_found` for unknown documents and unknown routes | | Ethan (Claude, small call) |
| 2026-10-20 | Stored file name | Metadata `original_filename` is the sanitized base name. The client's directory parts are dropped. | | Ethan (Claude, small call) |
| 2026-10-20 | Batch status route | `GET /documents/status?document_id=...`, registered before `/documents/{id}` | | Ethan (Claude, small call) |
| 2026-10-20 | Ingestion source for API uploads | Keep `"UI"`. The API can't tell Streamlit uploads from direct API calls, so the metadata contract is unchanged. | Add an `"API"` source (Claude, small call) | Ethan |
| 2026-10-20 | Eval set location | `data/eval/eval_set.jsonl`, committed, one JSON object per line | CSV (awkward for lists of KBs and long answers) (Claude, small call) | Ethan |
| 2026-10-20 | Chroma location | `backend/instance/chroma/`, next to the SQLite dev DB, git-ignored | Repo-root `chroma/` (scatters local state) (Claude, small call) | Ethan |
| 2026-10-20 | Session-start pull | `git pull --ff-only` only when the branch has an upstream, otherwise `git fetch` | Plain `git pull` (fails on local-only branches, can create merge commits) (Claude, small call) | Ethan |
| 2026-10-20 | FastAPI packaging | Slim `fastapi` + `uvicorn` + `python-multipart` (in F1) | `fastapi[standard]` (pulls in sentry-sdk, opentelemetry, fastapi-cloud-cli) | Ethan |
| 2026-10-20 | Real KB IDs in code | F1 replaces `kb_placeholder_a/b` with `it_policies,hw_datasheets` in config, `.env.example` and tests. Ethan edits his own `.env`. | Keep placeholders until PM confirmation (the demo needs real IDs; still config-driven) | Ethan |
| 2026-10-20 | `Project Scope.pdf` in `backend/app/uploads/` | Leave it; ask Erynn | Untrack it now (her file) | Ethan |
| 2026-10-20 | Linter | Ruff, rules E and F, as a chore commit at the start of F1 | Ruff in the setup commit (would touch code in a no-code session); no linter | Ethan |
| 2026-10-20 | Python environment | Python 3.11 in the project `.venv` | Global Python (drifted from the pins: FastAPI 0.115.12 installed vs 0.142.2 pinned); Python 3.6 (Chroma, sentence-transformers and Streamlit need 3.9+) | Ethan |
| 2026-10-20 | Workflow | AGENTS.md rules, SPEC.md as the source of truth, PROGRESS.md as the log, `ethan/<feature>` branches, ask before push, merge or PR | Old CLAUDE.md + tasks.md + decisions.md | Ethan |
| 2026-10-20 | Cost limit | $0 target (free tier), hard cap about $10 for the semester, ask before any run over 20 LLM calls | | Ethan |
| 2026-10-20 | Corpus | All public documents, downloaded by hand into `data/corpus/<kb_id>/` (git-ignored). Only `MANIFEST.md` is committed. | Sponsor documents (not allowed) | Ethan |
| 2026-10-20 | Database | SQLite, single writer, local, no migrations: a schema change means deleting the dev DB. WAL mode lets status reads run during worker writes. | Supabase/Postgres: there is a single writer and only small metadata, and the sponsor requires laptop-local reproducibility. The repository class keeps a later Postgres swap to one class. | Ethan |
| 2026-10-20 | API framework | FastAPI | Flask: FastAPI has built-in request validation and an automatic `/docs` page for demoing endpoints, and an earlier branch (`feature/ingestion`) already used it. | Ethan |
| 2026-10-20 | Front end | Streamlit, an HTTP-only client of the API (so the API stays the platform), polling through `st.fragment(run_every=...)`. Erynn likely builds it. **Deviation** from the Phase 1 deck's JavaScript UI; the sponsor approved flexibility. | React+Vite (more build work); plain HTML/JS (thin demo). Python-only means faster delivery. | Erynn |
| 2026-10-20 | LLM | Gemini Flash (current model in AI Studio's list) through the Gemini API free tier, key `GEMINI_API_KEY`, behind a provider interface (Claude Haiku or Ollama via `.env`), mocked in all tests, 429 retry with backoff, limit shown in the UI. $0 cost, and it returns token usage for cost tracking. | Local Ollama: slow on a laptop CPU, weaker at grounded citation, no usage counts. Paid hosted APIs: Claude Pro and Gemini Pro subscriptions don't include API access. | Ethan |
| 2026-10-20 | Vector store and keyword search | Chroma, persistent on disk, one collection per KB (maps directly to independent KBs), with metadata filtering; BM25 per KB | FAISS (we'd build persistence and per-KB filtering ourselves); Qdrant (needs Docker or a server); sqlite-vec (young) | Ethan |
| 2026-10-20 | Embedding model | `BAAI/bge-small-en-v1.5`, local via sentence-transformers. Runs on CPU, 512-token limit, 384 dimensions. | all-MiniLM-L6-v2: 256-token limit, borderline for ~250-token chunks, and weaker retrieval at the same 384 dimensions. Hosted embeddings: cost, and internet access on every re-index. | Ethan |
| 2026-10-20 | KB topics | KB1 `it_policies` = public university IT policies and procedures; KB2 `hw_datasheets` = public hardware datasheets. Pending PM confirmation, so config-driven. | | Ethan |
| 2026-10-20 | Demo flow | (1) both KBs and their docs, (2) upload and watch status, (3) one question per KB with routing and sources, (4) off-topic "not in the KB", (5) table baseline failure as motivation | | Ethan |
| 2026-10-20 | MVP scope for Oct 27 | Upload PDF/TXT/MD into one of two KBs → status → ask without choosing a KB → routing → hybrid retrieval (BM25 + vector, RRF) → LLM answer with sources and routed KB. Re-ranking, the Table Challenge and the strategy recommendation come after Oct 27. | | Ethan |
| 2026-10-14 | Build approach for the progress demo | AI-assisted MVP, then the team rebuilds and extends it | Hand-build everything (not feasible by Oct 27) | Team |
| 2026-10-14 | AI split | AI builds the plumbing. Ethan writes the core pieces (Table Challenge, strategy recommendation, hybrid merge and re-rank, routing) with coaching. | Full AI build (team couldn't defend the core pieces in the oral Q&A) | Ethan |
| 2026-10-14 | PDF baseline extractor | pypdf text layer, no OCR | (baseline only; the table-aware method is decided separately in F8) | Ethan |

Still open (decide when the feature needs it): Table Challenge approach (F8, coach), re-ranker
model (F7, coach), BM25 library (F2, `rank-bm25` proposed), PR review and CI workflow with
Erynn, `httpx` vs `httpx2` for TestClient (see Known issues).

Correction to the 2026-10-20 "FastAPI packaging" row: slim `fastapi` 0.142 still depends on
`opentelemetry-api` (the small no-op API package). The `[standard]` extras that are now gone
are sentry-sdk, the opentelemetry SDK and exporters, fastapi-cli and fastapi-cloud-cli.

## Deviations from the spec or the Phase 1 deck

- **UI is Streamlit, not JavaScript** (Phase 1 deck). The sponsor approved flexibility.
  Streamlit is HTTP-only, so it could be swapped out later.
- **The setup commit message** ("Project setup: AGENTS.md, SPEC.md, PROGRESS.md") is not a
  conventional commit. Ethan chose it.

## Known issues

- Starlette 1.7 (in `.venv`) warns that using `httpx` with its TestClient is deprecated
  and suggests `httpx2`. It's only a warning, and tests pass. Starlette is transitive and
  unpinned: the scratch venv resolved 1.9.0. Decide `httpx` vs `httpx2` before Starlette
  removes httpx support.
- `backend/tests/test_task1_ingestion_core.py` contains `# ... existing code ...` markers
  and one test. It has looked like that since Erynn's first commit (`294b052`), so tests may
  have been lost in an AI edit. Ask Erynn.
- The in-memory queue isn't durable. A document that is `processing` when the process
  dies stays `processing` forever, because the lifecycle has no processing → queued
  transition. Queued documents are re-enqueued on startup.
- The request-size cap is per request (`max_files_per_batch × max_size + 1 MB`, about
  501 MB with the defaults). The per-file limit is enforced while the file is copied out of
  Starlette's spool, not while it arrives over the network.
- The global Python 3.11.9 has drifted from the pins (FastAPI 0.115.12, python-multipart
  0.0.6). The project `.venv` matches the pins (FastAPI 0.142.2, pypdf 6.20.1). Always
  use `.venv\Scripts\python`.
- The module headers say "Python 3.6 compatible", and `.idea/misc.xml` (tracked) points
  at a "Python 3.6 (venv)" SDK. The real target is 3.11. Fix the headers when touching
  those files, and don't rewrite them in bulk.
- Test output prints pypdf "invalid pdf header" and "EOF marker not found" lines. This
  is expected noise from the corrupt-PDF tests, not a failure.

## Open questions

For Erynn:
1. `backend/app/uploads/Project Scope.pdf` is tracked in git, and you added it on
   2026-10-10. Is it sponsor or course material? If so, it conflicts with the
   public-data-only rule. *Recommendation:* untrack it and ignore `backend/app/uploads/`.
2. Please switch your interpreter to Python 3.11 with a project `.venv`. PyCharm
   currently points at "Python 3.6 (venv)", and Chroma, sentence-transformers and
   Streamlit need 3.9 or later. *Recommendation:* yes, before F2 lands.
3. `.idea/` is tracked, so machine-specific IDE settings are in the repo.
   *Recommendation:* untrack it and add `.idea/` to `.gitignore`.
4. Will you build the F5 Streamlit UI? F1's API contract is in SPEC.md section 2 and at
   `/docs`. *Recommendation:* review the endpoints and the F1 changes to your modules
   (listed in the F1 session summary) before F5.
5. The stack of four unmerged branches is growing. *Recommendation:* review and merge
   it into `main` soon, oldest first, so new work bases on `main` again.

For Ethan:
6. The old CLAUDE.md listed MCP as a consumer of the knowledge layer, but no feature
   schedules it. *Recommendation:* document it as future work for Dec 8, unless the
   sponsor asks for it.
7. Have the PMs confirmed the KB topics? Confirmation changes only config and the
   corpus, not code.
8. Please confirm the AI-written code list below. The pre-2026-10-20 entries are
   inferred from commit messages and the 2026-10-14 decisions.
9. The decision log has "Not recorded" reasons for four of your F1 choices: re-enqueue,
   the 202 status, size enforcement and leaving `.venv` alone. Please give the reasons
   you'd defend.

## Evaluation numbers

| Date | Commit | Eval set size | Routing accuracy | Hit@5 | Faithfulness | Notes |
|---|---|---|---|---|---|---|
| | | | | | | No runs yet. The first run is in F6. |

## AI-written code

Every file or function written or substantially changed by an AI assistant. Ethan's
coach-mode code is never on this list.

| Date | Files | Tool | Reviewed by | Notes |
|---|---|---|---|---|
| 2026-10-20 | `backend/app/api/api_app.py`, `api_errors.py`, `api_uploads.py`; tests `test_api_documents.py`, `test_api_uploads.py`, `test_ingestion_inventory.py`; `list_documents` and `count_documents_by_kb_and_status` in the status repository; `list_documents` and `_status_from_record` in the status service; `document_id`, `new_document_id` and `resolve_kb_id` in the upload service; `not_found` in the error model; `ruff.toml`; Ruff fixes in 4 test files and `ingestion_status_constants.py`; KB defaults; requirements.txt | Claude Code | Ethan (to review) | F1 |
| 2026-10-20 | `AGENTS.md`, `CLAUDE.md`, `docs/SPEC.md`, `docs/PROGRESS.md`, `.claude/skills/decide/SKILL.md`, `.claude/skills/finish-feature/SKILL.md`, `.gitignore` additions, `data/corpus/MANIFEST.md` | Claude Code | Ethan | Docs and config only |
| 2026-10-15 | `ingestion_chunking.py`, `ingestion_artifact_repository.py`, `ingestion_pipeline.py`, worker wiring, related tests (`4feb83c`) | Claude Code (inferred) | Ethan | To confirm |
| 2026-10-15 | `kb_id` changes in metadata contract, status repository, upload service, config, stage contracts, tests (`2e44595`) | Claude Code (inferred) | Ethan | To confirm |
| 2026-10-15 | CLAUDE.md, skills, task list, decision log (`2649814`) | Claude Code (inferred) | Ethan | Replaced by this setup |
| 2026-10-14 | `ingestion_text_extraction.py`, `pdf_fixtures.py`, extraction tests, SQLite test fix (`ee39d42`, `2faa164`) | Claude Code (inferred) | Ethan | To confirm |
| 2026-10-10 to 10-14 | Tasks 1-3 modules and tests (`294b052`, `f10217f`, `07ddd77`) | AI agent, per the commit message of `294b052` | Erynn | Erynn to confirm how much |
