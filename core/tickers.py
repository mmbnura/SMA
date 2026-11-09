# tickers.py — Official Nifty 500 constituent list from NSE Indices.
# Source: https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv
# Falls back to the last saved copy if NSE is unreachable, and says so.

from __future__ import annotations

import io
import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

from core.timeutil import IST

NSE_CSV_URL = "https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv"
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
CACHE_FILE = DATA_DIR / "nifty500_cache.csv"
CACHE_MAX_AGE_SECONDS = 24 * 3600

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.niftyindices.com/",
}

REQUIRED_COLUMNS = {"Company Name", "Industry", "Symbol"}

# NSE's "Industry" column uses macro-sector names; banks, NBFCs and insurers
# all appear as "Financial Services". The other names are kept in case NSE
# switches to a finer classification.
FINANCIAL_SECTORS = {
    "Financial Services",
    "Bank",
    "Banks",
    "Insurance",
    "Diversified Financials",
    "Consumer Finance",
}


@dataclass
class UniverseLoad:
    stocks: list[tuple[str, str, str]]
    source: str  # "nse" or "cache"
    as_of: datetime | None
    warning: str | None = None


def _cache_mtime() -> datetime | None:
    if not CACHE_FILE.exists():
        return None
    return datetime.fromtimestamp(os.path.getmtime(CACHE_FILE), tz=IST)


def _cache_is_fresh() -> bool:
    if not CACHE_FILE.exists():
        return False
    return time.time() - os.path.getmtime(CACHE_FILE) < CACHE_MAX_AGE_SECONDS


def _validate(df: pd.DataFrame) -> pd.DataFrame:
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"NSE list is missing columns: {', '.join(sorted(missing))}")
    if df.empty:
        raise ValueError("NSE list is empty")
    return df


def _load_from_nse() -> pd.DataFrame:
    resp = requests.get(NSE_CSV_URL, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    raw = resp.content.decode("utf-8-sig")
    return _validate(pd.read_csv(io.StringIO(raw)))


def _load_cache() -> pd.DataFrame:
    return _validate(pd.read_csv(CACHE_FILE))


def _build_ticker_list(df: pd.DataFrame) -> list[tuple[str, str, str]]:
    result = []
    seen = set()
    for _, row in df.iterrows():
        symbol = str(row.get("Symbol", "")).strip()
        if not symbol or symbol.lower() == "nan" or symbol in seen:
            continue
        seen.add(symbol)
        name = str(row.get("Company Name", "")).strip() or symbol
        sector = str(row.get("Industry", "")).strip()
        if not sector or sector.lower() == "nan":
            sector = "Sector not available"
        result.append((symbol + ".NS", name, sector))
    return result


def load_nifty500(force_refresh: bool = False) -> UniverseLoad:
    """Return the Nifty 500 universe as (yfinance_ticker, name, sector) tuples."""
    if not force_refresh and _cache_is_fresh():
        try:
            return UniverseLoad(_build_ticker_list(_load_cache()), "cache", _cache_mtime())
        except Exception:
            pass

    try:
        df = _load_from_nse()
    except Exception as exc:
        err = f"network error: {type(exc).__name__}" if isinstance(exc, requests.RequestException) else str(exc)
        if CACHE_FILE.exists():
            as_of = _cache_mtime()
            return UniverseLoad(
                _build_ticker_list(_load_cache()),
                "cache",
                as_of,
                warning=(
                    f"Could not reach NSE ({err}). Using the saved constituent list from "
                    f"{as_of:%d %b %Y %H:%M} IST; index changes since then are not reflected."
                ),
            )
        raise RuntimeError(
            f"Could not fetch the Nifty 500 list from NSE ({err}) and no saved copy exists."
        ) from exc

    try:
        df.to_csv(CACHE_FILE, index=False)
    except OSError:
        pass
    return UniverseLoad(_build_ticker_list(df), "nse", datetime.now(IST))


def get_all_sectors(stocks: list[tuple[str, str, str]]) -> list[str]:
    return sorted({s for _, _, s in stocks})
