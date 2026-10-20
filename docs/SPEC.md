# SPEC: Centralized GenAI Knowledge Platform and Enterprise Knowledge Agent

Source of truth for scope, architecture and the feature order. The running log is
`docs/PROGRESS.md`. The working rules are `AGENTS.md`.

Sponsor: MSE Technology. Course: BUAN/MIS 6399, Fall 2026.
Milestones: progress-report demo **2026-10-27** (solid MVP). Final demo and sponsor
walkthrough **2026-12-08**.

## 1. Goal, users and value

**Goal.** Build a shared, governed knowledge layer that several consumers use the
same way: a Streamlit UI, a REST API and a routing Knowledge Agent. Documents go into
separate knowledge bases (KBs). A question is routed to the right KB or KBs without
the user choosing, answered from retrieved passages only, and returned with visible
sources.

**Users.**
- Knowledge admins upload documents into a KB and watch them get processed.
- Employees ask questions and get grounded answers with sources.
- Developers and other agents call the same layer through the REST API (and, in
  future, MCP).

**Value for MSE Technology.**
- One ingestion and retrieval layer instead of a separate chatbot per team.
- Answers are traceable to a document and page, so they can be checked.
- KBs stay separate but are searchable together, so it scales to more domains.
- The evaluation numbers (routing accuracy, hit@5 and later faithfulness) show
  whether answers can be trusted.
- The Table Challenge result shows how to handle table-heavy technical documents.

### Sponsor minimum (what the final demo must show)
1. Two separate, independently searchable KBs built from public PDF, TXT and MD files.
2. A displayed chunking and indexing strategy recommendation per document.
3. One working Table Challenge approach, measured against the naive baseline.
4. Hybrid retrieval: BM25 plus vector search, merged with RRF, then re-ranked.
5. A routing Knowledge Agent that picks the right KB or KBs.
6. Grounded answers with visible sources.
7. Later: certified questions, a Judge Agent, provenance, a freshness indicator, and
   token and cost visibility.

## 2. Stack and how to run

| Layer | Choice |
|---|---|
| Language | Python 3.11, project `.venv` |
| API | FastAPI (slim: `fastapi` + `uvicorn` + `python-multipart`, from F1) |
| Database | SQLite, single writer, local. Dev DB at `backend/instance/ingestion.sqlite3` (git-ignored). No migrations: a schema change means deleting the dev DB. |
| Text extraction | pypdf (baseline), plain TXT and MD |
| Embeddings | `BAAI/bge-small-en-v1.5`, local on CPU, via sentence-transformers (from F2). 384 dimensions, normalized; the bge query instruction goes on queries only. The model name is a code constant, not `.env`. |
| Vector store | Chroma, persistent on disk at `backend/instance/chroma/` (git-ignored), one collection `kb_<kb_id>` per KB, cosine distance, vectors from our embedder (Chroma's own embedder is off). Chunk text stays in SQLite. |
| Keyword search | BM25 (`rank-bm25`), one in-memory index per KB and chunker, built lazily from SQLite chunks of `success` documents |
| LLM | Gemini Flash (the current model from AI Studio's model list) through the Gemini API free tier, behind a provider interface. Claude Haiku or Ollama can be swapped in through `.env`. |
| UI | Streamlit, HTTP-only client of the API |
| Tests | `unittest`. The LLM is mocked in every test. |
| Lint | Ruff, rules E and F (added at the start of F1) |

**KBs** are config-driven through `INGESTION_ALLOWED_KB_IDS`:
- `it_policies`: public university IT policies and procedures.
- `hw_datasheets`: public hardware datasheets.

Both topics are pending PM confirmation.

**Planned dependencies.** Each is added in its feature, and Ethan confirms it when it
is added.

| Feature | Dependency |
|---|---|
| F1 | `fastapi`, `uvicorn`, `python-multipart` (replace `fastapi[standard]`), `httpx` (TestClient), `ruff` |
| F2 | `sentence-transformers==6.1.0`, `torch==2.14.1`, `chromadb==1.5.9`, `rank-bm25==0.2.2` (Chroma also pulls in `uvicorn[standard]`, opentelemetry, kubernetes and grpcio) |
| F4 | `google-genai` |
| F5 | `streamlit` (needs 1.37 or later for `st.fragment(run_every=...)`) |

**How to run** (Windows PowerShell, repo root):

```powershell
.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env    # then set GEMINI_API_KEY and check the KB IDs
.venv\Scripts\python -m unittest discover -s backend\tests
.venv\Scripts\python -m ruff check backend
.venv\Scripts\python -m uvicorn api.api_app:create_app --factory --app-dir backend\app --port 8000
```

**Indexing notes (F2).**
- The install is large: a fresh venv from requirements.txt measured 1,334 MB (torch is
  506 MB of that) and took about 6.5 minutes on the dev laptop.
- PyPI's Windows torch wheels are CPU-only. **On Linux**, install the CPU wheel first, or
  pip pulls the multi-GB CUDA build:
  `pip install torch==2.14.1 --index-url https://download.pytorch.org/whl/cpu`, then
  `pip install -r requirements.txt`.
- The first processed document downloads bge-small (about 128 MB) into the Hugging Face
  cache, `%USERPROFILE%\.cache\huggingface`. Once it is cached, set `HF_HUB_OFFLINE=1`
  for the demo so a network hiccup can't stop model loading.
- The model loads on the first document, not at startup (about 10 s on the dev laptop).
- Changing the embedding model means deleting `backend/instance/chroma/` and
  re-processing: the vector index refuses a collection built with another model.
- The opt-in real-model test: `$env:RUN_MODEL_TESTS='1'` then
  `.venv\Scripts\python -m unittest discover -s backend	ests -p test_indexing_model_integration.py`.

The last command starts the API at `http://127.0.0.1:8000`, with interactive docs at
`/docs`. The background worker starts and stops with it. Run **one process only**: no
`--workers`. Each process would get its own in-memory queue and worker thread.
Uploaded files go to `backend/instance/uploads/<document_id>/` (git-ignored). On startup,
documents still `processing` from a crashed or killed run are marked `failed`
(`internal_failure`, "interrupted by server restart") and their vectors removed;
re-upload them to process again. An embedding or indexing error fails the document with
`indexing_failure`. F5 adds the UI start command here.

**API (F1).** Every error uses the canonical body `{code, message, details}` (plus
`field` or `file_name` when relevant). Status codes: `unknown_kb`, `validation_failed`
and `batch_limit_exceeded` → 400; `not_found` → 404; `file_too_large` → 413;
`internal_failure` → 500.

| Endpoint | Returns |
|---|---|
| `POST /documents` (multipart: `kb_id`, one or more `files`) | 202 with per-file accepted or rejected results, even if every file was rejected. Every accepted file is enqueued. A request-level problem (unknown KB, too many files, body over the size cap) returns the canonical error instead. |
| `GET /documents?kb_id=` | `{documents: [...]}`, newest first, without history |
| `GET /documents/status?document_id=a&document_id=b` | Batch status: counts, progress, `missing_document_ids` |
| `GET /documents/{id}` | Status, timestamps, `failure_code`, `failure_reason` and history |
| `GET /kbs` | `{kbs: [{kb_id, counts: {queued, processing, success, failed}, total}]}` in config order |

**Data layout.**
- `data/corpus/<kb_id>/`: public documents, downloaded by hand. Git-ignored.
- `data/corpus/MANIFEST.md`: committed. Lists title, file, URL and KB for each file.
- `data/eval/eval_set.jsonl`: committed evaluation set (section 5).

## 3. Constraints

- **Public data only.** No sponsor documents. Every corpus file is listed in
  MANIFEST.md with its public URL.
- **Laptop-local.** Everything runs on one Windows laptop: local embeddings, local
  Chroma, SQLite. The only network call is the hosted LLM.
- **Cost.** The target is $0 (free tier), with a hard cap of about $10 for the
  semester. Any run over 20 LLM calls needs Ethan's approval and an estimate first.
- **Gemini free-tier data use.** Google may use prompts sent on the free tier to
  improve its products. That is acceptable because every document and question is
  public. Never send personal information.
- **Rate limits.** On HTTP 429 the provider retries with exponential backoff. If the
  retries run out, the API returns a clear rate-limit error and the UI shows it as
  such, not as a generic failure.
- **Streamlit deviation.** The Phase 1 deck committed to a JavaScript UI. The sponsor
  approved flexibility, so the UI is Streamlit. This is recorded as a deviation in
  PROGRESS.md. Because Streamlit only talks HTTP to the API, a JavaScript UI could
  replace it later without backend changes.
- **Out of scope** (documented as future work, not built): graph retrieval, SQL or
  spreadsheet querying, RBAC, Azure deployment, production security.

## 4. Architecture

```
upload (UI/API) → intake + validation → SQLite status (queued)
      → queue → worker: extract → chunk → persist → embed + index (Chroma, BM25)
question (UI/API) → router (which KB?) → per-KB vector + BM25 search
      → merge (RRF) → [re-rank, after Oct 27] → LLM answer from chunks only
      → answer + sources (document, page, KB) + routed KB
```

| Part | What it does | Coach mode | Owner | Status |
|---|---|---|---|---|
| Ingestion core | config, errors, metadata contract, upload intake, queue, worker, status lifecycle | No | Erynn (tasks 1-3), Ethan (kb_id) | Done |
| Extraction | TXT, MD, pypdf PDF baseline | No | Ethan | Done |
| Table Challenge | table-aware extractor and table-safe chunker beside the baseline, measured against it | **Yes** | Ethan | F8 |
| Chunking baseline | fixed-size character chunker, persisted per chunker name | No | Ethan | Done |
| Strategy recommendation | analyze each document's structure and recommend a chunking and indexing strategy, shown in the UI | **Yes** | Ethan | F9 |
| Embeddings and indexing | bge-small embeddings, per-KB Chroma collection, per-KB BM25 index | No | Ethan | F2 |
| Retrieval plumbing | per-KB vector and keyword search returning separate ranked lists | No | Ethan | F3 |
| Hybrid merge (RRF) | merge the two ranked lists | **Yes** | Ethan | F3 |
| Re-ranking | re-rank the merged list | **Yes** | Ethan | F7 |
| Query routing | pick the KB or KBs for a question | **Yes** | Ethan | F4 |
| Agent and LLM | provider interface (Gemini by default), grounded prompt, no-answer path | No | Ethan | F4 |
| API | FastAPI endpoints for upload, status, inventory and ask | No | Ethan | F1, F4 |
| UI | Streamlit Documents and Ask pages | No | Erynn (likely) | F5 |
| Evaluation | eval set, routing accuracy, hit@5, later Judge Agent | No (Judge: no) | Ethan | F6, F11 |

## 5. Quality and evaluation

**Evaluation set.** The file is `data/eval/eval_set.jsonl` (committed), one JSON
object per line:

```json
{"id": "q01", "question": "...", "expected_kb": "it_policies", "expected_source": "<file name from MANIFEST.md>", "expected_answer": "..."}
```

`expected_kb` is a KB ID, a list of KB IDs for questions that span KBs, or `"none"`
for off-topic questions. For off-topic questions `expected_source` is `null` and
`expected_answer` describes the "not in the knowledge base" reply.

**Reported numbers.** Each run's numbers are logged in PROGRESS.md with the date and
commit.
- **Routing accuracy:** the share of questions whose routed KB set equals
  `expected_kb`.
- **Retrieval hit@5:** the share of on-topic questions where `expected_source` appears
  among the top 5 retrieved chunks' documents.
- **Answer faithfulness** (later, F11): the Judge Agent scores whether each answer is
  supported by its cited chunks.
- **Table Challenge** (F8): retrieval precision on table questions and index size,
  baseline against the table-aware method.

## 6. Features in order

Each feature is sized for one session and ends with every check passing and a commit.

### MVP for 2026-10-27

**F1: HTTP API.**
- *First, as a separate chore commit:*
  - Add Ruff (rules E and F) and `ruff check backend` to the checks.
  - Replace `fastapi[standard]` with slim `fastapi` + `uvicorn` + `python-multipart`.
- *Done when:*
  - A FastAPI app starts with one command.
  - `POST /documents` takes one or more files plus `kb_id`. It stores the files,
    calls the existing upload service, and returns per-file accepted or rejected
    results.
  - Every accepted file is enqueued automatically.
  - The worker thread starts with the app and stops cleanly on shutdown.
  - `GET /documents/{id}` and a batch status endpoint return the status service's
    output.
  - `GET /kbs` lists the configured KBs with document counts by status.
  - `GET /documents?kb_id=` lists the inventory.
  - Every error response uses the canonical error payload.
  - The `kb_placeholder_a/b` defaults are replaced by `it_policies,hw_datasheets` in
    the config, `.env.example` and the tests.
  - API tests run through FastAPI's TestClient.

**F2: Indexing.**
- *Done when:*
  - After chunking, the worker embeds the persisted chunks with bge-small and writes
    them to the KB's Chroma collection and BM25 index.
  - Re-processing a document replaces its entries, with no duplicates.
  - An indexing failure marks the document `failed` with a canonical code.
  - Tests use a small fake embedder; there is no model download in the test suite.
  - One manual run on a real file is recorded in PROGRESS.md.

**F3: Retrieval plumbing.**
- *Done when:*
  - For a given KB, vector search and keyword search each return a separate ranked
    list of `(chunk_id, score, rank)` with chunk text and source metadata.
  - A merge-function interface (signature, docstring, `NotImplementedError`) and its
    tests exist. Claude writes the interface and tests because this spec asks for
    them. **Ethan implements RRF (coach mode).**

**F4: Answer endpoint.**
- *Done when:*
  - `POST /ask {question}` runs routing (a router interface plus tests written by
    Claude; **routing logic by Ethan, coach mode**), then retrieval and merge for the
    routed KBs, then the LLM provider.
  - The answer is grounded only in the retrieved chunks.
  - The response contains the answer, sources (document, page, KB, chunk), the routed
    KB or KBs, and a `no_answer` flag.
  - Off-topic questions return a "not in the knowledge base" answer.
  - A 429 is retried with backoff and then reported as a rate-limit error.
  - The provider is chosen through `.env`. Gemini is the default.
  - Every test mocks the provider.

**F5: Streamlit UI.**
- *Done when:*
  - The Documents page has a KB picker, multi-file upload, per-file
    accepted/rejected results, a status table that refreshes itself through
    `st.fragment(run_every=...)` while anything is queued or processing, and failure
    reasons.
  - The Ask page shows the question, answer, sources and routed KB, plus loading,
    empty, no-answer, rate-limit and error states.
  - The UI talks to the API over HTTP only and imports no backend modules.
  - A Streamlit smoke test (the app imports and starts headless) is added to the
    checks.

**F6: Demo readiness.**
- *Done when:*
  - A seed script ingests everything in `data/corpus/` through the API.
  - `data/eval/eval_set.jsonl` has 5-8 questions covering both KBs and one off-topic
    question.
  - An evaluation script prints routing accuracy and hit@5. It asks before making
    more than 20 LLM calls.
  - The demo script (section 7) is written.
  - A fallback plan exists: a recorded backup video, a pre-seeded DB, and the
    rate-limit plan.
  - Numbers are logged in PROGRESS.md.

### After 2026-10-27

- **F7: Re-ranking (coach).** Re-rank the merged list, for example with a small local
  cross-encoder. Report hit@5 with and without re-ranking.
- **F8: Table Challenge (coach).**
  - Add a table-aware extractor and a table-safe chunker beside the baselines.
  - Pick 2-3 public table-heavy documents and write 5-10 table questions.
  - Compare retrieval precision and index size against the baseline, and save the
    results table.
- **F9: Strategy recommendation (coach).** Analyze each document's structure
  (headings, tables, length), recommend a chunking and indexing strategy, and show
  it in the UI.
- **F10: Duplicate handling.** Compute a checksum at intake and apply the configured
  policy. Exact duplicates are blocked with clear feedback.
- **F11: Certified questions and Judge Agent.** Certified Q&A pairs, plus a Judge
  Agent that scores faithfulness. Report faithfulness alongside the other numbers.
- **F12: Token and cost tracking.** Tokens and estimated cost per query and per KB,
  shown in the UI.
- **F13: Provenance and freshness.** Provenance per answer and a freshness indicator
  per document and KB (sponsor minimum, item 7).

## 7. Milestone checkpoints

### Demo script (both milestones)

1. Show both KBs and their documents.
2. Upload a new file and watch its status go from queued to processing to success.
3. Ask one question per KB and show the routing and the sources.
4. Ask an off-topic question and show the "not in the knowledge base" answer.
5. Show the table baseline failure as the motivation for the next milestone. On
   Dec 8, show the Table Challenge result instead.

### Oct 27 readiness checklist

- [ ] F1-F6 done, all checks green on the demo branch.
- [ ] `data/corpus/` has documents for both KBs, all listed in MANIFEST.md.
- [ ] The seed script has run on a clean DB, and every document is `success`.
- [ ] The evaluation script has run, and routing accuracy and hit@5 are logged.
- [ ] Demo script rehearsed end to end at least twice.
- [ ] One table question prepared that the baseline answers badly.
- [ ] Fallbacks: a recorded backup video of the full demo, a copy of the seeded DB and
      Chroma directory, a plan for a Gemini rate limit (wait or switch provider via
      `.env`), and offline screenshots.
- [ ] GEMINI_API_KEY works on the demo laptop, and the free-tier quota hasn't been
      used up that day.

### Dec 8 readiness checklist

- [ ] F7-F13 done, or the cut ones documented as future work.
- [ ] Table Challenge results table (baseline against the table-aware method) in the
      slides.
- [ ] Evaluation numbers with re-ranking and Judge faithfulness logged.
- [ ] Demo script updated, rehearsed, and recorded as a backup video.
- [ ] Seed data and fallback DB and Chroma snapshot refreshed.
- [ ] Sponsor walkthrough notes: architecture, decisions, deviations, future work
      (graph retrieval, SQL, RBAC, Azure, production security, MCP).
- [ ] Ethan has rehearsed the oral Q&A on the four coach-mode pieces.
