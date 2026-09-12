import pandas as pd

from common.validate import Report, check_catalog_frame, check_indicator_text

HEADER = "ticker,year,value,source,source_url,retrieved,note\n"
GOOD_ROW = "AAPL,2024,0.12,SEC XBRL,https://data.sec.gov/x,2026-09-12,\n"


def messages(report):
    return " | ".join(m for _, m in report.errors)


def test_good_file_passes():
    assert check_indicator_text(HEADER + GOOD_ROW, "t").errors == []


def test_missing_source_is_an_error():
    report = check_indicator_text(HEADER + "AAPL,2024,0.12,SEC XBRL,,2026-09-12,\n", "t")
    assert "source_url" in messages(report)


def test_bad_values_are_caught():
    text = HEADER + GOOD_ROW + "msft,24.5,n/a,SEC,https://x,12.09.2026,\n"
    msg = messages(check_indicator_text(text, "t"))
    for expected in ("ticker", "year", "value", "retrieved"):
        assert expected in msg


def test_duplicate_ticker_year_is_an_error():
    assert "twice" in messages(check_indicator_text(HEADER + GOOD_ROW + GOOD_ROW, "t"))


def test_extra_columns_are_rejected():
    text = "ticker,year,value,source,source_url,retrieved,sector\nAAPL,2024,1,S,https://x,2026-09-12,Tech\n"
    assert "unexpected columns" in messages(check_indicator_text(text, "t"))


def test_unknown_ticker_is_only_a_warning():
    report = check_indicator_text(HEADER + GOOD_ROW, "t", universe={"MSFT"})
    assert report.errors == []
    assert any("not in universe" in m for _, m in report.warnings)


def test_catalog_rules():
    df = pd.DataFrame(
        [
            ["good_one", "N", "D", "%", "true", "1", "Jean", "EPA", "ready"],
            ["Bad-Id", "", "", "", "yes", "0", "", "", "done"],
        ],
        columns=["indicator_id", "name", "description", "unit", "higher_is_better", "weight", "owner", "source", "status"],
    )
    report = Report()
    check_catalog_frame(df, "c", report)
    msg = messages(report)
    for expected in ("snake_case", "higher_is_better", "weight", "status"):
        assert expected in msg
    assert "good_one" not in msg
