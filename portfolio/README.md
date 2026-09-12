# portfolio/ - phase 3, owner: Arash

Turns a profile's scores (`scores/<profile>/scores.csv`) into portfolio weights.

**Status: placeholder.** `allocate.py` fixes the interface (`allocate(scores, profile)` ->
`ticker, weight, reason`) and the settings a profile can store under `[portfolio]`; the
method itself raises `NotImplementedError`. The dashboard's Portfolio tab shows the plan.
Open questions are in `docs/PLAN.md` (phase 3). Weights must come from deterministic code, like scores.
