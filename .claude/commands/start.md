---
description: Start a work session - pull the team's latest work and see what to do next
---

1. Run `python run.py start`. If it prints STOP, follow AGENTS.md section 3 and explain the situation in plain words.
2. Run `git config user.name` and figure out which team member this is (Arash, Florian, Lauren, Jean). If unclear, ask.
3. Read `docs/tasks/<name>.md` (especially the last Log entries) and that person's `<category>/catalog.csv`.
4. Run `python run.py check` and note anything in their area.
5. Reply in the person's language, short:
   - what changed in the team since their last log entry (from `git log --oneline -15`)
   - where their indicators stand (idea / in_progress / ready, out of the 3 needed)
   - a suggested next step
   Then wait for them to say what they want to do.

$ARGUMENTS
