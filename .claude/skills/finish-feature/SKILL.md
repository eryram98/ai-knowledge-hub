---
name: finish-feature
description: Wrap up a finished feature. Run every check, update docs/PROGRESS.md, commit, and print the end-of-session summary from AGENTS.md.
---

Finish the current feature. $ARGUMENTS

1. Run every check listed under "Commands" in `AGENTS.md`, with `.venv\Scripts\python`
   (tests, plus Ruff and the Streamlit smoke test once they exist). If anything fails or
   is skipped, fix it, or stop and report the exact output. Never commit with a failing check.
2. Check the feature against its "Done when" in `docs/SPEC.md`, point by point. If a
   point isn't met, say so. Don't mark the feature done. Either finish it or commit as
   `wip:` (step 5).
3. Run `git status` and `git diff <parent>...HEAD --stat`, where `<parent>` is the branch
   this one was created from (the branch stack is at the top of PROGRESS.md; use `main`
   once the stack is merged). Make sure only this feature's files changed and nothing
   from anyone else's uncommitted work is included.
4. Update `docs/PROGRESS.md`:
   - The feature table: status, branch, and commit. Write "this commit", because the hash
     doesn't exist yet. The next PROGRESS.md update replaces it with the real short hash.
   - "Now": current feature, next concrete step, and add this branch to the stack if
     it's new.
   - The session log: date, branch, what was finished, test count.
   - Decisions (via the `/decide` format), deviations, known issues and open questions
     found during the work.
   - Evaluation numbers, if they were measured.
   - The AI-written code list: every file Claude wrote or substantially changed.
   - The countdown: days left to the next milestone and what's at risk.
5. Commit the feature and PROGRESS.md together with a conventional commit message
   (`feat:`, `fix:`, `test:`, `docs:`, `chore:`; `wip:` for an unfinished stop). Never
   push, merge or open a PR.
6. Print the end-of-session summary in the exact format from `AGENTS.md`. Under "What's
   done", list every change to Erynn's modules (tasks 1-3) so Ethan can tell her.
7. Print the command Ethan can run to push (`git push -u origin <branch>`), and say
   whether a PR for Erynn makes sense now.
8. If the feature included a coach-mode piece, ask Ethan one likely professor or
   interviewer question about it. Wait for his answer before explaining.
