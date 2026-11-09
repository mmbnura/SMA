from datetime import date, datetime

import pandas as pd
import pytest

from core.screener import (
    INSUFFICIENT_DATA,
    apply_hard_filters,
    compute_metrics,
    period_return,
    reference_close_date,
    run_scan,
    score_stock,
    tickers_needing_fetch,
)
from core.screening_logic import get_default_config, normalize_config, validate_thresholds
from core.timeutil import IST, now_ist

FULL = {
    "trailingPE": 15.0,
    "pegRatio": 1.0,
    "priceToBook": 2.0,
    "returnOnEquity": 0.20,
    "returnOnAssets": 0.10,
    "debtToEquity": 50.0,
    "marketCap": 1e11,
    "freeCashflow": 5e9,
    "operatingMargins": 0.20,
    "earningsQuarterlyGrowth": 0.10,
    "revenueGrowth": 0.10,
    "currentRatio": 1.5,
    "currency": "INR",
    "financialCurrency": "INR",
    "lastPrice": 100.0,
    "fiftyTwoWeekHigh": 120.0,
    "fiftyTwoWeekLow": 80.0,
    "fetched_at": "2026-11-02T16:00:00+05:30",
}


def test_full_data_scores_with_full_coverage():
    rec = score_stock(FULL, "ABC", "ABC Ltd", "Information Technology", get_default_config())
    assert rec["Status"] == "SCORED"
    assert rec["Data Coverage %"] == 100.0
    assert rec["Unavailable Metrics"] == ""
    assert 0 <= rec["Score"] <= 100
    assert rec["52W Position %"] == 50.0
    assert rec["Market Cap (₹ Cr)"] == 10000


def test_missing_metric_is_excluded_not_zero():
    cfg = get_default_config()
    no_peg = score_stock({**FULL, "pegRatio": None}, "A", "A", "IT", cfg)
    earned = sum(no_peg[c] for c in ("s_PE", "s_PB", "s_ROE", "s_ROA", "s_DE", "s_FCF", "s_OpM", "s_EPS", "s_Rev"))
    # Score is over the 87 points of weight that have data, not the full 100.
    assert no_peg["Score"] == round(earned / 87 * 100)
    assert no_peg["PEG"] is None
    assert no_peg["s_PEG"] is None
    assert "PEG: not provided by Yahoo Finance" in no_peg["Unavailable Metrics"]
    assert no_peg["Data Coverage %"] == pytest.approx(87.0, abs=0.1)


def test_trailing_peg_used_when_peg_missing():
    m = compute_metrics({**FULL, "pegRatio": None, "trailingPegRatio": 0.5}, "IT")
    assert m["peg"].value == 0.5 and m["peg"].points == 13


def test_low_coverage_gives_insufficient_data():
    sparse = {k: FULL[k] for k in ("trailingPE", "priceToBook", "lastPrice", "fetched_at")}
    rec = score_stock(sparse, "X", "X", "IT", get_default_config())
    assert rec["Recommendation"] == INSUFFICIENT_DATA
    assert rec["Data Coverage %"] < 70


def test_financial_sector_de_not_applicable_and_not_counted():
    rec = score_stock({**FULL, "debtToEquity": 900.0, "currentRatio": 0.1}, "B", "Bank", "Financial Services",
                      get_default_config())
    assert rec["Status"] == "SCORED"  # D/E and current-ratio filters do not apply to financials
    assert rec["D/E"] is None and rec["m_DE"] == 0.0
    assert "D/E: not applicable" in rec["Unavailable Metrics"]
    assert rec["Data Coverage %"] == 100.0


def test_negative_values_are_scored_zero_not_hidden():
    m = compute_metrics({**FULL, "trailingPE": -5.0, "priceToBook": -1.0, "debtToEquity": -20.0}, "IT")
    assert m["pe"].value == -5.0 and m["pe"].points == 0
    assert m["pb"].points == 0
    assert m["de"].value == -0.2 and m["de"].points == 0


def test_fcf_yield_requires_matching_currency():
    m = compute_metrics({**FULL, "financialCurrency": "USD"}, "IT")
    assert m["fcf_yield"].status == "missing" and "USD" in m["fcf_yield"].note
    m = compute_metrics({**FULL, "financialCurrency": None}, "IT")
    assert m["fcf_yield"].status == "missing"


def test_hard_filters_report_all_reasons_with_values():
    reasons = apply_hard_filters(
        {"currentRatio": 0.5, "returnOnEquity": -0.1, "debtToEquity": 400.0,
         "freeCashflow": -1.0, "operatingMargins": -0.05},
        "IT",
    )
    assert len(reasons) == 4
    assert "0.50" in reasons[0] and "-10.0%" in reasons[1]


def test_hard_filters_skip_missing_values():
    assert apply_hard_filters({}, "IT") == []
    assert apply_hard_filters({"currentRatio": float("nan")}, "IT") == []


def test_nan_inputs_from_csv_are_missing():
    rec = score_stock({**FULL, "returnOnEquity": float("nan")}, "A", "A", "IT", get_default_config())
    assert rec["ROE %"] is None


def test_disabled_metric_not_listed_or_counted():
    cfg = get_default_config()
    for m in cfg["metrics"]:
        if m["id"] == "peg":
            m["enabled"] = False
    rec = score_stock({**FULL, "pegRatio": None}, "A", "A", "IT", cfg)
    assert rec["Data Coverage %"] == 100.0
    assert "PEG" not in rec["Unavailable Metrics"]


def test_run_scan_accounts_for_every_stock():
    cache = pd.DataFrame([
        {**FULL, "Ticker": "GOOD"},
        {**FULL, "Ticker": "BAD", "returnOnEquity": -0.2},
    ])
    stocks = [("GOOD.NS", "Good", "IT"), ("BAD.NS", "Bad", "IT"), ("NONE.NS", "None", "IT")]
    res = run_scan(stocks, cache, get_default_config(), [{"Ticker": "NONE", "Reason": "boom"}])
    assert res.in_scope == 3
    assert list(res.scored["Ticker"]) == ["GOOD"]
    assert list(res.disqualified["Ticker"]) == ["BAD"]
    assert res.unavailable.iloc[0]["Reason"] == "boom"


def test_tickers_needing_fetch():
    fresh = now_ist().isoformat()
    cache = pd.DataFrame([
        {"Ticker": "FRESH", "fetched_at": fresh},
        {"Ticker": "OLD", "fetched_at": "2020-01-01T10:00:00+05:30"},
        {"Ticker": "UNDATED", "fetched_at": None},
    ])
    need = tickers_needing_fetch(cache, ["FRESH", "OLD", "UNDATED", "NEW"], 24)
    assert set(need) == {"OLD", "UNDATED", "NEW"}


def test_reference_close_date():
    assert reference_close_date(datetime(2026, 5, 25, 7, 31, tzinfo=IST)) == date(2026, 5, 24)
    assert reference_close_date(datetime(2026, 5, 25, 16, 0, tzinfo=IST)) == date(2026, 5, 25)


def test_period_return_uses_last_close_on_or_before_reference():
    s = pd.Series([100.0, 110.0, 121.0], index=[date(2026, 5, 22), date(2026, 5, 26), date(2026, 5, 27)])
    r = period_return(s, date(2026, 5, 24))
    assert r["start_date"] == date(2026, 5, 22)
    assert r["return_pct"] == pytest.approx(21.0)
    assert period_return(s, date(2026, 5, 1)) is None


def test_thresholds_validation():
    assert validate_thresholds({"strong_buy": 60, "buy": 70, "hold": 40})[1] is not None
    assert validate_thresholds({"strong_buy": 80, "buy": 70, "hold": 40}) == (
        {"strong_buy": 80, "buy": 70, "hold": 40}, None)


def test_legacy_config_is_migrated():
    legacy = {"version": 1, "metrics": [{"id": "pe", "enabled": False, "weight": 5}],
              "recommendation_thresholds": {"strong_buy": 75, "buy": 60, "hold": 45}}
    cfg = normalize_config(legacy)
    assert cfg["version"] == 2 and cfg["min_data_coverage"] == 70
    pe = next(m for m in cfg["metrics"] if m["id"] == "pe")
    assert pe["enabled"] is False and pe["weight"] == 5


def test_fetch_upserts_cache_and_keeps_rows_on_failure(tmp_path, monkeypatch):
    import core.screener as screener
    from core.screener import FetchError, fetch_and_cache_base_data, load_base_cache

    path = tmp_path / "base.csv"
    pd.DataFrame([
        {"Ticker": "OLD", "Name": "Old", "Sector": "IT", "trailingPE": 9.0, "fetched_at": "2020-01-01T10:00:00+05:30"},
        {"Ticker": "FAIL", "Name": "Fail", "Sector": "IT", "trailingPE": 5.0, "fetched_at": "2020-01-01T10:00:00+05:30"},
    ]).to_csv(path, index=False)

    def fake_fetch(yf_ticker):
        if yf_ticker == "FAIL.NS":
            raise FetchError("boom")
        return {**{k: None for k in screener.YF_FIELDS}, "trailingPE": 20.0, "lastPrice": 1.0,
                "fetched_at": now_ist().isoformat()}

    monkeypatch.setattr(screener, "fetch_fundamentals", fake_fetch)
    cache, failures = fetch_and_cache_base_data(
        [("OLD.NS", "Old", "IT"), ("NEW.NS", "New", "IT"), ("FAIL.NS", "Fail", "IT")], path
    )
    saved = load_base_cache(path).set_index("Ticker")
    assert set(saved.index) == {"OLD", "NEW", "FAIL"}
    assert saved.loc["OLD", "trailingPE"] == 20.0
    assert saved.loc["FAIL", "trailingPE"] == 5.0
    assert failures == [{"Ticker": "FAIL", "Name": "Fail", "Sector": "IT", "Reason": "boom — older cached data kept"}]
