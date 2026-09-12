# Adversarial check on our own output. OWNER: Harprit. Run at ~07:00.
#
# Two payoffs: you patch the holes before Q&A, and "we ran an adversarial agent
# against our own rankings, here is what it found" signals more maturity than any
# amount of model architecture.

from __future__ import annotations

import pandas as pd

from ..agents.client import MODEL, client

SYSTEM = (
    "You are a hostile reviewer at an investment committee. You are shown a "
    "sustainability ranking and the evidence behind it. Your job is to build the "
    "strongest possible case that the ranking is WRONG.\n\n"
    "Attack in this order: (1) is the data actually measuring what they claim, "
    "(2) is the peer group wrong, (3) is there a confound that explains the ranking "
    "without the causal story, (4) what would a short seller say. Be specific and "
    "quantitative. Do not be polite. If an attack does not work, say so - a fake "
    "objection wastes their preparation time."
)


def attack(scores: pd.DataFrame, evidence: pd.DataFrame, n: int = 5) -> str:
    top = scores.nlargest(n, "score")
    bottom = scores.nsmallest(n, "score")
    resp = client().messages.create(
        model=MODEL,
        max_tokens=8192,
        system=SYSTEM,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        messages=[{
            "role": "user",
            "content": (
                "Best-ranked:\n" + top.to_markdown()
                + "\n\nWorst-ranked:\n" + bottom.to_markdown()
                + "\n\nUnderlying evidence:\n" + evidence.head(40).to_markdown()
                + "\n\nWhere is this ranking wrong?"
            ),
        }],
    )
    return "".join(b.text for b in resp.content if b.type == "text")
