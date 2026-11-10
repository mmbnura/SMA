"""Fill gaps in Yahoo Finance data from IndianAPI.in (Indian Stock Market API).

Only fields Yahoo did not provide are filled; Yahoo values are never replaced.
Every filled value keeps its source and the date IndianAPI reports for it.

API: https://stock.indianapi.in  (header X-Api-Key). One /stock call per stock
returns about 120 "keyMetrics"; the ones used here are mapped below with their
unit conversions so they match Yahoo's conventions.
"""

from __future__ import annotations

import json
import math
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

import pandas as pd
import requests

from core.timeutil import IST, now_ist, parse_timestamp

BASE_URL = "https://stock.indianapi.in"
SOURCE = "IndianAPI"
DEFAULT_MONTHLY_LIMIT = 5000
DEFAULT_MAX_AGE_DAYS = 30
DEFAULT_GAP_SECONDS = 1.5


@dataclass(frozen=True)
class FieldMap:
    yahoo_field: str  # field name in the base-data cache (Yahoo's naming and units)
    label: str  # metric label shown in the app
    group: str  # keyMetrics group
    keys: tuple[str, ...]  # keyMetrics keys, in order of preference
    scale: float  # multiply IndianAPI's value by this to get Yahoo's unit


# Free cash flow is deliberately not mapped: IndianAPI's figure follows a different
# definition (for TCS it was about one sixth of the cash-flow statement's FCF).
FIELD_MAP: list[FieldMap] = [
    FieldMap("trailingPE", "P/E", "valuation", ("pPerEIncludingExtraordinaryItemsTTM",), 1),
    FieldMap("pegRatio", "PEG", "valuation", ("pegRatio",), 1),
    FieldMap("priceToBook", "P/B", "valuation", ("priceToBookMostRecentQuarter", "priceToBookMostRecentFiscalYear"), 1),
    # IndianAPI reports percentages; Yahoo uses decimals.
    FieldMap("returnOnEquity", "ROE", "mgmtEffectiveness", ("returnOnAverageEquityTrailing12Month",), 0.01),
    FieldMap("returnOnAssets", "ROA", "mgmtEffectiveness", ("returnOnAverageAssetsTrailing12Month",), 0.01),
    FieldMap("operatingMargins", "Op Margin", "margins", ("operatingMarginTrailing12Month",), 0.01),
    FieldMap("revenueGrowth", "Revenue Growth", "growth", ("revenueChangePercentMostRecentQuarter1YearAgo",), 0.01),
    FieldMap("earningsQuarterlyGrowth", "Earnings Growth", "growth", ("ePSChangePercentMostRecentQuarter1YearAgo",), 0.01),
    # IndianAPI gives D/E as a ratio; Yahoo's debtToEquity is in percent.
    FieldMap("debtToEquity", "D/E", "financialstrength",
             ("totalDebtPerTotalEquityMostRecentQuarter", "totalDebtPerTotalEquityMostRecentFiscalYear"), 100),
    FieldMap("currentRatio", "Current ratio", "financialstrength",
             ("currentRatioMostRecentQuarter", "currentRatioMostRecentFiscalYear"), 1),
    # IndianAPI gives market cap in ₹ crore; Yahoo in rupees.
    FieldMap("marketCap", "Market cap", "priceandVolume", ("marketCap",), 1e7),
]
FILLABLE_FIELDS = [m.yahoo_field for m in FIELD_MAP]
LABELS = {m.yahoo_field: m.label for m in FIELD_MAP}
CACHE_COLUMNS = ["Ticker", "fetched_at", "as_of", "matched_name", "status", "error", *FILLABLE_FIELDS]


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(n) or math.isinf(n) else n


def _norm(key: str) -> str:
    # Some IndianAPI keys carry stray characters, e.g. "ePSChangePercentMostRecentQuarter1YearAgo)".
    return re.sub(r"[^a-z0-9]", "", key.lower())


# ── parsing ───────────────────────────────────────────────────────────────────


class ApiError(Exception):
    """kind: auth | quota | not_found | mismatch | stale | network | bad_response"""

    def __init__(self, message: str, kind: str):
        super().__init__(message)
        self.kind = kind


def parse_stock(payload: dict[str, Any], symbol: str, max_age_days: float = DEFAULT_MAX_AGE_DAYS) -> dict[str, Any]:
    """Extract the mapped fields from a /stock response, after checking it is the right, recent company."""
    if payload.get("error") and not payload.get("companyProfile"):
        # Unknown names come back as HTTP 200 with {"error": "Stock not found"}.
        raise ApiError(f"IndianAPI: {payload['error']}", "not_found")
    profile = payload.get("companyProfile") or {}
    nse = str(profile.get("exchangeCodeNse") or "").strip().upper()
    if nse != symbol.upper():
        found = f"{payload.get('companyName') or 'unknown company'} ({nse or 'no NSE symbol'})"
        raise ApiError(f"IndianAPI matched a different company: {found}", "mismatch")

    metrics = payload.get("keyMetrics")
    if not isinstance(metrics, dict):
        raise ApiError("IndianAPI has no key metrics for this stock", "not_found")
    by_group: dict[str, dict[str, Any]] = {}
    for group, items in metrics.items():
        if isinstance(items, list):
            by_group[group] = {_norm(str(i.get("key", ""))): i.get("value") for i in items if isinstance(i, dict)}

    pdate = by_group.get("priceandVolume", {}).get(_norm("PDATE"))
    as_of = parse_timestamp(pdate) if isinstance(pdate, str) else None
    if as_of is None:
        raise ApiError("IndianAPI response does not say when its metrics were calculated", "stale")
    if now_ist() - as_of > timedelta(days=max_age_days):
        raise ApiError(f"IndianAPI metrics are dated {as_of:%d %b %Y}, older than {max_age_days:g} days", "stale")

    values: dict[str, float] = {}
    for m in FIELD_MAP:
        group = by_group.get(m.group, {})
        for key in m.keys:
            n = _number(group.get(_norm(key)))
            if n is not None:
                values[m.yahoo_field] = n * m.scale
                break
    return {"as_of": as_of.date().isoformat(), "matched_name": payload.get("companyName"), "values": values}


# ── HTTP client with pacing, usage counting and clear errors ──────────────────


class UsageCounter:
    """Requests this app has sent to IndianAPI in the current calendar month (IST).

    IndianAPI's own dashboard is the authoritative count; this only tracks this app.
    """

    def __init__(self, path: Path):
        self.path = Path(path)

    def _load(self) -> dict[str, Any]:
        month = now_ist().strftime("%Y-%m")
        try:
            data = json.loads(self.path.read_text())
            if data.get("month") == month:
                return data
        except (OSError, ValueError):
            pass
        return {"month": month, "requests": 0}

    @property
    def used(self) -> int:
        return int(self._load()["requests"])

    def add(self, n: int = 1) -> None:
        data = self._load()
        data["requests"] = int(data["requests"]) + n
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data))


class IndianApiClient:
    def __init__(self, api_key: str, usage: UsageCounter, monthly_limit: int = DEFAULT_MONTHLY_LIMIT,
                 gap_seconds: float = DEFAULT_GAP_SECONDS, session: requests.Session | None = None):
        self.api_key = api_key
        self.usage = usage
        self.monthly_limit = monthly_limit
        self.gap = gap_seconds
        self.session = session or requests.Session()
        self._next = 0.0

    def get_stock(self, name: str) -> dict[str, Any]:
        if self.usage.used >= self.monthly_limit:
            raise ApiError(f"Monthly IndianAPI limit reached ({self.monthly_limit} requests counted by this app)", "quota")
        wait = self._next - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        try:
            resp = self.session.get(f"{BASE_URL}/stock", params={"name": name},
                                    headers={"X-Api-Key": self.api_key}, timeout=30)
        except requests.RequestException as err:
            raise ApiError(f"Cannot reach IndianAPI ({type(err).__name__})", "network") from err
        finally:
            self._next = time.monotonic() + self.gap
            self.usage.add()
        if resp.status_code in (401, 403):
            raise ApiError(f"IndianAPI rejected the API key (HTTP {resp.status_code})", "auth")
        if resp.status_code == 429:
            raise ApiError("IndianAPI request limit reached (HTTP 429)", "quota")
        if resp.status_code in (404, 422):
            raise ApiError(f"IndianAPI has no data for '{name}' (HTTP {resp.status_code})", "not_found")
        if resp.status_code >= 500:
            raise ApiError(f"IndianAPI server error (HTTP {resp.status_code})", "network")
        try:
            payload = resp.json()
        except ValueError as err:
            raise ApiError("IndianAPI returned a response that is not JSON", "bad_response") from err
        if not isinstance(payload, dict):
            raise ApiError("IndianAPI returned an unexpected response", "bad_response")
        return payload


def fetch_stock_metrics(client: IndianApiClient, symbol: str, company_name: str,
                        max_age_days: float = DEFAULT_MAX_AGE_DAYS) -> dict[str, Any]:
    """Look the stock up by NSE symbol, then by company name if that finds another company."""
    try:
        return parse_stock(client.get_stock(symbol), symbol, max_age_days)
    except ApiError as err:
        if err.kind not in ("mismatch", "not_found") or not company_name or company_name == symbol:
            raise
    return parse_stock(client.get_stock(company_name), symbol, max_age_days)


# ── cache and the gap-filling run ─────────────────────────────────────────────


def load_cache(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        return pd.DataFrame(columns=CACHE_COLUMNS)
    df = pd.read_csv(path, dtype={"Ticker": str, "status": str, "error": str, "matched_name": str})
    for col in CACHE_COLUMNS:
        if col not in df.columns:
            df[col] = None
    return df[CACHE_COLUMNS].drop_duplicates("Ticker", keep="last").reset_index(drop=True)


def missing_fields(row: dict[str, Any]) -> list[str]:
    return [f for f in FILLABLE_FIELDS if _number(row.get(f)) is None]


def symbols_to_fetch(base_cache: pd.DataFrame, api_cache: pd.DataFrame, symbols: list[str],
                     max_age_days: float = DEFAULT_MAX_AGE_DAYS) -> list[str]:
    """In-scope stocks with Yahoo data that still has gaps and no recent IndianAPI attempt.

    Failed lookups that will not change soon (wrong company, not found, stale) are
    not retried until they are older than max_age_days; network errors are retried.
    """
    base = base_cache.set_index("Ticker").to_dict(orient="index") if not base_cache.empty else {}
    tried = api_cache.set_index("Ticker").to_dict(orient="index") if not api_cache.empty else {}
    cutoff = now_ist() - timedelta(days=max_age_days)
    out = []
    for sym in symbols:
        row = base.get(sym)
        if row is None or not missing_fields(row):
            continue
        prev = tried.get(sym)
        if prev:
            when = parse_timestamp(prev.get("fetched_at")) if isinstance(prev.get("fetched_at"), str) else None
            if when and when >= cutoff and prev.get("status") in ("ok", "mismatch", "not_found", "stale"):
                continue
        out.append(sym)
    return out


@dataclass
class FillOutcome:
    requested: int = 0
    filled_stocks: int = 0
    failures: list[dict[str, str]] = field(default_factory=list)
    stopped: str | None = None


def fill_gaps(
    client: IndianApiClient,
    stocks: list[tuple[str, str]],
    cache_path: str | Path,
    max_requests: int,
    max_age_days: float = DEFAULT_MAX_AGE_DAYS,
    progress: Callable[[int, int, str], None] | None = None,
) -> tuple[pd.DataFrame, FillOutcome]:
    """Fetch IndianAPI metrics for (symbol, company name) pairs and upsert them into the cache."""
    cache = load_cache(cache_path)
    outcome = FillOutcome()
    rows: list[dict[str, Any]] = []
    total = len(stocks)
    start_usage = client.usage.used
    for i, (symbol, name) in enumerate(stocks, start=1):
        if client.usage.used - start_usage >= max_requests:
            outcome.stopped = f"Stopped after {max_requests} IndianAPI requests (the per-scan limit)."
            break
        outcome.requested += 1
        row: dict[str, Any] = {"Ticker": symbol, "fetched_at": now_ist().isoformat(timespec="seconds")}
        try:
            got = fetch_stock_metrics(client, symbol, name, max_age_days)
        except ApiError as err:
            row.update(status=err.kind, error=str(err))
            outcome.failures.append({"Ticker": symbol, "Name": name, "Reason": str(err)})
            rows.append(row)
            if err.kind in ("auth", "quota"):
                outcome.stopped = str(err)
                break
        else:
            row.update(status="ok", error=None, as_of=got["as_of"], matched_name=got["matched_name"], **got["values"])
            outcome.filled_stocks += 1
            rows.append(row)
        if progress:
            progress(i, total, symbol)

    if rows:
        new = pd.DataFrame(rows).reindex(columns=CACHE_COLUMNS)
        cache = pd.concat([cache[~cache["Ticker"].isin(new["Ticker"])], new], ignore_index=True)
        path = Path(cache_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        cache.to_csv(path, index=False)
    return cache, outcome


def merge_fallback(raw: dict[str, Any], api_row: dict[str, Any] | None,
                   max_age_days: float = DEFAULT_MAX_AGE_DAYS) -> dict[str, Any]:
    """Return raw Yahoo data with gaps filled from a cached IndianAPI row.

    Adds `_filled` (labels of filled fields), `_filled_as_of` and `_fallback_checked`.
    Rows that are not usable (failed lookups, older than max_age_days) fill nothing.
    """
    merged = dict(raw)
    merged["_filled"] = []
    merged["_fallback_checked"] = False
    if not api_row:
        return merged
    if api_row.get("status") == "not_found":
        # IndianAPI was asked recently and has nothing for this stock: the gaps are confirmed, not filled.
        fetched = parse_timestamp(api_row.get("fetched_at")) if isinstance(api_row.get("fetched_at"), str) else None
        merged["_fallback_checked"] = bool(fetched and now_ist() - fetched <= timedelta(days=max_age_days))
        return merged
    if api_row.get("status") != "ok":
        return merged
    as_of = parse_timestamp(api_row.get("as_of")) if isinstance(api_row.get("as_of"), str) else None
    if as_of is None or now_ist() - as_of > timedelta(days=max_age_days):
        return merged
    merged["_fallback_checked"] = True
    merged["_filled_as_of"] = as_of.date().isoformat()
    for f in FILLABLE_FIELDS:
        if _number(raw.get(f)) is None:
            value = _number(api_row.get(f))
            if value is not None:
                merged[f] = value
                merged["_filled"].append(LABELS[f])
    if LABELS["marketCap"] in merged["_filled"] and not isinstance(raw.get("currency"), str):
        merged["currency"] = "INR"  # the filled market cap is in rupees (converted from ₹ crore)
    return merged


def api_key_from_env() -> str | None:
    key = os.environ.get("INDIANAPI_KEY", "").strip()
    return key or None


def month_label() -> str:
    return datetime.now(IST).strftime("%B %Y")
