"""Paths and the shared data format. Every script imports from here - never hardcode paths."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CATEGORIES = ("economic", "social", "environmental")

UNIVERSE_CSV = ROOT / "universe" / "sp500.csv"
UNIVERSE_COLUMNS = ["ticker", "name", "sector", "cik"]

SCORES_DIR = ROOT / "scores"
PROFILES_DIR = ROOT / "profiles"
DEFAULT_PROFILE = "balanced"

CHECKS_DIR = ROOT / "checks"
CHECKS_RESULTS_DIR = CHECKS_DIR / "results"

# One row = one company, one year, one number. See docs/DATA_FORMAT.md.
INDICATOR_COLUMNS = ["ticker", "year", "value", "source", "source_url", "retrieved"]
OPTIONAL_INDICATOR_COLUMNS = ["note"]

CATALOG_COLUMNS = [
    "indicator_id",
    "name",
    "description",
    "unit",
    "higher_is_better",
    "weight",
    "owner",
    "source",
    "status",
]
STATUSES = ("idea", "in_progress", "ready")

# A company only gets a category score if its available indicators carry at least
# this share of the category's total weight. See docs/SCORING.md.
MIN_WEIGHT_SHARE = 0.5

# git refuses files over 100 MB; we stop well before that.
MAX_FILE_MB = 20


def catalog_path(category: str) -> Path:
    return ROOT / category / "catalog.csv"


def indicators_dir(category: str) -> Path:
    return ROOT / category / "indicators"


def indicator_path(category: str, indicator_id: str) -> Path:
    return indicators_dir(category) / f"{indicator_id}.csv"


def raw_dir(category: str) -> Path:
    return ROOT / category / "raw"


def scripts_dir(category: str) -> Path:
    return ROOT / category / "scripts"


def check_result_path(check_id: str) -> Path:
    return CHECKS_RESULTS_DIR / f"{check_id}.json"
