# Agent layer. LLM calls live ONLY in here and in sources/reports.py.
#
# The architectural rule from CLAUDE.md, restated because it matters most here:
#   agents turn unstructured documents into structured rows.
#   agents NEVER produce a score, a weight, or a portfolio position.
#
# If you find yourself wanting an LLM to decide a number that ends up in
# company_scores.parquet, stop - that number has to come from deterministic code
# or we cannot answer "why 0.40?" on stage.
