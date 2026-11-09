import json
import sqlite3
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import core.scan_history as scan_history
import core.screener as screener
import core.tickers as tickers
from core.screener import run_scan
from core.screening_logic import get_default_config
from tests.test_screener import FULL


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "scan_history.db"
    monkeypatch.setattr(scan_history, "DB_FILE", str(path))
    monkeypatch.setattr(tickers, "load_nifty500", lambda force_refresh=False: tickers.UniverseLoad([], "cache", None))
    return path


def open_page(page: str, **state) -> AppTest:
    at = AppTest.from_file("../app.py", default_timeout=30)
    at.run()
    for key, value in state.items():
        at.session_state[key] = value
    at.switch_page(page)
    at.run()
    return at


def _fake_download(prices: dict[str, list[float] | None], start: date):
    def download(tickers, start=None, end=None, **kwargs):
        days = pd.bdate_range(start=start_day, periods=n)
        cols = {}
        for t in tickers:
            series = prices.get(t)
            cols[("Close", t)] = series if series is not None else [np.nan] * n
        df = pd.DataFrame(cols, index=days)
        df.columns = pd.MultiIndex.from_tuples(df.columns)
        return df

    start_day = start
    n = len(next(v for v in prices.values() if v is not None))
    return download


def test_accuracy_page_compares_tiers_with_nifty(db, monkeypatch):
    scan_history.init_db()
    fetched = "2026-10-01T16:00:00+05:30"
    cache = pd.DataFrame([
        {**FULL, "Ticker": "AAA", "fetched_at": fetched},
        {**FULL, "Ticker": "BBB", "fetched_at": fetched},
        {**FULL, "Ticker": "CCC", "fetched_at": fetched, "returnOnEquity": -0.1},
    ])
    stocks = [("AAA.NS", "Aaa", "IT"), ("BBB.NS", "Bbb", "IT"), ("CCC.NS", "Ccc", "IT")]
    res = run_scan(stocks, cache, get_default_config())
    scan_history.save_scan_run("S1", "SECTOR", "2026-10-01T16:30:00+05:30", ["IT"], 3,
                               res.scored, res.disqualified, res.unavailable, get_default_config())

    # Business days from 2026-09-28; the reference close is 2026-10-01 (index 3).
    n = 20
    prices = {
        "^NSEI": [100.0] * 3 + [100.0] + [110.0] * (n - 4),
        "AAA.NS": [50.0] * 3 + [50.0] + [60.0] * (n - 4),
        "BBB.NS": None,
        "CCC.NS": [10.0] * 3 + [10.0] + [9.0] * (n - 4),
    }
    monkeypatch.setattr(screener.yf, "download", _fake_download(prices, date(2026, 9, 28)))

    at = open_page("pages/Accuracy_Verification.py", accuracy_scan_id="S1")
    assert not at.exception, at.exception

    summary = at.dataframe[0].value
    summary = summary.data if hasattr(summary, "data") else summary
    row = summary.set_index("Tier")
    tier = res.scored.iloc[0]["Recommendation"]
    assert row.loc[tier, "Stocks"] == 2
    assert row.loc[tier, "With price data"] == 1
    assert row.loc[tier, "Avg Outperformance %"] == pytest.approx(10.0)  # +20% vs +10%
    assert row.loc["Disqualified", "Avg Outperformance %"] == pytest.approx(-20.0)


def test_history_page_handles_legacy_scans(db):
    with sqlite3.connect(db) as conn:
        conn.execute(
            """CREATE TABLE scan_runs (scan_id TEXT PRIMARY KEY, scan_type TEXT NOT NULL,
               created_at TEXT NOT NULL, selected_sectors TEXT NOT NULL, total_in_scope INTEGER NOT NULL,
               total_scored INTEGER NOT NULL, results_json TEXT NOT NULL)"""
        )
        legacy_rows = [{
            "Ticker": "TCS", "Name": "Tata Consultancy", "Sector": "Information Technology",
            "Price (Rs)": 3500.0, "Cap Bucket": "Large (>₹2T)", "Score": 70, "Recommendation": "Buy",
            "P/E": "25.1", "P/B": "12.30", "ROE": "45.0%", "D/E": "N/A (Fin.)", "EPS Growth": "N/A",
            "Rev Growth": "5.5%", "Div Yield": None, "52W Position": 40.0,
        }]
        conn.execute(
            "INSERT INTO scan_runs VALUES (?,?,?,?,?,?,?)",
            ("FULL_OLD", "FULL", "2026-05-25T07:31:00", json.dumps(["Information Technology"]), 1, 1,
             json.dumps(legacy_rows)),
        )

    at = open_page("pages/History.py")
    assert not at.exception, at.exception
    assert any("earlier version" in w.value for w in at.warning)
