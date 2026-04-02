# tickers.py — Fetches the LIVE official Nifty 500 constituent list from NSE India
# Source: https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv
# Falls back to a cached copy if NSE is unreachable.

import io
import os
import time

import pandas as pd
import requests

NSE_CSV_URL = (
    "https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv"
)
CACHE_FILE = os.path.join(os.path.dirname(__file__), "nifty500_cache.csv")
CACHE_MAX_AGE_SECONDS = 24 * 3600   # refresh once a day

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.niftyindices.com/",
}

# Sectors where high D/E is structurally normal — skip D/E scoring
FINANCIAL_SECTORS = {
    "Financial Services",
    "Bank",
    "Insurance",
    "Diversified Financials",
    "Consumer Finance",
}


def _cache_is_fresh() -> bool:
    if not os.path.exists(CACHE_FILE):
        return False
    age = time.time() - os.path.getmtime(CACHE_FILE)
    return age < CACHE_MAX_AGE_SECONDS


def _load_from_nse() -> pd.DataFrame:
    """Download Nifty 500 CSV from niftyindices.com."""
    resp = requests.get(NSE_CSV_URL, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    raw = resp.content.decode("utf-8-sig")   # handle BOM
    df = pd.read_csv(io.StringIO(raw))
    return df


def _save_cache(df: pd.DataFrame):
    try:
        df.to_csv(CACHE_FILE, index=False)
    except Exception:
        pass


def _load_cache() -> pd.DataFrame:
    return pd.read_csv(CACHE_FILE)


def _build_ticker_list(df: pd.DataFrame) -> list:
    """
    Convert NSE DataFrame into (yfinance_ticker, name, sector) tuples.
    NSE CSV columns: Company Name, Industry, Symbol, Series, ISIN Code
    """
    result = []
    for _, row in df.iterrows():
        symbol = str(row.get("Symbol", "")).strip()
        name   = str(row.get("Company Name", "")).strip()
        sector = str(row.get("Industry", "Unknown")).strip()
        if not symbol or symbol == "nan":
            continue
        result.append((symbol + ".NS", name, sector))
    return result


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────

def load_nifty500(force_refresh: bool = False) -> list:
    """
    Returns list of (yfinance_ticker, display_name, sector) for all
    Nifty 500 constituents. Uses a 24-hour local cache.
    """
    df = None

    if not force_refresh and _cache_is_fresh():
        try:
            df = _load_cache()
        except Exception:
            df = None

    if df is None:
        try:
            df = _load_from_nse()
            _save_cache(df)
        except Exception:
            if os.path.exists(CACHE_FILE):
                df = _load_cache()
            else:
                raise RuntimeError(
                    "Could not fetch Nifty 500 list from NSE and no local "
                    "cache exists. Check your internet connection."
                )

    return _build_ticker_list(df)


def get_all_sectors(stocks: list) -> list:
    return sorted(set(s for _, _, s in stocks))


# ── Eager load on import ──────────────────────────────────────────────────────
try:
    NIFTY500_STOCKS = load_nifty500()
    _LOAD_ERROR = None
except Exception as e:
    NIFTY500_STOCKS = []
    _LOAD_ERROR = str(e)

ALL_SECTORS = get_all_sectors(NIFTY500_STOCKS)
