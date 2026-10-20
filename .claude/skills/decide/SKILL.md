---
name: decide
description: Record a team decision in the decision log in docs/PROGRESS.md. Use after Ethan picks an option for an open decision or a coach-mode piece, or to log a small call Claude made.
---

Record this decision: $ARGUMENTS

1. Read the "Decision log" section of `docs/PROGRESS.md`. If the topic is already there,
   update that row (keep the original date in the notes, set the new date) instead of
   adding a duplicate. If the topic is in the "Still open" line under the table, remove it
   from there.
2. Confirm with Ethan, in one short message, before writing:
   - The choice
   - The alternatives he ruled out and why (write "Not recorded" only if he declines to give them)
   - The owner (Ethan or Erynn)
   Skip the confirmation only for a small call Claude made itself. Mark those rows
   "(Claude, small call)" and mention them in the end-of-session summary.
3. Add the row at the top of the table (newest first) with today's date.
4. If the decision changes scope, stack, constraints or a feature's "Done when", update
   `docs/SPEC.md` to match in the same change. If it deviates from SPEC.md or the Phase 1
   deck, add it under "Deviations" in PROGRESS.md.
5. Remind Ethan to copy the row into the decision table of the
   `knowledge-hub-project-context` file in the Claude Project.
