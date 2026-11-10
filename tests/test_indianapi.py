from datetime import timedelta

import pandas as pd
import pytest

from core import indianapi
from core.indianapi import (
    ApiError,
    IndianApiClient,
    UsageCounter,
    fill_gaps,
    load_cache,
    merge_fallback,
    parse_stock,
    symbols_to_fetch,
)
from core.screener import run_scan
from core.screening_logic import get_default_config
from core.timeutil import now_ist
from tests.test_screener import FULL

TODAY = now_ist().date()


def payload(symbol="TCS", pdate=None, **overrides):
    """A trimmed /stock response with the structure IndianAPI returns (keys as seen live, incl. a stray ')')."""
    metrics = {
        "valuation": {"pPerEIncludingExtraordinaryItemsTTM": "17.36", "pegRatio": "3.05",
                      "priceToBookMostRecentQuarter": "7.53"},
        "mgmtEffectiveness": {"returnOnAverageEquityTrailing12Month": "45.79",
                              "returnOnAverageAssetsTrailing12Month": "28.34"},
        "margins": {"operatingMarginTrailing12Month": "23.19"},
        "growth": {"revenueChangePercentMostRecentQuarter1YearAgo": "11.23",
                   "ePSChangePercentMostRecentQuarter1YearAgo)": "14.97"},
        "financialstrength": {"totalDebtPerTotalEquityMostRecentQuarter": "0.10",
                              "currentRatioMostRecentQuarter": None, "currentRatioMostRecentFiscalYear": "2.23"},
        "priceandVolume": {"marketCap": "903816.35", "PDATE": (pdate or TODAY.isoformat()) + "T00:00:00"},
    }
    for key, value in overrides.items():
        for group in metrics.values():
            if key in group:
                group[key] = value
    return {
        "companyName": "Tata Consultancy Services",
        "companyProfile": {"exchangeCodeNse": symbol},
        "keyMetrics": {g: [{"key": k, "value": v} for k, v in items.items()] for g, items in metrics.items()},
    }


def test_parse_converts_units_to_yahoo_conventions():
    got = parse_stock(payload(), "TCS")
    v = got["values"]
    assert v["trailingPE"] == pytest.approx(17.36) and v["pegRatio"] == pytest.approx(3.05)
    assert v["returnOnEquity"] == pytest.approx(0.4579)  # percent -> decimal
    assert v["earningsQuarterlyGrowth"] == pytest.approx(0.1497)  # key with a stray ')' still matched
    assert v["debtToEquity"] == pytest.approx(10.0)  # ratio -> Yahoo's percent
    assert v["currentRatio"] == pytest.approx(2.23)  # falls back to the fiscal-year value
    assert v["marketCap"] == pytest.approx(903816.35e7)  # ₹ crore -> rupees
    assert "freeCashflow" not in v  # different definition from Yahoo: never filled


def test_parse_rejects_wrong_company_and_stale_data():
    with pytest.raises(ApiError, match="different company") as err:
        parse_stock(payload(symbol="TATAELXSI"), "TCS")
    assert err.value.kind == "mismatch"
    old = (TODAY - timedelta(days=60)).isoformat()
    with pytest.raises(ApiError, match="older than 30 days"):
        parse_stock(payload(pdate=old), "TCS")


class FakeResponse:
    def __init__(self, status, body=None):
        self.status_code = status
        self._body = body

    def json(self):
        if self._body is None:
            raise ValueError
        return self._body


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append((params["name"], headers["X-Api-Key"]))
        return self.responses.pop(0)


def client(tmp_path, responses, limit=5000):
    return IndianApiClient("secret", UsageCounter(tmp_path / "usage.json"), monthly_limit=limit, gap_seconds=0,
                           session=FakeSession(responses))


def test_lookup_falls_back_to_company_name_and_counts_usage(tmp_path):
    c = client(tmp_path, [FakeResponse(200, payload(symbol="TATAELXSI")), FakeResponse(200, payload())])
    cache, out = fill_gaps(c, [("TCS", "Tata Consultancy Services")], tmp_path / "api.csv", max_requests=10)
    assert c.session.calls == [("TCS", "secret"), ("Tata Consultancy Services", "secret")]
    assert c.usage.used == 2 and out.filled_stocks == 1
    row = load_cache(tmp_path / "api.csv").set_index("Ticker").loc["TCS"]
    assert row["status"] == "ok" and row["pegRatio"] == pytest.approx(3.05)


def test_bad_key_stops_the_run(tmp_path):
    c = client(tmp_path, [FakeResponse(401, {})])
    _, out = fill_gaps(c, [("TCS", "TCS"), ("INFY", "Infosys")], tmp_path / "api.csv", max_requests=10)
    assert out.requested == 1 and "rejected the API key" in out.stopped


def test_monthly_and_per_scan_limits(tmp_path):
    c = client(tmp_path, [], limit=0)
    _, out = fill_gaps(c, [("TCS", "TCS")], tmp_path / "api.csv", max_requests=10)
    assert "Monthly IndianAPI limit reached" in out.stopped and c.session.calls == []

    c = client(tmp_path, [FakeResponse(200, payload())] * 3)
    c.usage.path = tmp_path / "usage2.json"
    _, out = fill_gaps(c, [("TCS", "TCS"), ("TCS", "TCS"), ("TCS", "TCS")], tmp_path / "api2.csv", max_requests=2)
    assert out.requested == 2 and "per-scan limit" in out.stopped


def test_only_stocks_with_gaps_and_no_recent_attempt_are_fetched():
    base = pd.DataFrame([{**FULL, "Ticker": "FULL"}, {**FULL, "Ticker": "GAP", "pegRatio": None},
                         {**FULL, "Ticker": "TRIED", "pegRatio": None}, {**FULL, "Ticker": "NET", "pegRatio": None}])
    recent = now_ist().isoformat()
    api = pd.DataFrame([
        {"Ticker": "TRIED", "fetched_at": recent, "status": "mismatch"},
        {"Ticker": "NET", "fetched_at": recent, "status": "network"},
    ])
    assert symbols_to_fetch(base, api, ["FULL", "GAP", "TRIED", "NET", "NODATA"]) == ["GAP", "NET"]


def test_merge_fills_gaps_only_and_scan_shows_sources():
    api_row = {"status": "ok", "as_of": TODAY.isoformat(), "pegRatio": 1.0, "returnOnEquity": 0.99,
               "currentRatio": 0.5}
    merged = merge_fallback({**FULL, "pegRatio": None, "currentRatio": None}, api_row)
    assert merged["pegRatio"] == 1.0 and merged["returnOnEquity"] == FULL["returnOnEquity"]  # Yahoo value kept
    assert merged["_filled"] == ["PEG", "Current ratio"]
    assert merge_fallback(FULL, {**api_row, "as_of": "2020-01-01"})["_filled"] == []  # too old: nothing filled

    cache = pd.DataFrame([{**FULL, "Ticker": "A", "pegRatio": None},
                          {**FULL, "Ticker": "B", "pegRatio": None, "currentRatio": None}])
    api = pd.DataFrame([{"Ticker": "A", **api_row}, {"Ticker": "B", **api_row}])
    res = run_scan([("A.NS", "A", "IT"), ("B.NS", "B", "IT")], cache, get_default_config(), fallback=api)
    a = res.scored.set_index("Ticker").loc["A"]
    assert a["PEG"] == 1.0 and a["Filled From IndianAPI"] == "PEG" and a["Data Coverage %"] == 100.0
    b = res.disqualified.set_index("Ticker").loc["B"]  # filled current ratio 0.5 < 0.8 triggers the hard filter
    assert "Current ratio 0.50" in b["Reason"] and "filled from IndianAPI: PEG, Current ratio" in b["Reason"]


def test_missing_note_mentions_both_sources_once_indianapi_was_checked():
    cache = pd.DataFrame([{**FULL, "Ticker": "A", "pegRatio": None}])
    api = pd.DataFrame([{"Ticker": "A", "status": "ok", "as_of": TODAY.isoformat()}])
    res = run_scan([("A.NS", "A", "IT")], cache, get_default_config(), fallback=api)
    assert "PEG: not provided by Yahoo Finance or IndianAPI" in res.scored.iloc[0]["Unavailable Metrics"]
    plain = run_scan([("A.NS", "A", "IT")], cache, get_default_config())
    assert "PEG: not provided by Yahoo Finance" in plain.scored.iloc[0]["Unavailable Metrics"]
    assert "IndianAPI" not in plain.scored.iloc[0]["Unavailable Metrics"]


def test_usage_counter_resets_each_month(tmp_path, monkeypatch):
    u = UsageCounter(tmp_path / "u.json")
    u.add(3)
    assert u.used == 3
    (tmp_path / "u.json").write_text('{"month": "2000-01", "requests": 99}')
    assert u.used == 0


def test_api_key_from_env(monkeypatch):
    monkeypatch.setenv("INDIANAPI_KEY", "  ")
    assert indianapi.api_key_from_env() is None
    monkeypatch.setenv("INDIANAPI_KEY", "abc")
    assert indianapi.api_key_from_env() == "abc"


def test_not_found_and_missing_metrics_are_confirmed_gaps():
    with pytest.raises(ApiError, match="Stock not found") as err:
        parse_stock({"error": "Stock not found"}, "XYZ")
    assert err.value.kind == "not_found"
    no_metrics = {**payload(symbol="MAPMYINDIA"), "keyMetrics": None}
    with pytest.raises(ApiError, match="no key metrics") as err:
        parse_stock(no_metrics, "MAPMYINDIA")
    assert err.value.kind == "not_found"

    cache = pd.DataFrame([{**FULL, "Ticker": "A", "pegRatio": None}])
    api = pd.DataFrame([{"Ticker": "A", "status": "not_found", "fetched_at": now_ist().isoformat(),
                         "error": "IndianAPI has no key metrics for this stock"}])
    res = run_scan([("A.NS", "A", "IT")], cache, get_default_config(), fallback=api)
    assert "PEG: not provided by Yahoo Finance or IndianAPI" in res.scored.iloc[0]["Unavailable Metrics"]
    assert res.scored.iloc[0]["Filled From IndianAPI"] == ""
