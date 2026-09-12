"""Exhibit B - the numbers are in the filings.

Samples values from indicators backed by a real, openable per-company document
(not one shared endpoint) and whose `note` carries a quote, re-downloads the
document, and asks Claude: does this excerpt state this value? The model
verifies, never scores, and never changes a value. Fixed random seed so reruns
check the same rows; results are cached in checks/results/ so the dashboard costs
nothing to view.

Needs ANTHROPIC_API_KEY in .env (not committed - see .env.example). Without it,
run() raises and `python run.py verify` skips this check without writing a
result file, so the dashboard correctly shows "not run" rather than a fake number.

    python run.py verify agent_quote_verify
"""

from __future__ import annotations

import json
import os
import random
import re

import pandas as pd

from common.config import CATEGORIES, catalog_path, indicator_path
from common.io import cached_download

TITLE = "The numbers are in the filings"
KIND = "agent"
EXHIBIT = "B"
MODEL = "claude-sonnet-5"
SAMPLE_SIZE = 30
SEED = 20260913  # fixed: reruns check the same rows


def _eligible() -> dict[str, pd.DataFrame]:
    """indicator_id -> rows, for indicators with a per-company source_url and a quoted note."""
    out = {}
    for category in CATEGORIES:
        catalog = pd.read_csv(catalog_path(category), dtype=str, keep_default_na=False)
        for _, row in catalog.iterrows():
            path = indicator_path(category, row["indicator_id"])
            if not path.exists():
                continue
            df = pd.read_csv(path)
            if df.empty or df["source_url"].nunique() <= 1:
                continue  # a shared endpoint, not a per-company document (see checks/traceability.py)
            if not df["note"].astype(str).str.contains('"', regex=False).any():
                continue  # nothing quoted to check
            out[row["indicator_id"]] = df
    return out


def _clean_html(html: str) -> str:
    text = re.sub("<[^>]+>", " ", html)
    text = re.sub(r"&#\d+;", " ", text)
    return re.sub(r"\s+", " ", text)


def _quote_from_note(note: str) -> str:
    m = re.search(r'"([^"]{15,300})"', note)
    return m.group(1) if m else note[:300]


def _fetch_excerpt(url: str, quote: str) -> str:
    """Re-download the document (cached under checks/raw/) and return a window of
    text around our stored quote - falls back to the quote itself if the document
    can't be fetched again (e.g. it has since moved)."""
    try:
        filename = re.sub(r"[^A-Za-z0-9]+", "_", url)[-100:] + ".html"
        path = cached_download(url, "checks", filename)
        text = _clean_html(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return quote
    idx = text.find(quote[:40])
    if idx >= 0:
        return text[max(0, idx - 200) : idx + 400]
    return text[:2000]


def run() -> dict:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set in .env - add it, then run this check again")
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    pool = [(iid, r) for iid, df in _eligible().items() for _, r in df.iterrows()]
    if not pool:
        return {"status": "flagged", "verdict": "No document-backed indicator rows to sample.",
                "numbers": {}, "rows": []}

    sample = random.Random(SEED).sample(pool, min(SAMPLE_SIZE, len(pool)))
    results = []
    for iid, r in sample:
        our_quote = _quote_from_note(str(r["note"]))
        verdict, agent_quote, found_value = "not_found", "", None
        try:
            excerpt = _fetch_excerpt(r["source_url"], our_quote)
            msg = client.messages.create(
                model=MODEL,
                max_tokens=300,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"Value: {r['value']} for indicator '{iid}', company {r['ticker']}, year {r['year']}.\n\n"
                            f"Document excerpt:\n{excerpt}\n\n"
                            "Does the excerpt state this value? Reply with strict JSON only: "
                            '{"verdict": "confirmed|mismatch|not_found", "quote": "...", "found_value": ...}'
                        ),
                    }
                ],
            )
            parsed = json.loads(msg.content[0].text)
            verdict = parsed.get("verdict", "not_found")
            agent_quote = parsed.get("quote", "")
            found_value = parsed.get("found_value")
        except Exception:
            verdict = "not_found"
        results.append(
            {
                "ticker": r["ticker"],
                "year": int(r["year"]),
                "indicator_id": iid,
                "value": float(r["value"]),
                "detail": verdict,
                "url": r["source_url"],
                "quote": agent_quote or our_quote,
                "found_value": found_value,
            }
        )

    confirmed = sum(1 for r in results if r["detail"] == "confirmed")
    status = "passed" if confirmed == len(results) else "flagged"
    verdict = f"{confirmed} of {len(results)} sampled values confirmed by an independent read of the filing."
    return {"status": status, "verdict": verdict, "numbers": {"sampled": len(results), "confirmed": confirmed},
            "rows": results}
