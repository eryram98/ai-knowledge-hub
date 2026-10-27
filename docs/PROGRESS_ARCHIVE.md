# PROGRESS archive: full history

Moved out of `docs/PROGRESS.md` on 2026-10-22 so sessions don't load it. Don't read this file
unless you need old detail (a past measurement, a decision's full reasoning, a session's steps).
Search it with Grep and read only the matching lines. Below is PROGRESS.md exactly as it was at
`3e557c8` (end of F5), including superseded decisions and resolved issues. New session log
entries go at the top of the "Session log (archived)" section below this line.

## Session log (archived)

New entries go here, newest first. The snapshot below keeps its own older session log.

### 2026-10-27: PROGRESS.md conflict fix (branch `docs/fix-progress-conflict`)

- Merge `73e5c63` left conflict markers in PROGRESS.md. Resolved by keeping both decisions; trimmed to under 150 lines. Moved here, as they stood:

Old Now / Countdown text:
  - **Branch:** `ethan/delete-document`, local-only, from `main` (`01b7a2a`, F0-F6 merged). Committed at the end of this session.
  - **Current feature:** delete a document (outside SPEC's F-list): `DELETE /kbs/{kb_id}/documents/{document_id}` plus a
    Delete section on the Documents page. Plan: status-repository delete in one transaction, then Chroma, BM25, upload dir;
    404 and 409 `document_busy`. Risks: the worker's own BM25 invalidate can land mid-delete (harmless).
  - **Branch:** `ethan/demo-launcher`, local-only, from `ethan/f6-demo` (F6 `3418beb` is not merged to `main` yet, so merge F6 first).
    Added `start_demo.bat`/`stop_demo.bat` (scripts in `scripts/`): double-click demo start and stop, see DEMO_SCRIPT "Quick start".
  - **Current feature:** F6 done: seed ran on the real API (7 of 8 files indexed, the RPi 5 brief rejected), eval ran once
    (routing 100%, hit@5 86%, see the table below). `scripts/`, `data/eval/eval_set.jsonl`, `docs/DEMO_SCRIPT.md`.
    and ask to see the start-command error. Your `.env` line 11 points at the deleted `docs/decisions.md`.
  - **Next (as of 2026-10-27, before this fix):** (1) Ethan pushes `ethan/f6-demo` and opens the F6 PR. (2) Record the backup video and screenshots; rehearse
    `docs/DEMO_SCRIPT.md` twice, including the q04 table step. (3) Fill in the blank MANIFEST URLs. (4) After Oct 27: F7 re-ranking.
  - **Ethan by hand:** upload a small TXT on the Documents page (`backend/instance_backup/` is your copy); stop the API
  - **Countdown (2026-10-22):** 5 days to the progress demo (2026-10-27), 47 to the final (2026-12-08).
    At risk:
    1. Demo rehearsal and the backup video remain.
    2. Gemini latency varies: `/ask` took 1-2 s in the morning but 6-29 s that night with no
       retries. Warm up with one question before the demo (it also loads bge-small, about 10 s).
    3. Free-tier quota: each `/ask` is 2 calls (off-topic 1); the F6 eval is about 16 calls.
    4. The install is about 1.6 GB with Streamlit, plus bge-small (128 MB). Cache both on the demo
       laptop early and use `HF_HUB_OFFLINE=1`.
    5. Baseline retrieval splits datasheet tables. Pick demo questions carefully.

Old F5/F6 decision lines:
  - **F5 (details in the archive):** `streamlit==1.65.0`; `ui/` is an HTTP-only client with its own tests; the status table polls every 2 s only while needed; `.streamlit/config.toml` sets 25 MB and no usage stats.
  - **F5 Ask page:** latency measured in the UI; every source shown, cited first; `$` escaped; 180 s `/ask` timeout.
  - **F6 scripts:** `scripts/` reuses `ui/ui_api_client.py` over HTTP. Seed asks before wiping, refuses while an API runs, and exits 1 only on a `failed` document (a rejected file is listed). Eval asks before the LLM calls.
  - **F6 metrics:** routing correct = routed set equals expected (`none` = empty, so a fallback to all KBs is wrong); hit@5 = every expected source among the first 5 sources, over on-topic questions only.

### 2026-10-26: demo launcher (branch `ethan/demo-launcher`, from `ethan/f6-demo`)

- Added `scripts/start_demo.ps1` (-Warmup), `scripts/stop_demo.ps1`, root `start_demo.bat`/`stop_demo.bat`, DEMO_SCRIPT "Quick start", `logs/` ignore. No app code changed; checks reused from session start (backend 354 OK/3 skipped, ui 41 OK, scripts OK, Ruff clean).
- Real run from another cwd: API and UI up, `/kbs` and `:8501` 200, PIDs file written. Second start refused naming the port holders, PIDs file untouched. Stop freed both ports and removed the file; a repeat stop says nothing to stop. Missing `.venv`, `.env` and empty key each exit 1 with a message (tested in a temp copy).
- Warm-up `/ask` took 77 s (Gemini slow, as on 10-22) and printed the backup-video warning. 2 real Gemini calls.

### 2026-10-22: F6 build (branch `ethan/f6-demo`)

- Built the seed and eval scripts, the 8-question eval set and `docs/DEMO_SCRIPT.md`. Checks on `main` before the work:
  354 backend tests OK (3 skipped), 40 UI tests OK, Ruff clean.
- Table probes (no baseline failure found): Pico Popcorn Table 1 average at 85 C, board 2 -> 89.8 mA (correct, 79 s);
  mean maximum at 25 C -> 91.6 mA (correct, 75 s); product guide RP2040 memory and processor -> 264KB, Cortex-M0+ (correct, 29 s).
  The baseline chunks do flatten tables to one value per line and start mid-word.
- Calls made while probing: 6 LLM calls (3 `/ask`). The API I started for the probes was stopped.
- Seed on the real API (about 14:30): wiped, 7 of 8 files `success` in 67 s, RPi 5 brief `file_too_large`.
- Eval run 14:36:08-14:36:32 (commit `0ec3924` plus the F6 files): routing 8/8, hit@5 6/7, 24,624 tokens, per-question
  13.0, 1.7, 1.7, 1.4, 1.8, 1.9, 2.0, 1.7 s. q04 missed. Raw file: `data/eval/runs/eval_20261022_143634.json` (git-ignored).

Low-priority known issues moved out of PROGRESS.md on 2026-10-22 (still true):

- Starlette warns that `httpx` with TestClient is deprecated (suggests `httpx2`).
- The Linux torch instructions in SPEC §2 are untested.
- `EmbeddingStage`/`IndexingStage` in `ingestion_stage_contracts.py` are unused.
- Loading bge-small online prints an HF Hub warning; `HF_HUB_OFFLINE=1` stops it.

F5 decision lines moved out of PROGRESS.md on 2026-10-22:

- **F5 dependency:** `streamlit==1.65.0`; the UI's HTTP client is the already-pinned `httpx`.
- **F5 layout:** top-level `ui/` with pages in `ui/views/`, its own `ui/tests` check, and an AST test that bans backend imports.
- **F5 polling:** the status table refreshes every 2 s only while a document is queued or processing (an app rerun switches it on or off).
- **F5 settings:** `.streamlit/config.toml` turns usage stats off and sets `maxUploadSize = 25` to match `INGESTION_MAX_FILE_SIZE_MB`.

---
# PROGRESS: running log

Newest first. Old detail gets summarized. Scope and "Done when" live in `docs/SPEC.md`.

## Now

- **Branches:** F0-F4 are merged into `main` (PRs #4, #5 and #6, `eba0e60`). New branches base on
  `main`. `ethan/f5-ui` is local-only (from `eba0e60`).
- **Coach mode is paused** for `route()` and the rest of the MVP (F4-F6) until after Oct 27
  (Ethan, 2026-10-22). It resumes for F7-F9, and Ethan reviews `route()` then
  (`docs/ROUTER_EXPLAINED.md`).
- **Current feature:** F5 (Streamlit UI) is done on `ethan/f5-ui` (2026-10-22), checked with
  screenshots against the real API and real Gemini. Next is F6.
- **Next concrete steps:**
  1. Ethan: push `ethan/f5-ui` and open the F5 PR for Erynn.
  2. F6: seed script, eval set, eval script, demo script, fallbacks. The dev DB already matches
     `data/corpus/`.
- **Ethan by hand (F5):**
  - `pip install -r requirements.txt` (adds Streamlit, about 255 MB), start the API
    (`HF_HUB_OFFLINE=1`), then `.venv\Scripts\python -m streamlit run ui\app.py` in a second
    terminal. The browser opens `http://localhost:8501`.
  - Documents: upload one small TXT into IT policies. Expect a "Last upload" table with "✅ Accepted",
    then the row goes Queued → Processing → Ready by itself, with "Refreshing every 2 s" in the
    caption. Once it's Ready, the caption drops that text, and the KB table counts update. Note
    that the test file stays in the dev DB (and in retrieval) until you rebuild it, so copy
    `backend/instance/` first if you want the seeded state back.
  - Ask: the three questions from the F4 checks. Open a source card. Then stop the API and ask
    again: expect a red error naming the uvicorn start command, not a crash.
  - Fill in the blank URLs in `data/corpus/MANIFEST.md`.
  - Your `.env` comment on line 11 still points at the deleted `docs/decisions.md`.

## Countdown and risk (as of 2026-10-22)

- **5 days to the progress demo (2026-10-27). 47 days to the final demo (2026-12-08).**
- At risk:
  1. F6 remains (F5 done 2026-10-22). If a day is lost, cut F6's eval script down to routing
     accuracy only.
  2. Gemini reliability: on 2026-10-22, `gemini-3.8-flash` failed every call (504s at about 59 s
     and one 503), while `gemini-3.5-flash-lite` answered every call in about 1 s. Flash-Lite
     quality is checked on only 3 questions so far (F6's eval set will tell more). Fallback: set
     `GEMINI_MODEL` in `.env` (with both thinking variables at `low` for `gemini-3.8-flash`), or the
     provider-switch plan (SPEC Oct 27 checklist).
  3. Gemini free-tier quotas during rehearsal and the demo. Every `/ask` makes 2 LLM calls
     (route + answer), so the F6 eval run of 8 questions is about 16 calls. A 429 is retried
     3 times (about 15 s), then `/ask` returns 503.
  4. Gemini latency varies a lot. With Flash-Lite and `minimal` thinking, `/ask` took 1.0-2.1 s
     earlier on 2026-10-22, but 6-29 s in the F5 run later that night with no retries (a direct
     off-topic `/ask`, one LLM call, took 7.2 s). The per-attempt timeout is 20 s, so the worst
     case with 3 retries is about 1.5 min per step. The UI waits up to 180 s. Measure again on
     the demo laptop, and warm up with one question before the demo (the first one also loads
     bge-small, about 10 s).
  5. The F2 install is 1.3 GB and bge-small is a 128 MB download. Install and cache both on the
     demo laptop well before the demo, then use `HF_HUB_OFFLINE=1`.
  6. Baseline retrieval on the datasheet is weak for some questions (fixed 1000-character
     chunks split tables). Expected (Table Challenge motivation), but pick demo questions
     carefully.

## Features

| # | Feature | Status | Branch | Commit |
|---|---|---|---|---|
| F0 | Project setup: AGENTS.md, SPEC.md, PROGRESS.md | Done | `ethan/project-setup` | `f8be5c7` |
| F1 | HTTP API (+ Ruff, slim FastAPI, real KB IDs) | Done | `ethan/f1-api` | `1693e82`, `f077c3c`, `4e7eae5` (chores), `1aeffe8`, `c1df404` |
| F2 | Indexing: bge-small, Chroma and BM25 per KB | Done | `ethan/f2-indexing` | `a922552` |
| F3 | Retrieval plumbing + merge interface (RRF by Ethan, coach) | Done | `ethan/f3-retrieval` | `2b0566e`, this commit (RRF) |
| F4 | `/ask`: routing (Claude to Ethan's design; coach mode paused), grounded Gemini answer, sources | Done (verified with real Gemini) | `ethan/f4-ask` | `1aa5866`, `8f8f8cd`, `4fe7ab2`, `79b878e` (merged, PR #6) |
| F5 | Streamlit UI: Documents and Ask pages | Done (screenshots with the real API) | `ethan/f5-ui` | this commit |
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

- **2026-10-22 (3) · Ethan + Claude · `ethan/f5-ui` · F5 Streamlit UI.**
  - Start: `main` clean and up to date with `origin/main` (`eba0e60`). Backend tests: run 1 had
    354 run, 1 error, 3 skipped (traceback not captured; most likely the Chroma flake), run 2
    354 OK, 3 skipped. Ruff clean.
  - Added `streamlit==1.65.0` (Ethan approved with the plan). It adds 255 MB to `.venv`, and
    `pip check` is clean.
  - New `ui/`: `app.py` (`st.navigation`), `ui_config.py`, `ui_api_client.py` (httpx),
    `ui_messages.py`, `views/documents.py`, `views/ask.py`, and `ui/tests/` (5 files, 40 tests).
    Also `.streamlit/config.toml` (usage stats off, 25 MB upload limit).
  - New checks: `unittest discover -s ui\tests` (it includes the headless smoke test) and
    `ruff check backend ui` (AGENTS.md, SPEC §2).
  - Checks at the end: backend 354 OK, 3 skipped (2 of 2 runs). UI 40 OK. Ruff clean.
  - Real run: API on the dev DB (`HF_HUB_OFFLINE=1`) and Streamlit. Headless Chrome was driven
    over the DevTools protocol by a scratch script (not in the repo) that typed the question and
    clicked Ask. 6 LLM calls in all.
    - Documents: both KBs (3 + 4 documents, all Ready), the picker with descriptions, the
      uploader, and the status table.
    - Ask, Pico dimensions: routed to hardware datasheets, "51 × 21 mm, 1 mm thick PCB [3][8]",
      cited sources [3] and [8] listed first, 3,593 in / 56 out, 2 calls. Latency 29.1 s,
      including the first bge-small load.
    - Ask, password sharing: routed to IT policies, "No ... never disclose their account
      password ... [1]", policy-utdbp3096.pdf p. 8 cited, 17.1 s.
    - Ask, 1998 World Cup: the Off-topic badge, "Routed to no knowledge base", the KB-coverage
      answer, 1 call, 6.2 s. A direct `/ask` for the same question took 7.2 s, so the slowness
      is Gemini, not the UI. No retries showed in the API log.
    - Fixed after the first screenshots: the uploader said "200MB per file" (now 25 MB, matching
      the API default), and two buttons were both labeled "Upload" (the form's is now "Add files
      to <KB>").
    - Not exercised in the real run: an upload, polling, the busy and connection-error states.
      The tests cover them with a fake client.

- **2026-10-22 (2) · Ethan + Claude · `ethan/f4-ask` · 504 retry, model choice, real `/ask` check.**
  - Start: clean tree, up to date with `origin/ethan/f4-ask`. 345 tests OK, 3 skipped; Ruff
    clean.
  - `4fe7ab2`: Gemini 504 `DEADLINE_EXCEEDED` is retried like 503 and ends as 503
    `llm_unavailable`. 3 new tests.
  - Dev DB rebuilt (Ethan's choice): deleted the SQLite DB, Chroma and stored uploads, then
    uploaded `data/corpus/` through `POST /documents`. 7 documents `success` in 62 s (chunks:
    Pico 58, Pico 2 47, Pico W 50, product guide 5, utdbp3096 37, Process_UserData 5,
    policiespyramidnew 2). The RPi 5 brief was rejected (over 25 MB). The RP2040 datasheet is gone.
  - Model comparison: 12 generation calls, scratch script, no retries. Real retrieval
    (`hw_datasheets`, RRF top 10) and the real prompts, on "What are the board dimensions of the Pico?":

    | Model | Thinking | Router (2 calls) | Answer (2 calls) |
    |---|---|---|---|
    | `gemini-3.8-flash` | low | 504, 504 (58.8, 58.9 s) | 503 (0.4 s), 504 (58.7 s) |
    | `gemini-3.5-flash-lite` | minimal | correct, 1.09 / 0.68 s, 363 in / 32 out / 0 thinking | correct "51 × 21 mm, 1 mm thick PCB [3][8]", 0.99 / 0.53 s, 3,230 in / 28 out / 0 thinking |
    | `gemini-2.5-flash` | budget 0 | 404 "no longer available to new users" (×2) | 404 (×2) |

    `models.list()` lists `gemini-2.5-flash`, but the key can't use it. The 3.8 Lite variants on
    the key are TTS only.
  - Applied (Ethan approved): default `gemini-3.5-flash-lite`; `GEMINI_ROUTER_THINKING` and
    `GEMINI_ANSWER_THINKING` (default `minimal`); `GEMINI_TIMEOUT_SECONDS` (default 20, was a
    fixed 60). `route()` and `answer_question()` gained an optional `thinking` argument, which
    `/ask` fills from the config.
  - Real `/ask` (uvicorn, `HF_HUB_OFFLINE=1`, `LLM_MAX_RETRIES=1`, 5 calls, no retries in the log):
    1. Pico dimensions → `["hw_datasheets"]`, "Board dimensions are a physical specification found
       in hardware datasheets.", 2.11 s, 3,593 in / 56 out. Answer "51 × 21 mm, 1 mm thick PCB
       [3][8]" (pico-datasheet.pdf p7, p6-7).
    2. Password sharing → `["it_policies"]`, "A password sharing question is governed by university
       IT security policies.", 1.55 s, 2,731 in / 81 out. Answer: "No ... never disclose their
       account password ... [1]" (policy-utdbp3096.pdf p8).
    3. 1998 World Cup → `[]`, `off_topic: true`, "Sports history is not covered by any knowledge
       base.", 0.97 s, 1 call, 365 in / 21 out.
  - Tests: 354 run, OK, 3 skipped, in all 4 full runs this session (logs saved). No flaky error
    showed up, so there's no traceback to record. Ruff clean.

- **2026-10-22 · Ethan + Claude · `ethan/f4-ask` · F4 `route()`, per-call thinking, corpus.**
  - Start: clean tree, local-only branch (`git fetch` done). 330 tests OK, 3 skipped, 8 expected
    failures; Ruff clean.
  - Ethan paused coach mode for the MVP (decision log). AGENTS.md and SPEC.md updated.
  - `route()` implemented to Ethan's design: a prompt built from `kb_descriptions`, 4 few-shot
    examples, a JSON reply (fences stripped), fallback to every KB on an invalid reply, and
    `LlmUnavailableError` propagating. Ethan approved the prompt with the plan.
  - `generate(..., thinking=None)` on the provider interface, `UsageRecorder`, `GeminiLlm`
    (`ThinkingConfig.thinking_level`) and `FakeLlm`. The router uses `low`; the answer step keeps
    the model default.
  - Corpus: 7 PDFs uploaded through `POST /documents` to the dev server, all `success` in 353 s
    (chunks: Process_UserData 5, policiespyramidnew 2, utdbp3096 37, Pico 2 47, Pico W 50, RP2040
    1,649, product guide 5). The RPi 5 product brief (52.9 MB) was rejected `file_too_large`.
    `pico-datasheet.pdf` was already indexed, so it was skipped. MANIFEST.md has every file.
  - Tests: 345 run, OK, 3 skipped, 0 expected failures (2 of 3 full runs). One full run had 1
    error whose text wasn't captured, most likely the Chroma flake (Known issues). Ruff clean.
  - Real Gemini, 5 of the 8 approved calls:
    1. `/ask` route with `minimal` → 400 "Thinking level MINIMAL is not supported for this model".
    2. Answer step with `minimal` → the same 400.
    3. `/ask` route with `low` → OK, 28.5 s, 363 input and 28 output tokens. The routing result
       wasn't printed (script bug).
    4. The same `/ask`'s answer call (default thinking) → failed. The message was lost: the
       script's `os._exit` didn't flush stdout.
    5. Answer step alone (default thinking, "board dimensions") → 503, 503, 503 (retried), then
       504 `DEADLINE_EXCEEDED` (not retried) → `LlmError`.
    - Stopped there: Gemini was failing on the server side. No thinking comparison and no
      policy or off-topic result were measured.
  - New `docs/ROUTER_EXPLAINED.md`.

- **2026-10-20 · Ethan + Claude · `ethan/f4-ask` · F4 plumbing.**
  - Branched from `main` (`c48a584`, the merged stack). Checks at the start: 265 tests OK,
    3 skipped; Ruff clean.
  - Added `google-genai==2.28.0`. Ethan approved 2.31.0 with a fallback to the newest
    release at least two weeks old; 2.31.0 was 6 days old, so 2.28.0 (2026-10-02).
  - New `backend/app/agent/` package:
    - LLM provider interface, `UsageRecorder` and `build_llm`.
    - `GeminiLlm`: lazy client, temperature 0, AFC off, its own retries on 429/503 and network
      errors, `LlmUnavailableError`, usage including thinking tokens.
    - `AgentConfig` and the KB descriptions file `config/kb_descriptions.json` (name +
      description per KB).
    - The grounded answer step with Ethan's approved prompt (KB display names in the source
      headers).
    - The `route()` interface only (coach mode).
  - `POST /ask`, plus `name` and `description` in `GET /kbs`. New canonical code
    `llm_unavailable` (503 + `Retry-After: 30`), and `not_implemented` maps to 501.
  - Tests: 330 run, OK, 3 skipped (opt-in model tests), 8 expected failures (the router
    tests), in `.venv` and in a scratch venv built only from requirements.txt (`pip check`
    clean). Ruff clean. The Chroma flake (Known issues) hit 2 of 32 looped runs of the API tests. New: `test_agent_llm.py`, `test_agent_gemini.py`,
    `test_agent_config.py`, `test_agent_answer.py`, `test_agent_router.py`, `test_api_ask.py`,
    and one error-model test.
  - Manual runs:
    - `models.list()` (no generation) confirmed the model names; default `gemini-3.8-flash`.
    - Answer step with real dev-DB retrieval (bge-small, `hw_datasheets`, RRF top 10) and real
      Gemini, 2 calls:
      - "What are the board dimensions of the Pico?" → "51 × 21 mm and is 1 mm thick
        [1][3][9]" (pages 7, 6-7, 4), 39.5 s.
      - "What is the warranty period for the Pico?" → exactly the no-answer sentence,
        `no_answer: true`, 8.8 s.
      - Total 6,547 input and 555 output tokens.
    - Real uvicorn: `/kbs` shows names and descriptions; `/ask` → 501 `not_implemented`
      "route() (query routing) is not implemented yet".

- **2026-10-20 · Ethan + Claude · `ethan/f3-retrieval` · merge argument checks (not committed).**
  - Ethan restored the `merge_ranked_lists` docstring and added ValueError checks for `k`
    and `top_n`. He decided to keep review items 3 and 4 as they are (decision log).
  - Claude added `TestMergeArgumentValidation` (3 tests), deleted the 8 commented-out
    decorators and updated the module docstring of `test_retrieval_merge.py`.
  - Tests: 265 run, 3 failures (the subtests of `test_top_n_must_be_an_integer`: `int()`
    truncates 2.5 to 2, converts "3" to 3 and True to 1, instead of raising). Ruff clean.
    Not committed: the commit waits for Ethan's fix.
- **2026-10-20 · Ethan + Claude · `ethan/f3-retrieval` · F3 RRF merge.**
  - Ethan implemented `merge_ranked_lists` (coach mode) and commented out the 8
    `@unittest.expectedFailure` decorators. All 8 merge tests pass.
  - Claude reviewed it (no rewrite) and checked these edge cases with a scratch script:
    - `top_n=-1` silently drops the last hit (`results[:-1]`), and `top_n=None` returns
      everything. The API validates 1-100, but F4 calls the function directly.
    - A chunk repeated within one list is counted twice (the docstring rules this out;
      nothing enforces it).
    - Any extra key on a hit is copied into the fused hit (a deny-list, not an allow-list).
    - `k=0` with rank 0 raises ZeroDivisionError. `k` isn't validated.
    - With three or more terms, float addition order can change a fused score by 1 ulp,
      which can flip a chunk_id tie-break. This can't happen today: a chunk appears in at
      most its own KB's two lists.
    - The input hits aren't mutated.
    - The docstring (the interface contract) was deleted with the old body.
  - `test_api_search.py`: the old not-implemented test failed once the merge existed. It is
    now two tests: the real merge (non-empty `merged` with `fused_score` and `sources`,
    `merge_error` null) and the not-implemented path, with `merge_ranked_lists` patched to
    raise NotImplementedError.
  - Tests: 262 run, OK, 3 skipped (opt-in model tests). Ruff clean.
- **2026-10-20 · Ethan + Claude · `ethan/f3-retrieval` · F3.**
  - New `backend/app/retrieval/` package:
    - `RetrievalConfig` (`RETRIEVAL_TOP_K`, default 20).
    - `Retriever`: two separate ranked lists per KB, with text and source metadata from
      SQLite, `success` documents only, and `embed_query` called once per request.
    - `merge_ranked_lists`: the interface only (docstring + `NotImplementedError`).
  - Vector hits are filtered to `success` documents inside Chroma (`document_id $in`), which
    closes the F2 known issue. `POST /search` returns the raw lists plus the merged list or
    `merge_error: not_implemented`.
  - Tests: 261 run, OK, 3 skipped (opt-in model tests), 8 expected failures (the RRF tests).
    Ruff clean.
  - The merge tests were checked against a throwaway reference RRF in the scratchpad (all 8
    pass with it), and that file was deleted. Nothing of it is in the repo.
  - Manual run (real uvicorn, dev DB, real bge-small, `HF_HUB_OFFLINE=1`) with `/search` on
    `hw_datasheets`, top_k 5:
    - "input voltage range": vector p20-22 + p8-9, keyword p22, p8-9, p21-24 (power
      section, relevant).
    - "board dimensions": "Mechanical specification" p7 is vector #3 and keyword #2.
    - "flash memory": still weak (as in F2).
    - Every call returned `merge_error.code = not_implemented` with 200. Omitting `kb_ids`
      searched both KBs, and an unknown KB returned `unknown_kb` 400.
    - The first query took 9.5 s (model load), later ones 35-39 ms.
- **2026-10-20 · Ethan + Claude · `ethan/f2-indexing` · F2.**
  - Repo moved out of OneDrive (decision logged); no paths needed changing.
  - Dependencies verified in a scratch venv first: install 394 s, venv 1,334 MB (torch
    506 MB). Chroma 1.5.9 checks: `embedding_function=None` really disables the default
    ONNX embedder (no download, `query_texts` raises); None metadata values are rejected;
    every in-memory client in a process shares one store, `reset()` empties it for all,
    and a second in-memory client with different settings raises; a PersistentClient
    holds file locks on Windows (WinError 32 on delete) until `client.close()`;
    `get_or_create_collection` keeps the original metadata (the model guard relies on it);
    telemetry off via `Settings(anonymized_telemetry=False)`.
  - New `backend/app/indexing/` package. The worker now runs extract → chunk → persist →
    embed → index and marks success only after indexing. Startup fails documents left
    `processing` and removes their vectors.
  - Tests: 225 run, OK, 3 skipped (the opt-in model tests), in `.venv` and in the scratch
    venv built only from requirements.txt. Ruff clean. The model test passed once with
    `RUN_MODEL_TESTS=1` (3 tests, 28 s including the first download).
  - Manual run (real uvicorn, dev DB, real model): the Pico datasheet (18 MB PDF) in
    `hw_datasheets` reached `success` 68 s after upload, including the first model load.
    58 chunks in SQLite = 58 Chroma entries. BM25 "gpio" returns 5 chunks (pages 4-20).
    Vector queries: "input voltage range" → pages 20-24 (power section, relevant);
    "board dimensions" → page 7 "51×21 mm" at rank 2; "flash memory" → weak (a page 13
    benchmark table first). Timings: model load + first query 10.1 s; warm embedding
    8.2 chunks/s (58 chunks of 1000 chars in 7.0 s, CPU); BM25 build + query 0.02 s.
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
| 2026-10-22 | F5 dependency | `streamlit==1.65.0` under "# UI (F5)" (2026-10-02; 1.66.0 and 1.66.1 were 8 days and 1 day old). The UI's HTTP client is the already-pinned `httpx`. | `requests` (one more direct dependency for the same job) | Ethan |
| 2026-10-22 | UI layout and tests | Top-level `ui/` with pages in `ui/views/` (`st.navigation`, not the automatic `pages/` folder), its own `ui/tests` run as a separate check, and an AST test that no `ui/` file imports a backend package (Claude, small call) | UI tests under `backend/tests` (would mix the two `sys.path` setups) | Ethan |
| 2026-10-22 | Status polling | The fragment refreshes every 2 s only while a document of the selected KB is queued or processing. Because `run_every` is fixed when the fragment is defined, a change in that state reruns the app once. (Claude, small call) | Always poll every 2 s (constant API traffic and a flickering page during the demo) | Ethan |
| 2026-10-22 | Streamlit settings | `.streamlit/config.toml`: usage statistics off (no telemetry to Streamlit) and `maxUploadSize = 25` to match `INGESTION_MAX_FILE_SIZE_MB` (Claude, small call) | Streamlit's default 200 MB (the uploader would promise a limit the API rejects) | Ethan |
| 2026-10-22 | Ask page details | The latency is measured in the UI (the API doesn't return it). Every source the model saw is shown, cited first. `$` is escaped so answers aren't rendered as LaTeX. The `/ask` timeout is 180 s. (Claude, small call) | Show only cited sources (hides what the model saw; same reasoning as the F4 decision) | Ethan |
| 2026-10-22 | UI owner | Ethan (built by Claude) instead of Erynn, at Ethan's request for the demo | | Ethan |
| 2026-10-22 | Coach mode during the MVP | Paused for `route()` and all remaining MVP work (F4-F6) until after the Oct 27 progress report, because of time. Claude implements `route()` to Ethan's design, and it's listed as AI-written. After Oct 27 coach mode resumes for F7-F9, and Ethan reviews and may rewrite `route()`. | Ethan writes `route()` before Oct 27 (not enough time with F5 and F6 left) | Ethan |
| 2026-10-22 | Router design | LLM classification with a prompt built from `kb_descriptions`; rules: usually one KB, both only if the answer needs both, none if neither can answer; 4 few-shot examples (datasheet, policy, both, off-topic); reply `{"kb_ids": [...], "reason": "..."}`, fences stripped; an invalid reply (unparseable, wrong shape, unknown or duplicate id, more than 2) → every configured KB with `fallback: true`; `LlmUnavailableError` propagates | Embedding similarity to the KB descriptions (thresholds for off-topic and "both" can't be tuned without labeled data; see ROUTER_EXPLAINED.md) | Ethan |
| 2026-10-22 | Router details | Few-shot examples are shown only if every KB they name is configured; returned ids are in config order; no repair of bad replies (an unknown id isn't fuzzy-matched) (Claude, small call) | Always show all 4 examples (would name KBs that aren't configured) | Ethan |
| 2026-10-22 | Thinking control | `generate(..., thinking=None)` takes a level (`minimal`/`low`/`medium`/`high`) sent as Gemini's `thinking_level`; `None` = model default. Router: `low`, because `gemini-3.8-flash` rejects `minimal` (400). Answer step: model default until measured. (Claude, small call) | A token budget (`thinking_budget` is the Gemini 2.5 knob; Gemini 3 models take a level) | Ethan |
| 2026-10-22 | Re-uploading `pico-datasheet.pdf` | Skipped: already `success` in the dev DB, and the duplicate policy is `allow`, so a second copy would put duplicate chunks into retrieval (Claude, small call) | Upload it again as asked (duplicate hits in the top 10) | Ethan |
| 2026-10-20 | Grounding prompt (F4) | Ethan approved the system instruction and user-message layout in `agent_answer.py`, with two changes: the off-topic reply lists only the KB descriptions (no KB IDs), and source headers show a KB display name ("IT policies", "hardware datasheets") instead of the `kb_id`. The API response keeps `kb_id`. | | Ethan |
| 2026-10-20 | KB descriptions location | Committed `config/kb_descriptions.json` with `name` and `description` per KB (`KB_DESCRIPTIONS_PATH` overrides it). A configured KB without an entry stops the app at startup. | `.env` variables (git-ignored, so every machine copies them by hand, and routing quality depends on them) | Ethan |
| 2026-10-20 | Router reply format in tests | The router tests build every scripted LLM reply through one `routing_reply()` helper (JSON to start), which Ethan changes to match his format. The `route()` docstring doesn't fix a format. | A JSON reply format in the contract (takes the choice away from Ethan) | Ethan |
| 2026-10-20 | F4 dependency | `google-genai==2.28.0` under "# LLM (F4)". 2.31.0 was approved with a fallback to the newest release at least two weeks old; 2.31.0 (2026-10-14) was 6 days old. | | Ethan |
| 2026-10-20 | Default Gemini model | `gemini-3.8-flash`, the newest stable Flash in the key's `models.list()` on 2026-10-20, as a code default overridable by `GEMINI_MODEL` | `gemini-flash-latest` (an alias that moves without notice, so runs aren't reproducible) (Claude, small call) | Ethan |
| 2026-10-22 | Default Gemini model and thinking | `gemini-3.5-flash-lite`, `minimal` thinking for the router and answer steps (`GEMINI_ROUTER_THINKING`, `GEMINI_ANSWER_THINKING`), per-attempt timeout 20 s (`GEMINI_TIMEOUT_SECONDS`). Measured: about 1 s per call, correct routing and answer; `/ask` 1.0-2.1 s. Replaces the 2026-10-20 default-model row and the router `low` setting. | `gemini-3.8-flash` (4 of 4 calls failed with 504/503 on 2026-10-22, 28-59 s when it did answer); `gemini-2.5-flash` with thinking off (404 for this key); thinking levels as code constants only (switching models would mean a code change to avoid the `minimal` 400) | Ethan |
| 2026-10-22 | Rebuild the dev DB | Deleted the dev SQLite DB, Chroma and uploads and re-uploaded `data/corpus/`, so the RP2040 datasheet (removed from the corpus by Ethan) is out of retrieval | Measure on the old DB (RP2040 was 1,649 of 1,809 datasheet chunks); filter RP2040 hits in a scratch script (wouldn't cover the real `/ask`) | Ethan |
| 2026-10-22 | Retrying Gemini 504 | 504 `DEADLINE_EXCEEDED` joins 429 and 503: retried, then `LlmUnavailableError` → `/ask` 503 `llm_unavailable` | Leave it a 500 (Gemini's own deadline is a transient server-side failure, and the UI should show "busy, try again") | Ethan |
| 2026-10-20 | What the Gemini provider retries | 429, 503 and network errors (httpx transport errors), up to `LLM_MAX_RETRIES` (3) with 2/4/8 s backoff plus up to 1 s jitter, then `LlmUnavailableError`. Other API errors fail at once as `LlmError` (→ 500). The SDK's own retries stay off (its default). | 429 only (Gemini's "model overloaded" is a 503, and retrying it is just as harmless) (Claude, small call) | Ethan |
| 2026-10-20 | `/ask` error mapping | `route()` NotImplementedError → 501 `not_implemented`; `LlmUnavailableError` at any step → 503 `llm_unavailable` with `Retry-After: 30`; other `LlmError` → 500 without provider details; a `route()` result that breaks its contract (not a dict, unknown or duplicate KB, more than 2, wrong types) → logged 500 | Trust `route()`'s output (a bug in it would surface as a confusing KeyError or a search of an unknown KB) (Claude, small call) | Ethan |
| 2026-10-20 | `/ask` answer details | Merged top 10 into the prompt; no hits → the no-answer sentence without an LLM call; `no_answer` only when the reply is the no-answer sentence alone; every prompted chunk is returned as a numbered source with `cited` (its [n] appears in the answer) and a 300-character snippet; usage counts thinking tokens as output and covers the route and answer calls through a `UsageRecorder` wrapper | Return only cited sources (hides what the model saw) (Claude, small call) | Ethan |
| 2026-10-20 | Merge argument checks | `merge_ranked_lists` raises ValueError for `k <= 0` or a non-numeric `k`, and for a `top_n` that isn't a positive integer (floats, numeric strings and bools included), even on empty input | Trust the callers (`/search` validates `top_n`, but F4's `/ask` calls the function directly) | Ethan |
| 2026-10-20 | Repeated chunk within one ranked list (review item 3) | No check: the Retriever returns each chunk at most once per list, and the docstring states it as a precondition. A repeat would be counted twice. | Count a repeated chunk once (defends against a caller bug that can't happen today) | Ethan |
| 2026-10-20 | Copying hit fields into the fused hit (review item 4) | Keep the deny-list (every field except `rank`, `score`, `source` is copied). The test's exact field set catches a new field leaking through. | Allow-list of the documented fields (immune to new hit fields, but has to be updated when the contract grows) | Ethan |
| 2026-10-20 | Success filter for vector hits | Chroma `where document_id $in <success IDs from SQLite>`, plus a final SQLite lookup that drops any hit whose chunk is gone or whose document isn't `success`; ranks are reassigned 1..n | Fetch top_k and drop non-success hits afterwards (leftover vectors of a failed document would take top_k slots) (Claude, small call) | Ethan |
| 2026-10-20 | Merge contract | `merge_ranked_lists(ranked_lists, k=60, top_n=10)`. Output hits carry `fused_score` and `sources: [{source, kb_id, rank, score}]` in input-list order. Sorted by `fused_score` descending, ties broken by `chunk_id` ascending | Tie-break on best single rank (also valid; Ethan can still change it with the tests) (Claude, small call, approved in the F3 plan) | Ethan |
| 2026-10-20 | `/search` when the merge fails | 200 with the raw lists, `merged: null` and `merge_error` (new canonical code `not_implemented`; any other exception → `internal_failure`, logged) | 501 or 500 for the whole request (would hide the retrieval evidence the endpoint exists to show) (Claude, small call, approved in the F3 plan) | Ethan |
| 2026-10-20 | `/search` defaults | `kb_ids` omitted → every configured KB (an empty list → 400); `top_k` 1-100, default `RETRIEVAL_TOP_K`; `top_n` 1-100, default 10; `chunker` defaults to the baseline; KB IDs normalized and de-duplicated | (Claude, small call) | Ethan |
| 2026-10-20 | Retrieval config location | New `RetrievalConfig` in `retrieval/retrieval_config.py` | A field on Erynn's `IngestionConfig` (retrieval isn't ingestion, and her module stays untouched) (Claude, small call) | Ethan |
| 2026-10-20 | F2 dependencies | `sentence-transformers==6.1.0`, `torch==2.14.1`, `chromadb==1.5.9`, `rank-bm25==0.2.2` under "# Indexing". Accepted side effect: Chroma pulls back `uvicorn[standard]`, opentelemetry, kubernetes and grpcio. Linux needs the CPU torch index (SPEC section 2). | | Ethan |
| 2026-10-20 | F2 index layout | Collection `kb_<kb_id>`, cosine, `embedding_function=None`; IDs are our chunk_id; chunk text only in SQLite; each collection records `embedding_model` and a mismatch is refused; model name and query prefix are code constants; interrupted documents use `internal_failure`; F2 exposes raw `query -> [(chunk_id, score)]`, and F3 owns ranked lists, text, metadata, the merge interface and endpoints | | Ethan |
| 2026-10-20 | BM25 corpus | Chunks of documents in `success` only (`list_kb_chunks` joins the status table). The worker's `on_finished` hook invalidates the KB's BM25, so a finished document is searchable on the next query. | Index chunks as soon as they are persisted (a processing or later-failed document would show up in keyword results) (Claude, small call) | Ethan |
| 2026-10-20 | BM25 hit rule | A chunk is a hit if it shares a query term, ranked by BM25 score | `score > 0` (BM25Okapi's IDF is negative for a term in most chunks of a small KB, so a single-chunk KB never matched) (Claude, small call) | Ethan |
| 2026-10-20 | Indexer in the pipeline | `DocumentProcessor` requires `indexer=` and indexes the chunks read back from SQLite after persisting | Optional indexer (a silent path to success without indexing); indexing the chunk generator (persistence has already consumed it) (Claude, small call) | Ethan |
| 2026-10-20 | Default Chroma path in `create_app` | `chroma/` beside the status repository's DB file, which is `backend/instance/chroma/` for the dev DB | Always `backend/instance/chroma/` (a test with a temp DB that forgot to inject an index would write to the dev Chroma) (Claude, small call) | Ethan |
| 2026-10-20 | Repo location | Moved from OneDrive to `C:\dev\ai-knowledge-hub`, `.venv` rebuilt from requirements.txt (178 tests and Ruff passed after the move). No absolute paths in AGENTS.md, SPEC.md or PROGRESS.md needed changing. | Stay in OneDrive (it locks SQLite and Chroma files while syncing them, and syncs the ~1 GB venv) | Ethan |
| 2026-10-20 | Paths in API responses | `temp_file_path` is stripped from every API response. It stays in the service-layer result for the worker. A test checks that no response contains it or the local upload path. | Return it unchanged (it leaks an absolute local path) | Ethan |
| 2026-10-20 | Re-enqueue on startup | Documents still `queued` in SQLite are re-enqueued when the app starts, oldest first. A queued row with no stored file is skipped with a warning. | No re-enqueue (any restart, including `--reload` during the demo, would leave documents stuck in `queued` forever; re-enqueue is cheap to add and testable) | Ethan |
| 2026-10-20 | `POST /documents` status code | 202 with per-file results whenever the request itself is valid, even if every file was rejected. Request-level errors (unknown KB, batch limit, body over the cap) return the canonical error. | Return the shared code's status (for example 413) when no file is accepted (loses the per-file list). 202 because processing is asynchronous, so 202 Accepted is the correct HTTP semantics, and one response shape (per-file results) keeps the client simple. | Ethan |
| 2026-10-20 | Upload size enforcement | ASGI middleware caps the whole request body while it streams in (413 when over `max_files_per_batch × max_size + 1 MB`), plus a per-file chunked copy that stops at the limit and deletes the partial file | Own streaming multipart parser with python-multipart for a true per-file streaming limit (Starlette buffers multipart bodies before the endpoint runs, so this means hand-parsing multipart: about 100 lines plus a broken `/docs` upload form. The middleware caps the whole request, and the chunked copy keeps oversize files out of `uploads/`.) | Ethan |
| 2026-10-20 | F1 dependencies | `fastapi==0.142.2`, `uvicorn==0.54.0`, `python-multipart==0.0.32`, `httpx==0.28.1` (TestClient), `ruff==0.17.1`. Verified in a scratch venv; `.venv` left alone. | Also uninstall the `[standard]` extras from `.venv` (the clean scratch venv already proves requirements.txt is sufficient; uninstalling from a working venv adds risk and proves nothing more) | Ethan |
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
model (F7, coach), PR review and CI workflow with Erynn, `httpx` vs `httpx2` for TestClient
(see Known issues), retiring the unused `EmbeddingStage`/`IndexingStage` contracts.

Correction to the 2026-10-20 "FastAPI packaging" row: slim `fastapi` 0.142 still depends on
`opentelemetry-api` (the small no-op API package). The `[standard]` extras that are now gone
are sentry-sdk, the opentelemetry SDK and exporters, fastapi-cli and fastapi-cloud-cli.

## Deviations from the spec or the Phase 1 deck

- **UI is Streamlit, not JavaScript** (Phase 1 deck). The sponsor approved flexibility.
  Streamlit is HTTP-only, so it could be swapped out later.
- **The setup commit message** ("Project setup: AGENTS.md, SPEC.md, PROGRESS.md") is not a
  conventional commit. Ethan chose it.

## Known issues

- UI (F5): the KB table at the top of the Documents page refreshes only on a full app rerun
  (when polling starts or stops, or on any click). The status table below it refreshes every
  2 s while needed.
- UI (F5): `ui/ui_messages.py` copies the canonical error codes as strings, because the UI may
  not import the backend. A new code added in the error model needs a line there too.
  Otherwise the UI shows the API's own message, which is still readable.
- UI (F5): `.streamlit/config.toml` is read only when Streamlit starts from the repo root, and
  its `maxUploadSize = 25` must be changed together with `INGESTION_MAX_FILE_SIZE_MB`.
- UI test output prints "missing ScriptRunContext" warnings from Streamlit's AppTest. It's
  expected noise, not a failure.
- The source snippets from `/ask` can start mid-word ("atasheet 2. Mechanical ..."), because the
  snippet is the start of an overlapping 1000-character chunk. This is an API snippet issue,
  not a UI one, and cosmetic.
- *(Fixed 2026-10-22)* A Gemini 504 `DEADLINE_EXCEEDED` wasn't retried and became a 500. It is
  now retried like a 503 and ends as 503 `llm_unavailable`.
- `gemini-3.8-flash` rejects thinking level `minimal` (400). The default model is now
  `gemini-3.5-flash-lite`, which accepts it. Anyone who sets `GEMINI_MODEL=gemini-3.8-flash` must
  also set `GEMINI_ROUTER_THINKING=low` and `GEMINI_ANSWER_THINKING=low`, or every `/ask` returns 500.
- The Gemini SDK appears to send the client timeout to the server as the request deadline: the
  504s on 2026-10-22 came at about 59 s with a 60 s timeout. Not verified in the SDK source. With
  the 20 s timeout, a call slower than 20 s becomes a retried 504.
- `gemini-2.5-flash` appears in `models.list()` but returns 404 "no longer available to new users"
  for this key. Don't pick a model from the list alone.
- `AskApiTestCase` builds its app with the default `AgentConfig()`, which reads `.env`. If someone
  sets `GEMINI_ROUTER_THINKING` or `GEMINI_ANSWER_THINKING` in `.env`, the thinking assertions in
  `test_api_ask.py` would fail. Nobody sets them today.
- With 3 or more configured KBs, the router's fallback ("every configured KB") would exceed the
  2-KB cap, and `/ask`'s `_checked_routing` would return 500. Not reachable with 2 KBs.
- `RP-008348-DS-8-raspberry-pi-5-product-brief.pdf` (52.9 MB) is over the 25 MB upload limit,
  so it isn't indexed.
- *(Resolved 2026-10-22)* The RP2040 datasheet was removed from the corpus, and the dev DB was
  rebuilt without it (`hw_datasheets`: 160 chunks).
- **Rare, unexplained Chroma error in tests:** `chromadb.errors.InternalError: Error
  executing plan: Internal error: Error finding id` from `collection.query`.
  - Seen once in 11 full-suite runs, and about 5 times in ~1,000 looped runs of the
    `/search` API tests (in-memory Chroma shared between tests).
  - It also happens with the F3 `$in` filter patched out, so it's in the F2 query path,
    not caused by F3.
  - Once it happens, an immediate retry fails too.
  - It never reproduced in standalone Chroma scripts (fresh or reset ephemeral client,
    fresh persistent client, 3,800 queries).
  - F4: 2 failures in 32 looped runs of the API test files (7 of `test_api_ask.py` alone, 25 of
    all `test_api_*.py`), both in `/ask` tests. They query more KBs per test, so the flake
    shows up more often.
  - Not seen on the real server. If it does show up there, `/search` returns a canonical
    500 `internal_failure`.
  - If the suite fails with this error, re-run it. If it gets more frequent or shows up on
    the dev DB, consider a chromadb upgrade (a dependency change, so ask first).
- `merge_ranked_lists` accepts a NaN or infinite `k` (NaN makes every score NaN; infinity
  makes every score 0). Not reachable from `/search`, which doesn't expose `k`.
- `/ask` makes 2 LLM calls (route + answer); off-topic makes 1. On `gemini-3.5-flash-lite` with
  `minimal` thinking, it took 1.0-2.1 s with 0 thinking tokens (2026-10-22).
- *(Fixed in F3)* Vector hits could include documents not in `success`. `/search` and the
  Retriever now filter them out.
- The API keeps one Chroma PersistentClient open for its lifetime and never calls
  `close()`. Fine for one process, but on Windows the Chroma directory can't be deleted
  while the server runs.
- Loading bge-small with network access prints "You are sending unauthenticated requests
  to the HF Hub", because it checks the Hub on each load. `HF_HUB_OFFLINE=1` stops it.
- The `EmbeddingStage` and `IndexingStage` contracts in `ingestion_stage_contracts.py`
  are unused: F2's `Embedder` and `DocumentIndexer` have different shapes. Retiring them
  is an open question for Ethan and Erynn.
- The Linux torch instructions in SPEC section 2 are untested (no Linux machine here).
- Starlette (1.9.0 in the rebuilt `.venv`) warns that using `httpx` with its TestClient is
  deprecated and suggests `httpx2`. It's only a warning, and tests pass. Starlette is
  transitive and unpinned. Decide `httpx` vs `httpx2` before Starlette
  removes httpx support.
- `backend/tests/test_task1_ingestion_core.py` contains `# ... existing code ...` markers
  and one test. It has looked like that since Erynn's first commit (`294b052`), so tests may
  have been lost in an AI edit. Ask Erynn.
- The in-memory queue isn't durable. Since F2, a document left `processing` when the
  process dies is marked `failed` on the next startup ("interrupted by server restart").
  It has to be re-uploaded, because the lifecycle has no processing → queued transition.
  Queued documents are re-enqueued on startup.
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
4. *(Resolved 2026-10-22)* Ethan had Claude build F5 for the demo. Please review the F5 PR
   (`ui/`), especially the Documents page, since you know the upload and status services
   best.
5. F4 changed two shared things: `GET /kbs` entries gained `name` and `description`, and the
   error model gained `llm_unavailable` (503). F5's Ask page uses both.

For Ethan:
6. The old CLAUDE.md listed MCP as a consumer of the knowledge layer, but no feature
   schedules it. *Recommendation:* document it as future work for Dec 8, unless the
   sponsor asks for it.
7. Have the PMs confirmed the KB topics? Confirmation changes only config and the
   corpus, not code.
8. Please confirm the AI-written code list below. The pre-2026-10-20 entries are
   inferred from commit messages and the 2026-10-14 decisions.

## Evaluation numbers

| Date | Commit | Eval set size | Routing accuracy | Hit@5 | Faithfulness | Notes |
|---|---|---|---|---|---|---|
| | | | | | | No runs yet. The first run is in F6. |

## AI-written code

Every file or function written or substantially changed by an AI assistant. Ethan's own
coach-mode code is never on this list. Coach-mode pieces Claude wrote while coach mode was
paused (2026-10-22 decision) are.

| Date | Files | Tool | Reviewed by | Notes |
|---|---|---|---|---|
| 2026-10-22 | All of `ui/` (`app.py`, `ui_config.py`, `ui_api_client.py`, `ui_messages.py`, `views/documents.py`, `views/ask.py`, `tests/ui_fakes.py`, `tests/test_ui_api_client.py`, `test_ui_messages.py`, `test_ui_pages.py`, `test_ui_no_backend_imports.py`, `test_ui_smoke.py`); `.streamlit/config.toml`; the UI lines in `requirements.txt`, `.env.example` and `ruff.toml`; SPEC §2/§4 and AGENTS.md check edits | Claude Code | Ethan (to review), Erynn (PR) | F5 |
| 2026-10-22 | 504 in `RETRYABLE_STATUS_CODES` (`agent_gemini.py`); `_resolve_thinking`, `_resolve_timeout`, new defaults and fields in `agent_config.py`; timeout in `build_llm`; `ANSWER_THINKING` and the `thinking` argument of `answer_question`; `ROUTER_THINKING = "minimal"` and the `thinking` argument of **`route()`**; thinking wiring in `/ask` (`api_app.py`); `.env.example`; tests in `test_agent_gemini.py` (2 new), `test_api_ask.py` (2 new, scripted routers take `thinking`), `test_agent_config.py` (3 new, defaults extended), `test_agent_answer.py` (1 new), `test_agent_router.py` (1 new, `minimal` pinned), `test_agent_llm.py`; SPEC and ROUTER_EXPLAINED edits | Claude Code | Ethan (to review) | F4 reliability follow-up |
| 2026-10-22 | **`route()`** and the rest of `backend/app/agent/agent_router.py` (routing prompt, examples, `build_routing_instruction`, `parse_routing_reply`); per-call `thinking` in `agent_llm.py` (`THINKING_LEVELS`, `check_thinking`, `UsageRecorder`) and `agent_gemini.py`; `FakeLlm.thinking_levels`; tests in `test_agent_router.py` (decorators removed, 11 new), `test_agent_gemini.py` (2 new), `test_agent_llm.py` (1 new), `test_api_ask.py` (501 test now patches `route`, 1 new real-router test); `docs/ROUTER_EXPLAINED.md`; MANIFEST rows; AGENTS.md and SPEC.md edits | Claude Code | Ethan (to review after Oct 27; may rewrite `route()`) | F4 routing, a coach-mode piece built while coach mode was paused |
| 2026-10-20 | `backend/app/agent/agent_llm.py`, `agent_gemini.py`, `agent_config.py`, `agent_answer.py`, `agent_router.py` (the interface and docstring only; the body will be Ethan's); `config/kb_descriptions.json`; `POST /ask`, `AskRequest`, `_checked_routing`, the `/kbs` name and description, and the agent wiring in `api_app.py`; `Retry-After` support and the 501/503 mappings in `api_errors.py`; `llm_unavailable` in the error model; tests `agent_fakes.py`, `test_agent_llm.py`, `test_agent_gemini.py`, `test_agent_config.py`, `test_agent_answer.py`, `test_agent_router.py`, `test_api_ask.py`, plus one test in `test_ingestion_error_model.py`; the requirements.txt LLM group; `.env.example` | Claude Code | Ethan (to review) | F4 plumbing |
| 2026-10-20 | `test_retrieval_merge.py`: `TestMergeArgumentValidation`, decorator cleanup, module docstring. Not on this list: the argument checks in `merge_ranked_lists`, which Ethan wrote | Claude Code | Ethan (to review) | F3 RRF follow-up |
| 2026-10-20 | `test_api_search.py`: split the merge test into a real-merge test and a patched not-implemented test, with shared helpers | Claude Code | Ethan (to review) | F3 RRF. Not on this list: the `merge_ranked_lists` body, which Ethan wrote (coach mode) |
| 2026-10-20 | `backend/app/retrieval/retrieval_config.py`, `retrieval_retriever.py`, `retrieval_merge.py` (the interface only: signature, constants and the original docstring; the `merge_ranked_lists` body is Ethan's, not AI-written); `POST /search`, `SearchRequest` and retriever wiring in `api_app.py`; `document_ids` filter in `ChromaVectorIndex.query`; `list_success_document_ids` and `get_chunk_hits` in the artifact repository; `not_implemented` in the error model; tests `test_retrieval_retriever.py`, `test_retrieval_config.py`, `test_retrieval_merge.py`, `test_api_search.py`, plus additions to `test_indexing_vector_index.py` and `test_ingestion_error_model.py` | Claude Code | Ethan (to review) | F3 |
| 2026-10-20 | `backend/app/indexing/` (all four modules); indexing step in `ingestion_pipeline.py`; `list_kb_chunks` in the artifact repository; `on_finished` in `ingestion_worker.py`; `indexing_failure` in the error model; F2 wiring and `_fail_interrupted_documents` in `api_app.py`; tests `indexing_fakes.py` and six `test_indexing_*.py` files, plus F2 additions to `test_api_documents.py`, `test_ingestion_worker.py`, `test_ingestion_pipeline_e2e.py` and `test_ingestion_error_model.py`; the requirements.txt indexing group | Claude Code | Ethan (to review) | F2 |
| 2026-10-20 | `backend/app/api/api_app.py`, `api_errors.py`, `api_uploads.py`; tests `test_api_documents.py`, `test_api_uploads.py`, `test_ingestion_inventory.py`; `list_documents` and `count_documents_by_kb_and_status` in the status repository; `list_documents` and `_status_from_record` in the status service; `document_id`, `new_document_id` and `resolve_kb_id` in the upload service; `not_found` in the error model; `ruff.toml`; Ruff fixes in 4 test files and `ingestion_status_constants.py`; KB defaults; requirements.txt | Claude Code | Ethan (to review) | F1 |
| 2026-10-20 | `AGENTS.md`, `CLAUDE.md`, `docs/SPEC.md`, `docs/PROGRESS.md`, `.claude/skills/decide/SKILL.md`, `.claude/skills/finish-feature/SKILL.md`, `.gitignore` additions, `data/corpus/MANIFEST.md` | Claude Code | Ethan | Docs and config only |
| 2026-10-15 | `ingestion_chunking.py`, `ingestion_artifact_repository.py`, `ingestion_pipeline.py`, worker wiring, related tests (`4feb83c`) | Claude Code (inferred) | Ethan | To confirm |
| 2026-10-15 | `kb_id` changes in metadata contract, status repository, upload service, config, stage contracts, tests (`2e44595`) | Claude Code (inferred) | Ethan | To confirm |
| 2026-10-15 | CLAUDE.md, skills, task list, decision log (`2649814`) | Claude Code (inferred) | Ethan | Replaced by this setup |
| 2026-10-14 | `ingestion_text_extraction.py`, `pdf_fixtures.py`, extraction tests, SQLite test fix (`ee39d42`, `2faa164`) | Claude Code (inferred) | Ethan | To confirm |
| 2026-10-10 to 10-14 | Tasks 1-3 modules and tests (`294b052`, `f10217f`, `07ddd77`) | AI agent, per the commit message of `294b052` | Erynn | Erynn to confirm how much |
