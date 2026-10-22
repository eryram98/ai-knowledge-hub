# PROGRESS: running log

Current state only, newest first. Scope and "Done when" live in `docs/SPEC.md`. Full session logs,
measurements and the reasoning behind older decisions are in `docs/PROGRESS_ARCHIVE.md`: don't read
it unless you need that detail, and then Grep it.

## Now

- **Branch:** F0-F4 merged into `main` (PRs #4-#6, `eba0e60`). `ethan/f5-ui` is local-only, from `eba0e60`.
- **Current feature:** F5 done (`3e557c8`), checked with screenshots against the real API and Gemini.
- **Next:** (1) Ethan pushes `ethan/f5-ui` and opens the F5 PR for Erynn. (2) F6: seed script, eval
  set and script, demo script, fallbacks. The dev DB already matches `data/corpus/`.
- **Ethan by hand:** upload a small TXT on the Documents page and watch Queued → Processing → Ready
  with the 2 s refresh stopping at the end (copy `backend/instance/` first to keep the seeded
  state); open a source card on Ask; stop the API and ask to see the start-command error. Fill
  in the blank URLs in `data/corpus/MANIFEST.md`; your `.env` line 11 points at the deleted
  `docs/decisions.md`.
- **Countdown (2026-10-22):** 5 days to the progress demo (2026-10-27), 47 to the final (2026-12-08).
  At risk:
  1. F6 remains. If a day is lost, cut the eval script to routing accuracy only.
  2. Gemini latency varies: `/ask` took 1-2 s in the morning but 6-29 s that night with no
     retries. Warm up with one question before the demo (it also loads bge-small, about 10 s).
  3. Free-tier quota: each `/ask` is 2 calls (off-topic 1); the F6 eval is about 16 calls.
  4. The install is about 1.6 GB with Streamlit, plus bge-small (128 MB). Cache both on the demo
     laptop early and use `HF_HUB_OFFLINE=1`.
  5. Baseline retrieval splits datasheet tables. Pick demo questions carefully.

## Features

| # | Feature | Status | Branch | Commit |
|---|---|---|---|---|
| F0 | Project setup: AGENTS.md, SPEC.md, PROGRESS.md | Done | `ethan/project-setup` | `f8be5c7` |
| F1 | HTTP API (+ Ruff, slim FastAPI, real KB IDs) | Done | `ethan/f1-api` | `1693e82`, `f077c3c`, `4e7eae5`, `1aeffe8`, `c1df404` |
| F2 | Indexing: bge-small, Chroma and BM25 per KB | Done | `ethan/f2-indexing` | `a922552` |
| F3 | Retrieval plumbing + merge interface (RRF by Ethan, coach) | Done | `ethan/f3-retrieval` | `2b0566e`, `c6bddbe`, `6123769` |
| F4 | `/ask`: routing (Claude to Ethan's design), grounded Gemini answer, sources | Done | `ethan/f4-ask` | `1aa5866`, `8f8f8cd`, `4fe7ab2`, `79b878e` (PR #6) |
| F5 | Streamlit UI: Documents and Ask pages | Done | `ethan/f5-ui` | `3e557c8` |
| F6 | Demo readiness: seed, eval set and script, demo script, fallbacks | To do | | |
| F7 | Re-ranking (coach) | After Oct 27 | | |
| F8 | Table Challenge (coach) | After Oct 27 | | |
| F9 | Strategy recommendation (coach) | After Oct 27 | | |
| F10 | Duplicate handling | After Oct 27 | | |
| F11 | Certified questions and Judge Agent | After Oct 27 | | |
| F12 | Token and cost tracking | After Oct 27 | | |
| F13 | Provenance and freshness indicator | After Oct 27 | | |

Earlier work (tasks 1-3 by Erynn, extraction, chunking, kb_id) and the old task-list mapping: see the archive.

## Decisions (current, one line each; reasoning and superseded rows in the archive)

- **Coach mode:** paused for `route()` and F4-F6 until after Oct 27; resumes for F7-F9, and Ethan reviews `route()` (Ethan, 2026-10-22).
- **AI split:** Claude builds the plumbing; Ethan writes the coach pieces (Table Challenge, strategy recommendation, RRF and re-rank, routing).
- **Stack:** Python 3.11 `.venv`; FastAPI (slim); SQLite, single writer, WAL, no migrations; Chroma per KB; BM25 per KB; bge-small on CPU; Gemini free tier behind a provider interface.
- **UI:** Streamlit as an HTTP-only client (a deviation from the Phase 1 deck's JavaScript UI; the sponsor approved flexibility). Owner: Ethan, built by Claude.
- **Cost:** $0 target, about $10 cap for the semester; ask before any run over 20 LLM calls.
- **Data:** public documents only in `data/corpus/<kb_id>/` (git-ignored), with `MANIFEST.md` committed; eval set at `data/eval/eval_set.jsonl`.
- **KBs:** `it_policies` and `hw_datasheets`, config-driven, topics pending PM confirmation; names and descriptions in `config/kb_descriptions.json`.
- **Workflow:** AGENTS.md rules, SPEC.md as the source of truth, `ethan/<feature>` branches off `main`, ask before push, merge or PR. Repo lives in `C:\dev` (not OneDrive).
- **F5 dependency:** `streamlit==1.65.0`; the UI's HTTP client is the already-pinned `httpx`.
- **F5 layout:** top-level `ui/` with pages in `ui/views/`, its own `ui/tests` check, and an AST test that bans backend imports.
- **F5 polling:** the status table refreshes every 2 s only while a document is queued or processing (an app rerun switches it on or off).
- **F5 settings:** `.streamlit/config.toml` turns usage stats off and sets `maxUploadSize = 25` to match `INGESTION_MAX_FILE_SIZE_MB`.
- **F5 Ask page:** latency measured in the UI; every source shown, cited first; `$` escaped; 180 s `/ask` timeout.
- **Model:** `gemini-3.5-flash-lite`, `minimal` thinking for both steps (`generate(..., thinking=)` sends Gemini's `thinking_level`), 20 s per-attempt timeout, all overridable in `.env`.
- **LLM retries:** 429, 503, 504 and network errors, `LLM_MAX_RETRIES` (3) with 2/4/8 s backoff, then 503 `llm_unavailable` with `Retry-After: 30`.
- **Router:** LLM classification from the KB descriptions with 4 few-shots and a JSON reply; an invalid reply falls back to every KB; examples only for configured KBs; no repair of bad ids.
- **`/ask` errors:** 501 until `route()` exists; 503 when the LLM stays unavailable; other LLM errors and a contract-breaking `route()` → 500.
- **`/ask` answer:** merged top 10 in the prompt; no hits → the no-answer sentence without a call; every prompted chunk returned with `cited` and a 300-character snippet.
- **Prompts:** the grounding prompt (`agent_answer.py`) and routing prompt (`agent_router.py`) are approved; changing either needs Ethan's approval.
- **Merge contract:** `merge_ranked_lists(ranked_lists, k=60, top_n=10)` → `fused_score` and `sources`, ties by `chunk_id`; ValueError for a bad `k` or `top_n`; repeats and extra fields not policed.
- **Vector filter:** Chroma `document_id $in` the `success` IDs, plus a SQLite check; ranks reassigned 1..n.
- **`/search`:** returns 200 with the raw lists when the merge fails (`merge_error`); `kb_ids` defaults to every KB; `top_k`/`top_n` 1-100.
- **Retrieval config:** `RetrievalConfig` (`RETRIEVAL_TOP_K`, 20), separate from Erynn's `IngestionConfig`.
- **Index layout:** collection `kb_<kb_id>`, cosine, our embedder only, the model name recorded and a mismatch refused; Chroma at `backend/instance/chroma/` beside the DB.
- **BM25:** chunks of `success` documents only, invalidated when a document finishes; a hit is any chunk sharing a query term.
- **Pipeline:** `DocumentProcessor` requires an indexer and marks success only after indexing.
- **Uploads:** 202 with per-file results; a request-body cap plus a per-file chunked copy; sanitized base names; `temp_file_path` never sent to clients; source stays `"UI"`.
- **Startup:** queued documents are re-enqueued; documents left processing are failed with `internal_failure` ("interrupted by server restart").
- **Lint:** Ruff rules E and F, line length 120, E402 ignored in `backend/tests`.
- **Dev DB:** rebuilt 2026-10-22 from `data/corpus/` without RP2040; duplicate policy is `allow`, so don't re-upload indexed files.
- **PDF baseline:** pypdf text layer, no OCR. `PdfTextExtractor` and `FixedSizeCharChunker` stay as the Table Challenge baseline.

## Known issues

- Chroma test flake: `InternalError: Error finding id` from `collection.query`, rare (about 1 in 10 full runs, more in looped API tests). Re-run; never seen on the real server.
- `gemini-3.8-flash` rejects `minimal` thinking (400; set both thinking variables to `low`). `gemini-2.5-flash` is listed but returns 404 for this key.
- The Gemini SDK seems to send the client timeout as the server deadline (unverified), so a call slower than 20 s becomes a retried 504.
- `AskApiTestCase` reads `.env`; setting the thinking variables there would break its assertions.
- With 3 or more KBs, the router fallback would exceed the 2-KB cap and `/ask` would return 500.
- `merge_ranked_lists` accepts a NaN or infinite `k` (not reachable from `/search`).
- The RPi 5 product brief (52.9 MB) is over the 25 MB limit, so it isn't indexed.
- The API never closes its Chroma client, so the Chroma directory can't be deleted while it runs.
- Loading bge-small online prints an HF Hub warning; `HF_HUB_OFFLINE=1` stops it.
- `EmbeddingStage`/`IndexingStage` in `ingestion_stage_contracts.py` are unused.
- Starlette warns that `httpx` with TestClient is deprecated (suggests `httpx2`).
- `test_task1_ingestion_core.py` has `# ... existing code ...` markers and one test (since `294b052`).
- The in-memory queue isn't durable: an interrupted document must be re-uploaded.
- The upload size cap is per request (about 501 MB by default); the per-file limit applies while copying.
- The global Python has drifted from the pins (always use `.venv\Scripts\python`). Module headers say "Python 3.6 compatible" and `.idea/misc.xml` points at 3.6; fix headers when touching files.
- The Linux torch instructions in SPEC §2 are untested.
- UI: the KB table on Documents refreshes only on a full rerun; the status table refreshes every 2 s while needed.
- UI: `ui/ui_messages.py` copies the error codes, so a new code needs a line there (otherwise the API's message shows).
- UI: `.streamlit/config.toml` is read only when Streamlit starts from the repo root, and its 25 MB must match `INGESTION_MAX_FILE_SIZE_MB`.
- `/ask` snippets can start mid-word (overlapping chunks); cosmetic.
- Expected test noise: pypdf "invalid pdf header"/"EOF marker" lines and Streamlit "missing ScriptRunContext" warnings.

## Open questions

For Erynn:
1. `backend/app/uploads/Project Scope.pdf` is tracked. If it's sponsor or course material, it breaks the public-data rule. *Rec:* untrack it and ignore the folder.
2. Switch your interpreter to Python 3.11 with a project `.venv` (PyCharm points at 3.6). *Rec:* yes.
3. `.idea/` is tracked. *Rec:* untrack it and add it to `.gitignore`.
4. Review the F5 PR (`ui/`), especially the Documents page. F4 added `name`/`description` to `/kbs` and the `llm_unavailable` code; F5 uses both.

For Ethan:
5. MCP isn't scheduled. *Rec:* document it as future work for Dec 8 unless the sponsor asks.
6. Have the PMs confirmed the KB topics? (Only config and corpus change.)
7. Confirm the AI-written code list; pre-2026-10-20 entries are inferred from commits.
8. Still open when the feature needs it: Table Challenge approach (F8), re-ranker model (F7), PR review and CI with Erynn, `httpx` vs `httpx2`, retiring the unused stage contracts.

## Evaluation numbers

| Date | Commit | Eval set size | Routing accuracy | Hit@5 | Faithfulness | Notes |
|---|---|---|---|---|---|---|
| | | | | | | No runs yet. The first run is in F6. |

## AI-written code

Every file or function written or substantially changed by an AI assistant. Ethan's own coach-mode
code is never on this list; coach pieces Claude wrote while coach mode was paused are.

| Date | Files | Tool | Reviewed by | Notes |
|---|---|---|---|---|
| 2026-10-22 | All of `ui/` (app, config, API client, messages, both views, 6 test files); `.streamlit/config.toml`; UI lines in `requirements.txt`, `.env.example`, `ruff.toml`; SPEC and AGENTS.md check edits; `/finish-feature` SKILL.md; this trim and `PROGRESS_ARCHIVE.md` | Claude Code | Ethan (to review), Erynn (PR) | F5 and docs |
| 2026-10-22 | 504 retry (`agent_gemini.py`); thinking and timeout config (`agent_config.py`); `thinking` in `answer_question`, **`route()`** and `/ask`; `.env.example`; tests in 6 agent/API test files; SPEC and ROUTER_EXPLAINED edits | Claude Code | Ethan (to review) | F4 reliability follow-up |
| 2026-10-22 | **`route()`** and the rest of `agent_router.py`; per-call `thinking` in `agent_llm.py` and `agent_gemini.py`; `FakeLlm.thinking_levels`; router, Gemini, LLM and `/ask` tests; `docs/ROUTER_EXPLAINED.md`; MANIFEST rows; AGENTS.md and SPEC edits | Claude Code | Ethan (after Oct 27; may rewrite `route()`) | F4 routing, coach piece built while paused |
| 2026-10-20 | `backend/app/agent/` (`agent_llm`, `agent_gemini`, `agent_config`, `agent_answer`, the `agent_router` interface); `config/kb_descriptions.json`; `POST /ask` and agent wiring in `api_app.py`; `Retry-After` and 501/503 in `api_errors.py`; `llm_unavailable`; agent and `/ask` tests; requirements LLM group; `.env.example` | Claude Code | Ethan (to review) | F4 plumbing |
| 2026-10-20 | `test_retrieval_merge.py`: `TestMergeArgumentValidation`, decorator cleanup, docstring (not the checks in `merge_ranked_lists`, which Ethan wrote) | Claude Code | Ethan (to review) | F3 RRF follow-up |
| 2026-10-20 | `test_api_search.py`: real-merge and patched not-implemented tests (not the `merge_ranked_lists` body, which Ethan wrote) | Claude Code | Ethan (to review) | F3 RRF |
| 2026-10-20 | `backend/app/retrieval/` (config, retriever, the merge interface only); `POST /search`; Chroma `document_ids` filter; `list_success_document_ids`, `get_chunk_hits`; `not_implemented`; retrieval and `/search` tests | Claude Code | Ethan (to review) | F3 |
| 2026-10-20 | `backend/app/indexing/` (four modules); indexing step in `ingestion_pipeline.py`; `list_kb_chunks`; worker `on_finished`; `indexing_failure`; F2 wiring in `api_app.py`; indexing tests and F2 test additions; requirements indexing group | Claude Code | Ethan (to review) | F2 |
| 2026-10-20 | `backend/app/api/` (`api_app`, `api_errors`, `api_uploads`); API and inventory tests; `list_documents` and counts in the status repository and service; upload service ID helpers; `not_found`; `ruff.toml`; Ruff fixes; KB defaults; requirements | Claude Code | Ethan (to review) | F1 |
| 2026-10-20 | `AGENTS.md`, `CLAUDE.md`, `docs/SPEC.md`, `docs/PROGRESS.md`, `/decide` and `/finish-feature` skills, `.gitignore` additions, `data/corpus/MANIFEST.md` | Claude Code | Ethan | Docs and config only |
| 2026-10-15 | `ingestion_chunking.py`, `ingestion_artifact_repository.py`, `ingestion_pipeline.py`, worker wiring, tests (`4feb83c`) | Claude Code (inferred) | Ethan | To confirm |
| 2026-10-15 | `kb_id` in metadata contract, status repository, upload service, config, stage contracts, tests (`2e44595`) | Claude Code (inferred) | Ethan | To confirm |
| 2026-10-15 | CLAUDE.md, skills, task list, decision log (`2649814`) | Claude Code (inferred) | Ethan | Replaced by this setup |
| 2026-10-14 | `ingestion_text_extraction.py`, `pdf_fixtures.py`, extraction tests, SQLite test fix (`ee39d42`, `2faa164`) | Claude Code (inferred) | Ethan | To confirm |
| 2026-10-10 to 10-14 | Tasks 1-3 modules and tests (`294b052`, `f10217f`, `07ddd77`) | AI agent, per `294b052` | Erynn | Erynn to confirm how much |
