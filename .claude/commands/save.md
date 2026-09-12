---
description: Save work - log progress, commit, pull, check and push safely
---

1. Run `python run.py status` and look at every changed file. If a file is outside the
   area of the person you help (AGENTS.md section 2), do not save it - explain and ask.
2. Append a short entry to the Log in `docs/tasks/<name>.md` (format: AGENTS.md section 6).
   Only numbers you actually saw printed.
3. Run `python run.py save "[area] concrete past-tense message"`. Use the person's hint if given: $ARGUMENTS
4. If it prints STOP or NOT PUSHED, follow the table in AGENTS.md section 3.
   Never use force-push, reset or other destructive git commands.
5. Tell the person in one or two plain sentences what was saved and whether it is on GitHub.
