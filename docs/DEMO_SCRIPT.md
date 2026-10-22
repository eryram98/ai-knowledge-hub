# Demo script (progress report 2026-10-27)

Follows SPEC §7 ("Demo script"). About 8 minutes. Questions come from `data/eval/eval_set.jsonl`, so
`scripts\run_eval.py` shows how each one scores before you present it.

## Before you present (the night before and 30 minutes ahead)

1. Seeded state: `.venv\Scripts\python scripts\seed_corpus.py` (asks before wiping). Every file should end
   `success`; the RPi 5 brief is listed as `rejected: file_too_large`, which is expected.
2. Copy `backend\instance\` to `backend\instance_backup\` (the fallback, and the way to undo the step 2 upload).
3. `GEMINI_API_KEY` works and the free-tier quota isn't used up that day (see "Gemini slow or busy").
4. Cache the models and go offline for the embedder: run one question first, then `$env:HF_HUB_OFFLINE='1'`.
5. Rehearse the five steps twice, with a stopwatch on step 3.

## Startup (two terminals, repo root, PowerShell)

```powershell
# Terminal 1: API (one process only, no --workers)
$env:HF_HUB_OFFLINE = '1'
.venv\Scripts\python -m uvicorn api.api_app:create_app --factory --app-dir backend\app --port 8000

# Terminal 2: UI, opens http://localhost:8501
.venv\Scripts\python -m streamlit run ui\app.py
```

Check: `http://127.0.0.1:8000/kbs` lists `it_policies` (3 documents) and `hw_datasheets` (4 documents).

## Warm-up (before the audience is watching)

On the Ask page: **How much on-board QSPI flash does the Raspberry Pi Pico 2 have?** (expected: 4 MB).
It loads bge-small (about 10 s) and opens the Gemini connection, so the first demo question isn't the slow one.
Don't present this answer; it is the same question as the eval set's q02.

## The five steps

**1. Both KBs and their documents** (Documents page)
- Pick `hw_datasheets`, then `it_policies`. Point at the document names and the Ready status.
- Say: two separate KBs, built only from public PDFs; the user never picks one when asking.

**2. Upload a new file and watch it process** (Documents page)
- Create the file: `Set-Content $env:TEMP\pico2-notes.txt "The Raspberry Pi Pico 2 uses the RP2350 microcontroller with dual Arm Cortex-M33 cores at 150 MHz and 520 kB of SRAM."`
- Pick `hw_datasheets`, upload `pico2-notes.txt`. Point at the status going Queued, Processing, Ready on its own
  (2 s refresh that stops when done).
- Duplicates are allowed, so don't upload it twice. Restore `backend\instance_backup\` afterwards if you rehearse.

**3. One question per KB** (Ask page). After each answer point at the routed KB, the route reason, the
numbered citations, and a source card (document, page).
- Hardware: **What wireless chip does the Raspberry Pi Pico W use, and which Bluetooth version does it support?**
  Routed to `hw_datasheets`; Infineon CYW43439, Bluetooth 5.2; source `RP-008312-DS-2-pico-w-datasheet.pdf`.
- Policy: **Do I have to encrypt confidential university data that I store on my laptop?**
  Routed to `it_policies`; yes; source `policy-utdbp3096.pdf`.
- Optional, if time: the question spanning both KBs (q07 in the eval set) shows two routed KBs.

**4. Off-topic question** (Ask page): **What is a good recipe for banana bread?**
- Point at: no KB routed, no sources, a reply listing what the KBs cover. Nothing was retrieved and no answer was
  generated, so the system doesn't make something up.

**5. Why tables are the next milestone** (Ask page)
- Ask: **Who has to approve a request for a user's data in a criminal investigation at UT Dallas?**
  The answer is in the approvers table of `Process_UserData.pdf` (requestor UTD Police, approver UTD Attorney).
  In the 2026-10-22 eval run the baseline returned the no-answer reply: the top 5 chunks were all from the long
  policy, so the table never reached the model. Rehearse it: it was one run, so confirm it still fails.
- Open a source card from any datasheet answer to show the cause: the snippet can start mid-word, and tables are
  flattened to one value per line with the header separated from the values.
- Say: this is the fixed-size character baseline, kept as the Table Challenge baseline. F8 adds a table-aware
  extractor and measures it against this question set. If the question happens to answer correctly on the day,
  say that the baseline is inconsistent on tables and show the flattened chunk.

## What to expect from timing

Measured 2026-10-22: `/ask` took 1-2 s in the morning and 29-79 s that evening with Gemini slow. The UI waits up to
180 s and shows a spinner. Say what it is doing while it waits: routing, retrieval from both indexes, merge,
then the grounded answer.

## Fallbacks

**Gemini slow or busy**
- Slow: keep talking over the spinner; the UI waits 180 s. Don't click twice.
- "Busy" message (503 `llm_unavailable`, after 3 retries): wait about 30 s and ask again, or ask a different
  question. If it keeps failing, show the saved answers in the screenshots and the recorded video.
- Quota used up: switch the model in `.env` (`GEMINI_MODEL=gemini-3.8-flash` also needs
  `GEMINI_ROUTER_THINKING=low` and `GEMINI_ANSWER_THINKING=low`), restart the API, run the warm-up question.

**API down**
- The UI says it can't reach the API and shows the start command. Run Terminal 1 again (about 5 s).
- If the data looks wrong or missing: stop the API, delete `backend\instance\`, copy `backend\instance_backup\`
  back, restart. As a last resort, re-seed (`scripts\seed_corpus.py`, several minutes).

**Backup video and screenshots** (record and save before the demo; not in the repo)
- A recording of all five steps on the seeded state, plus screenshots of each Ask answer with its sources.
  Switch to them if the API or Gemini can't recover within a minute. Say so rather than pretending it's live.

**Retrieval or routing gives a wrong answer live**
- Say so, open the sources to show what was retrieved, and move on. The evaluation numbers in `docs/PROGRESS.md`
  are the honest picture.
