# Runtime knobs. No magic numbers in the core - the dashboard mutates these.
# OWNER: Arash. Add a constant here rather than hardcoding it in your layer.

from __future__ import annotations

CARBON_PRICES = (50.0, 100.0, 200.0)          # USD per tonne CO2e
BOOTSTRAP_N = 500                              # CI resamples
TIER_EDGES = (0.80, 0.60, 0.40, 0.20)          # A/B/C/D/E percentile cuts
MIN_COVERAGE_TO_RANK = 0.30                    # below this we refuse to rank, we flag

DATA_ROOT = "data"
RAW = f"{DATA_ROOT}/raw"
MOCK = f"{DATA_ROOT}/mock"
PROCESSED = f"{DATA_ROOT}/processed"
MANUAL = f"{DATA_ROOT}/manual"

SEC_USER_AGENT = "EThack hackathon research arashbayat.13834@gmail.com"

# Durability -> weight multiplier used by the confidence-weighting mode.
# Rationale: an indicator whose source may not exist next year should not carry
# the same weight as one nobody can switch off.
DURABILITY_WEIGHT = {
    "permanent": 1.00,
    "statutory": 0.95,
    "at_risk": 0.70,
    "voluntary": 0.45,
    "derived": 0.80,
}
