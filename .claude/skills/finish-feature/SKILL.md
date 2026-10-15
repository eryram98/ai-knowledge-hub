---
name: finish-feature
description: Wrap up a finished feature. Run the tests, update docs/tasks.md, commit, and print the updated task list.
---

Finish the current feature. $ARGUMENTS

1. Run `python -m unittest discover -s backend\tests`. If anything fails or is skipped, stop and report it. Do not continue.
2. Run `git diff main...HEAD --stat` and `git status` to see what this branch changed.
3. Update `docs/tasks.md`:
   - Check off every subtask this branch completed. Only check off what the code and tests actually do.
   - Check off the parent task only when all of its non-deferred subtasks are done.
   - Move the `— next` marker to the next unchecked task.
   - Add a line to the Progress log: date, branch, what was finished, test count.
   - If work revealed a missing task, add it, labeled `(added)`.
4. Commit the task list with the feature, using a conventional commit message.
5. Print the full updated task list in the chat.
6. Print exactly what Ethan needs to do next: the push command, whether to open a PR for Erynn, and anything to tell her (for example a convention she needs to follow).
7. List up to three questions a professor could ask about this feature. Wait for Ethan's answers before explaining.
