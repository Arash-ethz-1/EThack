# Shared Anthropic client + structured extraction helper.
# OWNER: Arash. Used by Jean (reports.py) and Harprit (redteam.py).

from __future__ import annotations

import json
import os
from typing import Any

from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-opus-5"


def client():
    # Import locally so the rest of the pipeline works without the SDK installed.
    import anthropic

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and fill it in. "
            "Only the agent layers need this - the rest of the pipeline does not."
        )
    return anthropic.Anthropic()


# The citation rule is enforced by the schema, not by good intentions:
# every extracted figure must arrive with the words it came from.
SCOPE1_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["found", "reported_scope1_t", "verbatim_quote", "page", "confidence"],
    "properties": {
        "found": {
            "type": "boolean",
            "description": "false if the document does not state a Scope 1 figure",
        },
        "reported_scope1_t": {
            "type": ["number", "null"],
            "description": "Scope 1 gross emissions in metric tonnes CO2e. "
                           "Convert if the document reports Mt or kt.",
        },
        "base_year": {"type": ["integer", "null"]},
        "target_year": {"type": ["integer", "null"]},
        "target_pct": {
            "type": ["number", "null"],
            "description": "Fractional reduction target, e.g. 0.42 for a 42% cut",
        },
        "assurance_provider": {
            "type": ["string", "null"],
            "description": "Third party that assured the figure, null if none stated",
        },
        "verbatim_quote": {
            "type": "string",
            "description": "The exact sentence containing the figure, copied character "
                           "for character. Empty string only if found is false.",
        },
        "page": {"type": ["integer", "null"]},
        "confidence": {"type": "number", "description": "0-1, your own confidence"},
        "notes": {"type": ["string", "null"]},
    },
}

SCOPE1_SYSTEM = (
    "You extract greenhouse gas figures from corporate sustainability reports for a "
    "financial risk audit. Accuracy matters more than completeness.\n\n"
    "Rules:\n"
    "- Report Scope 1 GROSS emissions. Never net-of-offsets. If only net is given, "
    "set found=false and say so in notes.\n"
    "- Convert to metric tonnes CO2e. State the original unit in notes.\n"
    "- verbatim_quote must be copied exactly from the source. Never paraphrase it. "
    "If you cannot quote it, you did not find it: set found=false.\n"
    "- If the document is ambiguous, set found=false rather than guessing. A missing "
    "row costs us coverage; a wrong row costs us the audit."
)


def extract_scope1(document_text: str, company: str) -> dict[str, Any]:
    # Returns a dict matching SCOPE1_SCHEMA. Caller is responsible for rejecting
    # rows where found is false or verbatim_quote is empty.
    resp = client().messages.create(
        model=MODEL,
        max_tokens=4096,
        system=SCOPE1_SYSTEM,
        thinking={"type": "adaptive"},
        output_config={
            "effort": "medium",
            "format": {
                "type": "json_schema",
                "name": "scope1_extraction",
                "schema": SCOPE1_SCHEMA,
            },
        },
        messages=[{
            "role": "user",
            "content": (
                f"Company: {company}\n\n"
                f"Extract the Scope 1 figure from this report.\n\n{document_text}"
            ),
        }],
    )
    text = "".join(b.text for b in resp.content if b.type == "text")
    return json.loads(text)


def adjudicate(company: str, extracted: float, metered: float,
               document_text: str) -> dict[str, Any]:
    # Second pass when the extracted figure and the metered sum disagree by >2x.
    # One of three things is true and we need to know which:
    #   the extraction is wrong / the company under-reports / our facility join is wrong.
    resp = client().messages.create(
        model=MODEL,
        max_tokens=4096,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        system=(
            "You are auditing a discrepancy between a company's self-reported Scope 1 "
            "emissions and the sum of EPA-metered emissions at facilities it owns. "
            "Exactly one of three explanations is usually right: (1) the extraction "
            "read the wrong number, (2) the company's disclosure excludes facilities it "
            "controls, (3) our facility-to-parent attribution is wrong. Say which, and "
            "quote the evidence. Do not soften the finding, and do not invent one."
        ),
        messages=[{
            "role": "user",
            "content": (
                f"Company: {company}\n"
                f"Extracted from their report: {extracted:,.0f} tCO2e\n"
                f"Sum of EPA-metered facilities we attribute to them: {metered:,.0f} tCO2e\n"
                f"Ratio: {metered / extracted if extracted else float('nan'):.2f}x\n\n"
                f"Report text:\n{document_text}"
            ),
        }],
    )
    return {"analysis": "".join(b.text for b in resp.content if b.type == "text")}
