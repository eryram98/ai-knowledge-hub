# Tasks: knowledge pipeline and retrieval MVP

Legend: `[x]` done, `[ ]` to do, `(added)` was not in the original list, `(core)` coach mode (Ethan writes the logic), `(deferred)` not needed for the MVP.

Target: progress presentation around Oct 27. Milestones: M4 knowledge pipeline (through Oct 18), M5 retrieval and routing (Oct 19 to Oct 31).

## Tasks
- [x] **1.0 Define ingestion architecture, configuration, and shared contracts**
  - [x] 1.1 Define lifecycle states and transition rules (`queued` → `processing` → `success`/`failed`).
  - [x] 1.2 Configure allowed extensions, file size, batch size, and duplicate policy.
  - [x] 1.3 Define standardized errors and messages.
  - [x] 1.4 Define metadata and persistence contracts.
  - [x] 1.5 Define extraction, chunking, embedding, and indexing interfaces.
  - [x] 1.6 (added) Add `kb_id` to the metadata contract and persistence.
  - [x] 1.7 (added) Fix `__metaclass__ = ABCMeta` in the stage contracts (Python 2 syntax that Python 3 ignores) by switching to `class X(metaclass=ABCMeta)`.
- [x] **2.0 Implement upload intake and validation**
  - [x] 2.1 Implement the upload intake service.
  - [x] 2.2 Validate PDF, TXT, and MD extensions.
  - [x] 2.3 Enforce per-file and per-batch limits.
  - [x] 2.4 Add readability pre-checks where feasible.
  - [x] 2.5 Return per-file acceptance/rejection results.
  - [x] 2.6 (added) Accept `kb_id` at upload and reject unknown KBs.
- [x] **3.0 Implement ingestion queue, worker, and status lifecycle components**
  - [x] 3.1 Add queue abstraction and background worker entrypoint.
  - [x] 3.2 Persist and expose initial `queued` status.
  - [x] 3.3 Persist `processing` when the worker starts a file.
  - [x] 3.4 Isolate failures so one file does not block others.
  - [x] 3.5 Persist final `success` or `failed` status with failure reason.
  - [x] 3.6 Add status query service for UI polling and batch progress.
- [ ] **4.0 Implement format-specific text extraction**
  - [x] 4.1 Implement the extractor interface and extension-based dispatcher.
  - [x] 4.2 Implement encoding-safe TXT extraction.
  - [x] 4.3 Implement MD extraction, preserving raw Markdown.
  - [x] 4.4 Implement text-based PDF extraction; exclude OCR. This is the Table Challenge baseline.
  - [x] 4.5 Normalize extracted-text payloads.
  - [x] 4.6 Map extraction exceptions to standardized failure reasons.
  - [ ] **4.7 (added, core) Implement a table-aware PDF extractor and register it on the dispatcher. Keep the baseline — next.**
  - [ ] 4.8 (added, core) Analyze document structure (headings, tables, length) and display a chunking and indexing strategy recommendation.
- [ ] **5.0 Implement chunking, embeddings, and keyword indexing**
  - [ ] 5.1 Configure chunk size and overlap. This fixed-size chunker is the baseline.
  - [ ] 5.2 Handle empty, short, and very long text safely.
  - [ ] 5.3 Generate embeddings with retry-safe failure propagation. Blocked until the embedding model is decided.
  - [ ] 5.4 Implement keyword (BM25) indexing, one index per KB.
  - [ ] 5.5 Persist links between documents, chunks, embeddings, and indexes.
  - [ ] 5.6 (added, core) Implement table-safe and structure-aware chunking alongside the baseline.
  - [ ] 5.7 (added) Build a vector index per KB. Blocked until the vector store is decided.
- [ ] **6.0 Implement artifact and metadata persistence**
  - [x] 6.1 Add repository methods for file metadata and status history.
  - [ ] 6.2 Persist full extracted text.
  - [ ] 6.3 Persist chunks and embedding/index references.
  - [x] 6.4 Persist source metadata with v1 source value `UI`.
  - [ ] 6.5 Make persistence idempotent where practical for safe reprocessing.
- [ ] **7.0 Implement configurable duplicate handling**
  - [ ] 7.1 Calculate file checksums during intake.
  - [ ] 7.2 Resolve duplicate policy from configuration.
  - [ ] 7.3 (deferred) Support allowing duplicates.
  - [ ] 7.4 Block exact duplicates with clear feedback.
  - [ ] 7.5 (deferred) Support linked versions, if selected.
  - [ ] 7.6 (deferred) Allow policy changes without rewriting the workflow.
- [ ] **8.0 Expose backend capabilities required by the UI**
  - [ ] 8.1 Define upload, inventory, status, question, answer, and source API contracts.
  - [ ] 8.2 Add an HTTP upload handler using the existing intake service (FastAPI, as on the old `feature/ingestion` branch).
  - [ ] 8.3 Connect accepted uploads to the queue, worker, and actual processing stages.
  - [ ] 8.4 Expose document inventory and status through HTTP endpoints.
  - [x] 8.5 Keep lifecycle labels consistent across services.
  - [ ] 8.6 Retrieve relevant chunks using embeddings and keyword search.
  - [ ] 8.6a (added, core) Merge the keyword and vector result lists (for example Reciprocal Rank Fusion).
  - [ ] 8.6b (added, core) Re-rank the merged list (for example with a cross-encoder).
  - [ ] 8.7 Generate answers grounded in retrieved content. Blocked until local vs hosted LLM is decided.
  - [ ] 8.8 Expose a question endpoint with supporting source references.
  - [ ] 8.9 Handle questions with no relevant content.
  - [ ] 8.10 Return consistent, human-readable API errors.
  - [ ] 8.11 (deferred) Preserve hooks for future manual retry support.
  - [ ] 8.12 (added, core) Route each question to the relevant KB or KBs automatically.
  - [ ] 8.13 (added) Add a KB inventory endpoint with enable and disable.
- [ ] **9.0 Build a basic, functional UI**
  - [ ] 9.1 Select a simple UI approach and document startup. Blocked until the front-end framework is decided.
  - [ ] 9.2 Define Documents and Ask a question views and API interactions.
  - [ ] 9.3 Add simple navigation between views.
  - [ ] 9.4 Add multiple-file selection and upload controls, including KB selection.
  - [ ] 9.5 Display per-file acceptance/rejection results.
  - [ ] 9.6 Display document status, timestamps, and failure reasons.
  - [ ] 9.7 Poll while documents are queued or processing.
  - [ ] 9.8 Add question input and submission.
  - [ ] 9.9 Display questions, answers, and supporting sources together, including which KB was routed to.
  - [ ] 9.10 Handle loading, empty, no-results, and error states.
  - [ ] 9.11 Render filenames and generated answers safely.
  - [ ] 9.12 (added) Display each document's strategy recommendation.
- [ ] **10.0 (added) Run the Table Challenge test**
  - [ ] 10.1 Pick 2–3 public documents that contain tables and write 5–10 questions whose answers live in table cells.
  - [ ] 10.2 Compare the baseline (4.4 + 5.1) with the table-aware method (4.7 + 5.6): retrieval precision and index size.
  - [ ] 10.3 Save the results table for the slides and the decision log.

## Later milestones (not in this sprint)
- M6: certified questions, Judge Agent, provenance, freshness indicator.
- M7: token usage and estimated cost per query and per KB.

## Progress log
- By 2026-10-14 · Erynn · `main` · Tasks 1.0–3.0, 6.1, 6.4, 8.5. 66 tests.
- 2026-10-14 · Ethan · `feat/text-extraction` · Tasks 4.1–4.6, plus a fix so SQLite tests pass on Windows. 92 tests.
- 2026-10-15 · Ethan · `chore/claude-code-setup` · Added CLAUDE.md, the `/finish-feature` and `/decide` skills, this task list, and the decision log.
- 2026-10-15 · Ethan · `feat/kb-id` · Tasks 1.6, 1.7, 2.6: `kb_id` in metadata, SQLite (indexed column) and upload intake; canonical `unknown_kb` error; allowed KBs from `INGESTION_ALLOWED_KB_IDS` (`.env`, two placeholders); stage contracts now enforce `@abstractmethod`; SQLite WAL mode; upload tests use temp DBs and the shadowed test class runs. Requirements moved to root `requirements.txt`. 112 tests.
