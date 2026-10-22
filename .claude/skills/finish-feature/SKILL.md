---
name: finish-feature
description: Wrap up a finished feature. Confirm the checks, update docs/PROGRESS.md, commit, and print the end-of-session summary from AGENTS.md.
---

Finish the current feature. $ARGUMENTS

1. Checks: if every check under "Commands" in `AGENTS.md` passed in this session and no
   code changed since, reuse those results. Otherwise run them again, printing only the
   summary lines (`Ran`, `OK`/`FAILED`, Ruff's result) plus any traceback. Never commit with
   a failing check.
2. Check the feature against its "Done when" in `docs/SPEC.md`, point by point. If a
   point isn't met, say so. Don't mark the feature done. Either finish it or commit as
   `wip:` (step 5).
3. Run `git status --short` and make sure only this feature's files changed and nothing
   from anyone else's uncommitted work is included.
4. Update `docs/PROGRESS.md` with targeted edits, keeping it under 150 lines:
   - The feature table: status, branch, and commit. Write "this commit", because the hash
     doesn't exist yet. The next PROGRESS.md update replaces it with the real short hash.
   - "Now": current feature, next concrete step, branch.
   - The session log: one short entry with the date, branch, what was finished and the
     test counts, inserted at the top of "Session log (archived)" in
     `docs/PROGRESS_ARCHIVE.md`. Grep for that heading; don't read the archive.
   - Decisions (one line each), deviations, known issues and open questions found during
     the work, only if there are new ones. Move superseded or resolved ones to the archive.
   - Evaluation numbers, only if they were measured.
   - The AI-written code list: every file Claude wrote or substantially changed.
   - The countdown, only if a risk changed.
5. Commit the feature and PROGRESS.md together with a conventional commit message
   (`feat:`, `fix:`, `test:`, `docs:`, `chore:`; `wip:` for an unfinished stop). Never
   push, merge or open a PR.
6. Print the end-of-session summary in the 8-point format from `AGENTS.md`, keeping each
   point brief and pointing to PROGRESS.md for detail instead of repeating it. Under
   "What's done", list every change to Erynn's modules (tasks 1-3). End with the push
   command (`git push -u origin <branch>`) and whether a PR for Erynn makes sense now.
7. If the feature included a coach-mode piece, ask Ethan one likely professor or
   interviewer question about it. Wait for Ethan's answer before explaining.
