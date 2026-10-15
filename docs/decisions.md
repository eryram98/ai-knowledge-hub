# Decision log

| Decision | Choice | Alternatives ruled out (why) | Owner | Decided on |
|---|---|---|---|---|
| Build approach for the progress demo | AI-assisted ("vibe coded") MVP, then the team rebuilds and extends it | Hand-build everything (not feasible by the Oct 27 deadline) | Team | 2026-10-14 |
| AI split | AI builds the plumbing. Ethan writes the core pieces (Table Challenge, strategy recommendation, hybrid merge and re-rank, routing) with coaching | Full AI build (team couldn't defend the core pieces in the oral Q&A) | Ethan | 2026-10-14 |
| PDF baseline extractor | pypdf text layer, no OCR | (baseline only; the table-aware method is decided separately) | Ethan | 2026-10-14 |
| KB topics | TODO (placeholder IDs `kb_placeholder_a`, `kb_placeholder_b` via `INGESTION_ALLOWED_KB_IDS` until decided) | | | |
| Embedding model | TODO | | | |
| Vector store | TODO | | | |
| Local or hosted LLM | TODO | | | |
| Front-end framework | TODO (the Phase 1 deck says a JavaScript UI) | | | |
| Table Challenge approach | TODO | | | |
| Workflow (feature branches, PR reviews, CI) | TODO | | | |
