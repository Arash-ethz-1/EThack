"""Checks that every catalog and indicator file follows docs/DATA_FORMAT.md.

    python run.py check

Errors block `python run.py save` for the category you changed. Warnings never block.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

import pandas as pd

from common.config import (
    CATALOG_COLUMNS,
    CATEGORIES,
    INDICATOR_COLUMNS,
    OPTIONAL_INDICATOR_COLUMNS,
    STATUSES,
    UNIVERSE_COLUMNS,
    UNIVERSE_CSV,
    catalog_path,
    indicator_path,
    indicators_dir,
)

ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass
class Report:
    errors: list[tuple[str, str]] = field(default_factory=list)  # (area, message)
    warnings: list[tuple[str, str]] = field(default_factory=list)

    def error(self, area: str, msg: str) -> None:
        self.errors.append((area, msg))

    def warn(self, area: str, msg: str) -> None:
        self.warnings.append((area, msg))


def read_csv_as_text(source) -> pd.DataFrame:
    """Read every cell as a string so validation sees exactly what is in the file."""
    return pd.read_csv(source, dtype=str, keep_default_na=False)


def load_universe_tickers() -> set[str] | None:
    if not UNIVERSE_CSV.exists():
        return None
    df = read_csv_as_text(UNIVERSE_CSV)
    return set(df["ticker"]) if "ticker" in df.columns else None


def check_catalog_frame(df: pd.DataFrame, area: str, report: Report) -> None:
    missing = [c for c in CATALOG_COLUMNS if c not in df.columns]
    if missing:
        report.error(area, f"catalog is missing columns {missing}")
        return
    ids = df["indicator_id"]
    for dup in sorted(set(ids[ids.duplicated()])):
        report.error(area, f"indicator_id '{dup}' appears more than once")
    for i, row in df.iterrows():
        line = f"catalog row {i + 2}"
        if not ID_PATTERN.match(row["indicator_id"]):
            report.error(area, f"{line}: indicator_id '{row['indicator_id']}' must be lowercase_snake_case")
        if row["higher_is_better"] not in ("true", "false"):
            report.error(area, f"{line}: higher_is_better must be 'true' or 'false', got '{row['higher_is_better']}'")
        try:
            if float(row["weight"]) <= 0:
                raise ValueError
        except ValueError:
            report.error(area, f"{line}: weight must be a number > 0, got '{row['weight']}'")
        if row["status"] not in STATUSES:
            report.error(area, f"{line}: status must be one of {STATUSES}, got '{row['status']}'")
        for col in ("name", "description", "unit", "owner", "source"):
            if not row[col].strip() and row["status"] == "ready":
                report.error(area, f"{line}: '{col}' is empty but status is ready")


def check_indicator_frame(
    df: pd.DataFrame, area: str, report: Report, universe: set[str] | None = None
) -> None:
    missing = [c for c in INDICATOR_COLUMNS if c not in df.columns]
    if missing:
        report.error(area, f"missing columns {missing}")
        return
    extra = [c for c in df.columns if c not in INDICATOR_COLUMNS + OPTIONAL_INDICATOR_COLUMNS]
    if extra:
        report.error(area, f"unexpected columns {extra} - put extra info in 'note' or a raw file")
    if df.empty:
        report.error(area, "file has no rows")
        return

    def bad_rows(mask: pd.Series) -> str:
        rows = [str(i + 2) for i in df.index[mask][:5]]
        more = "" if mask.sum() <= 5 else f" (+{mask.sum() - 5} more)"
        return ", ".join(rows) + more

    ticker = df["ticker"]
    mask = (ticker.str.strip() == "") | (ticker != ticker.str.strip().str.upper())
    if mask.any():
        report.error(area, f"ticker must be non-empty UPPERCASE without spaces (rows {bad_rows(mask)})")

    year = pd.to_numeric(df["year"], errors="coerce")
    mask = year.isna() | (year % 1 != 0) | (year < 1990) | (year > 2100)
    if mask.any():
        report.error(area, f"year must be a whole number like 2024 (rows {bad_rows(mask)})")

    value = pd.to_numeric(df["value"], errors="coerce")
    mask = value.isna() | value.abs().eq(float("inf"))
    if mask.any():
        report.error(area, f"value must be a number - drop rows without data (rows {bad_rows(mask)})")

    for col in ("source", "source_url"):
        mask = df[col].str.strip() == ""
        if mask.any():
            report.error(area, f"'{col}' is empty - no source, no row (rows {bad_rows(mask)})")

    mask = ~df["retrieved"].str.match(DATE_PATTERN)
    if mask.any():
        report.error(area, f"retrieved must be a date YYYY-MM-DD (rows {bad_rows(mask)})")

    dup = df.duplicated(subset=["ticker", "year"], keep=False)
    if dup.any():
        report.error(area, f"same ticker+year appears twice (rows {bad_rows(dup)})")

    if universe is not None:
        unknown = sorted(set(ticker) - universe)
        if unknown:
            report.warn(area, f"{len(unknown)} tickers not in universe/sp500.csv, e.g. {unknown[:5]}")
        if year.notna().any():
            latest_year = int(year.max())
            covered = len(set(df.loc[year == latest_year, "ticker"]) & universe)
            if covered < 0.7 * len(universe):
                report.warn(area, f"coverage {covered}/{len(universe)} companies in {latest_year} (target: 70%)")


def check_indicator_text(csv_text: str, area: str, universe: set[str] | None = None) -> Report:
    report = Report()
    check_indicator_frame(read_csv_as_text(io.StringIO(csv_text)), area, report, universe)
    return report


def validate_all() -> Report:
    report = Report()
    universe = load_universe_tickers()
    if universe is None:
        report.warn("universe", "universe/sp500.csv does not exist yet - tickers are not checked")
    else:
        header = read_csv_as_text(UNIVERSE_CSV).columns.tolist()
        if header[: len(UNIVERSE_COLUMNS)] != UNIVERSE_COLUMNS:
            report.error("universe", f"universe/sp500.csv must start with columns {UNIVERSE_COLUMNS}")

    seen_ids: dict[str, str] = {}
    for category in CATEGORIES:
        path = catalog_path(category)
        if not path.exists():
            report.error(category, f"{category}/catalog.csv is missing")
            continue
        catalog = read_csv_as_text(path)
        check_catalog_frame(catalog, category, report)
        if "indicator_id" not in catalog.columns:
            continue

        for _, row in catalog.iterrows():
            ind = row["indicator_id"]
            if ind in seen_ids and seen_ids[ind] != category:
                report.error(category, f"indicator_id '{ind}' is also used in {seen_ids[ind]}")
            seen_ids[ind] = category
            file = indicator_path(category, ind)
            area = f"{category}/indicators/{ind}.csv"
            if file.exists():
                check_indicator_frame(read_csv_as_text(file), area, report, universe)
            elif row.get("status") == "ready":
                report.error(area, "status is ready but the file does not exist")

        listed = set(catalog["indicator_id"])
        for file in sorted(indicators_dir(category).glob("*.csv")):
            if file.stem not in listed:
                report.error(f"{category}/indicators/{file.name}", "file is not listed in catalog.csv")

        ready = int((catalog.get("status") == "ready").sum()) if "status" in catalog.columns else 0
        if ready < 3:
            report.warn(category, f"{ready}/3 indicators are 'ready'")
    return report


def print_report(report: Report) -> None:
    for area, msg in report.warnings:
        print(f"  WARN   {area}: {msg}")
    for area, msg in report.errors:
        print(f"  ERROR  {area}: {msg}")
    if not report.errors:
        print(f"  OK - format check passed ({len(report.warnings)} warnings)")


if __name__ == "__main__":
    r = validate_all()
    print_report(r)
    raise SystemExit(1 if r.errors else 0)
