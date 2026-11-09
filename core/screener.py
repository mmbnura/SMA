# screener.py — Fetch fundamentals from Yahoo Finance, cache them, and score each stock.
#
# Principle: nothing is assumed. A metric whose input is missing is marked
# "not available" and excluded from the score (it is never scored as 0 or
# given default points). Each stock reports how much of the scoring weight had
# real data, and stocks below the configured minimum get "Insufficient Data"
# instead of a recommendation.

from __future__ import annotations

import math
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

import pandas as pd
import requests
import yfinance as yf

from core.screening_logic import (
    DEFAULT_MIN_DATA_COVERAGE,
    DEFAULT_RECOMMENDATION_THRESHOLDS,
    METRIC_DEFINITIONS,
    metric_lookup,
)
from core.tickers import FINANCIAL_SECTORS
from core.timeutil import IST, NSE_CLOSE, now_ist, parse_timestamp

NOT_AVAILABLE = "Not available"
INSUFFICIENT_DATA = "Insufficient Data"
RECOMMENDATION_ORDER = ["Strong Buy", "Buy", "Hold", "Avoid", INSUFFICIENT_DATA]
REC_COLOURS = {
    "Strong Buy": "#00a843",
    "Buy": "#c9a800",
    "Hold": "#ff6d00",
    "Avoid": "#d50000",
    INSUFFICIENT_DATA: "#8a8f98",
}
REC_EMOJI = {
    "Strong Buy": "🟢",
    "Buy": "🟡",
    "Hold": "🟠",
    "Avoid": "🔴",
    INSUFFICIENT_DATA: "⚪",
}

NIFTY50 = "^NSEI"

# Raw Yahoo Finance `info` fields stored in the base-data cache.
YF_FIELDS = [
    "trailingPE",
    "pegRatio",
    "trailingPegRatio",
    "priceToBook",
    "returnOnEquity",
    "returnOnAssets",
    "debtToEquity",
    "marketCap",
    "freeCashflow",
    "operatingMargins",
    "earningsQuarterlyGrowth",
    "revenueGrowth",
    "fiftyTwoWeekHigh",
    "fiftyTwoWeekLow",
    "currentRatio",
    "currency",
    "financialCurrency",
]
BASE_COLUMNS = ["Ticker", "Name", "Sector", "lastPrice", "fetched_at", *YF_FIELDS]
TEXT_FIELDS = {"Ticker", "Name", "Sector", "fetched_at", "currency", "financialCurrency"}


def to_number(value: Any) -> float | None:
    """Convert to a finite float, or None when the value is missing or not numeric."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    text = str(value).strip()
    return text or None


def _interp(x: float, points: list[tuple[float, float]]) -> float:
    """Piecewise-linear interpolation, clamped to the end points."""
    if x <= points[0][0]:
        return points[0][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x <= x1:
            return y0 + (x - x0) * (y1 - y0) / (x1 - x0)
    return points[-1][1]


# ─────────────────────────────────────────────────────────────────────────────
# METRICS — each returns (value, points, status, note)
#   status: "ok" | "missing" | "not_applicable"
# ─────────────────────────────────────────────────────────────────────────────

CURVES = {
    "pe": [(10, 12), (20, 9), (40, 4), (60, 0)],
    "peg": [(0.75, 13), (1.5, 7), (3.0, 0)],
    "pb": [(1.0, 10), (3.0, 6), (8.0, 0)],
    "roe": [(0, 0), (8, 5), (20, 11), (40, 13)],
    "roa": [(0, 0), (5, 3), (15, 6), (25, 7)],
    "de": [(0.3, 10), (1.0, 6), (2.0, 3), (3.0, 0)],
    "fcf_yield": [(0, 0), (2, 3), (8, 9), (15, 10)],
    "op_margin": [(0, 0), (5, 2), (15, 5), (25, 7), (40, 8)],
    "eps_growth": [(-10, 0), (0, 2), (10, 5), (25, 9), (60, 10)],
    "rev_growth": [(-5, 0), (0, 1), (10, 4), (20, 6), (50, 7)],
}


@dataclass
class MetricResult:
    value: float | None
    points: float | None
    status: str
    note: str = ""


def _missing(note: str = "not provided by Yahoo Finance") -> MetricResult:
    return MetricResult(None, None, "missing", note)


def _valuation(metric_id: str, raw_value: Any, negative_note: str) -> MetricResult:
    v = to_number(raw_value)
    if v is None:
        return _missing()
    if v <= 0:
        return MetricResult(v, 0.0, "ok", negative_note)
    return MetricResult(v, _interp(v, CURVES[metric_id]), "ok")


def _percent(metric_id: str, raw_value: Any) -> MetricResult:
    v = to_number(raw_value)
    if v is None:
        return _missing()
    v *= 100  # Yahoo reports these as decimals
    return MetricResult(v, _interp(v, CURVES[metric_id]), "ok")


def compute_metrics(raw: dict[str, Any], sector: str) -> dict[str, MetricResult]:
    peg_raw = raw.get("pegRatio")
    if to_number(peg_raw) is None:
        peg_raw = raw.get("trailingPegRatio")

    results = {
        "pe": _valuation("pe", raw.get("trailingPE"), "zero/negative earnings"),
        "peg": _valuation("peg", peg_raw, "negative earnings growth"),
        "pb": _valuation("pb", raw.get("priceToBook"), "negative book value"),
        "roe": _percent("roe", raw.get("returnOnEquity")),
        "roa": _percent("roa", raw.get("returnOnAssets")),
        "op_margin": _percent("op_margin", raw.get("operatingMargins")),
        "eps_growth": _percent("eps_growth", raw.get("earningsQuarterlyGrowth")),
        "rev_growth": _percent("rev_growth", raw.get("revenueGrowth")),
    }

    if sector in FINANCIAL_SECTORS:
        results["de"] = MetricResult(None, None, "not_applicable", "not applicable to financial sector")
    else:
        de_pct = to_number(raw.get("debtToEquity"))
        if de_pct is None:
            results["de"] = _missing()
        else:
            de = de_pct / 100  # Yahoo reports D/E in percent
            if de < 0:
                results["de"] = MetricResult(de, 0.0, "ok", "negative shareholder equity")
            else:
                results["de"] = MetricResult(de, _interp(de, CURVES["de"]), "ok")

    market_cap = to_number(raw.get("marketCap"))
    free_cf = to_number(raw.get("freeCashflow"))
    price_ccy = _text(raw.get("currency"))
    stmt_ccy = _text(raw.get("financialCurrency"))
    if market_cap is None or market_cap <= 0 or free_cf is None:
        results["fcf_yield"] = _missing()
    elif price_ccy is None or stmt_ccy is None:
        results["fcf_yield"] = _missing("reporting currency not available, so the yield cannot be verified")
    elif price_ccy != stmt_ccy:
        results["fcf_yield"] = _missing(f"cash flow reported in {stmt_ccy}, market cap in {price_ccy}")
    else:
        y = free_cf / market_cap * 100
        results["fcf_yield"] = MetricResult(y, _interp(y, CURVES["fcf_yield"]), "ok")

    return results


# ─────────────────────────────────────────────────────────────────────────────
# HARD FILTERS — only evaluated on data that exists
# ─────────────────────────────────────────────────────────────────────────────

def apply_hard_filters(raw: dict[str, Any], sector: str) -> list[str]:
    """Return the list of disqualification reasons (empty if the stock passes)."""
    reasons = []
    financial = sector in FINANCIAL_SECTORS

    current_ratio = to_number(raw.get("currentRatio"))
    if not financial and current_ratio is not None and current_ratio < 0.8:
        reasons.append(f"Current ratio {current_ratio:.2f} is below 0.8 (liquidity risk)")

    roe = to_number(raw.get("returnOnEquity"))
    if roe is not None and roe < 0:
        reasons.append(f"Trailing 12-month ROE is negative ({roe * 100:.1f}%)")

    de_pct = to_number(raw.get("debtToEquity"))
    if not financial and de_pct is not None and de_pct / 100 > 3.0:
        reasons.append(f"Debt/Equity {de_pct / 100:.2f}x is above 3.0x (excessive leverage)")

    free_cf = to_number(raw.get("freeCashflow"))
    op_margin = to_number(raw.get("operatingMargins"))
    if free_cf is not None and op_margin is not None and free_cf < 0 and op_margin < 0:
        reasons.append(
            f"Negative free cash flow and negative operating margin ({op_margin * 100:.1f}%) — cash burn"
        )

    return reasons


# ─────────────────────────────────────────────────────────────────────────────
# SCORING
# ─────────────────────────────────────────────────────────────────────────────

def get_recommendation(score: int | None, coverage: float | None, config: dict) -> str:
    thresholds = config.get("recommendation_thresholds") or DEFAULT_RECOMMENDATION_THRESHOLDS
    min_cov = config.get("min_data_coverage", DEFAULT_MIN_DATA_COVERAGE)
    if score is None or coverage is None or coverage < min_cov:
        return INSUFFICIENT_DATA
    if score >= thresholds["strong_buy"]:
        return "Strong Buy"
    if score >= thresholds["buy"]:
        return "Buy"
    if score >= thresholds["hold"]:
        return "Hold"
    return "Avoid"


def _combine(metrics: dict[str, MetricResult], config: dict) -> dict[str, Any]:
    lookup = metric_lookup(config)
    out: dict[str, Any] = {}
    earned = 0.0
    available_weight = 0.0
    applicable_weight = 0.0
    gaps = []

    for metric in METRIC_DEFINITIONS:
        mid = metric["id"]
        cfg = lookup.get(mid, {})
        weight = float(cfg.get("weight", metric["base_max"])) if cfg.get("enabled", True) else 0.0
        result = metrics[mid]

        out[metric["column"]] = result.value
        out[metric["score_col"]] = None
        out[metric["max_col"]] = weight

        if result.status != "ok":
            if weight > 0:
                gaps.append(f"{metric['label']}: {result.note}")
            if result.status == "not_applicable":
                out[metric["max_col"]] = 0.0
            else:
                applicable_weight += weight
            continue

        weighted = result.points / metric["base_max"] * weight
        out[metric["score_col"]] = round(weighted, 2)
        if weight > 0:
            earned += weighted
            available_weight += weight
            applicable_weight += weight

    score = int(round(earned / available_weight * 100)) if available_weight > 0 else None
    coverage = round(available_weight / applicable_weight * 100, 1) if applicable_weight > 0 else None

    out["Score"] = score
    out["Data Coverage %"] = coverage
    out["Unavailable Metrics"] = "; ".join(gaps) if gaps else ""
    out["Recommendation"] = get_recommendation(score, coverage, config)
    return out


def score_stock(raw: dict[str, Any], ticker: str, name: str, sector: str, config: dict) -> dict[str, Any]:
    """Score one stock from raw Yahoo fields. Returns a record with Status SCORED or DISQUALIFIED."""
    fetched_at = parse_timestamp(_text(raw.get("fetched_at")))
    base = {
        "Ticker": ticker,
        "Name": name,
        "Sector": sector,
        "Data As Of": fetched_at.strftime("%Y-%m-%d %H:%M IST") if fetched_at else NOT_AVAILABLE,
    }

    reasons = apply_hard_filters(raw, sector)
    if reasons:
        return {**base, "Status": "DISQUALIFIED", "Reason": "; ".join(reasons)}

    price = to_number(raw.get("lastPrice"))
    hi = to_number(raw.get("fiftyTwoWeekHigh"))
    lo = to_number(raw.get("fiftyTwoWeekLow"))
    market_cap = to_number(raw.get("marketCap"))
    price_ccy = _text(raw.get("currency"))

    w52_pos = None
    if price is not None and hi is not None and lo is not None and hi > lo:
        w52_pos = round((price - lo) / (hi - lo) * 100, 1)

    mcap_cr = None
    if market_cap is not None and market_cap > 0 and price_ccy in (None, "INR"):
        mcap_cr = round(market_cap / 1e7, 0)

    record = {
        **base,
        "Status": "SCORED",
        "Price (₹)": round(price, 2) if price is not None else None,
        "Market Cap (₹ Cr)": mcap_cr,
        "52W High": round(hi, 2) if hi is not None else None,
        "52W Low": round(lo, 2) if lo is not None else None,
        "52W Position %": w52_pos,
    }
    record.update(_combine(compute_metrics(raw, sector), config))
    return record


# ─────────────────────────────────────────────────────────────────────────────
# BASE DATA: fetch from Yahoo and cache locally (upsert per ticker)
# ─────────────────────────────────────────────────────────────────────────────

# yfinance's default hides HTTP errors (e.g. 401 "Invalid Crumb", 404) and returns
# empty data, which makes failures impossible to explain. Make them raise.
if hasattr(yf, "config"):
    yf.config.debug.hide_exceptions = False


class FetchError(Exception):
    """A download failure with a readable message and a kind used for retry decisions.

    kind: throttled | not_found | network | no_data | no_price | skipped | other
    """

    def __init__(self, message: str, kind: str = "other"):
        super().__init__(message)
        self.kind = kind


RETRYABLE = {"throttled", "network", "no_data"}
_TRANSIENT_NAMES = {
    "Timeout", "TimeoutError", "ConnectionError", "ConnectTimeout", "ReadTimeout",
    "ChunkedEncodingError", "RemoteDisconnected", "ProxyError", "SSLError",
}


def _yahoo_detail(err: Exception) -> str:
    """Yahoo's own error description from an HTTP error response, if any."""
    response = getattr(err, "response", None)
    try:
        body = response.json()
    except Exception:
        return ""
    for key in ("finance", "quoteSummary", "quoteResponse"):
        error = (body.get(key) or {}).get("error") if isinstance(body, dict) else None
        if isinstance(error, dict):
            return str(error.get("description") or error.get("code") or "")
    return ""


def classify_error(err: Exception) -> FetchError:
    if isinstance(err, FetchError):
        return err
    name = type(err).__name__
    status = getattr(getattr(err, "response", None), "status_code", None)
    detail = _yahoo_detail(err)
    suffix = f": {detail}" if detail else ""
    if name == "YFRateLimitError" or status == 429:
        return FetchError("Yahoo Finance is rate-limiting requests (HTTP 429 Too Many Requests)", "throttled")
    if status in (401, 403):
        return FetchError(
            f"Yahoo Finance refused the request (HTTP {status}{suffix}); usually a session or throttling issue",
            "throttled",
        )
    if status == 404:
        return FetchError(f"Symbol not found on Yahoo Finance (HTTP 404{suffix})", "not_found")
    if isinstance(status, int) and status >= 500:
        return FetchError(f"Yahoo Finance server error (HTTP {status}{suffix})", "network")
    if name in _TRANSIENT_NAMES or isinstance(err, (requests.RequestException, OSError, TimeoutError)):
        return FetchError(f"Network error while contacting Yahoo Finance ({name})", "network")
    return FetchError(f"Unexpected error from yfinance ({name}: {str(err)[:200]})", "other")


YAHOO_PROBE_URL = "https://query1.finance.yahoo.com/v8/finance/chart/%5ENSEI?range=1d&interval=1d"


def check_yahoo_reachable(timeout: float = 10.0) -> str | None:
    """Return None if Yahoo Finance answers at all, else a readable reason."""
    try:
        requests.get(YAHOO_PROBE_URL, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        return None  # any HTTP response (even 401/429) means the host is reachable
    except requests.RequestException as err:
        return f"Cannot reach Yahoo Finance ({type(err).__name__}). Check the internet connection or proxy."


# Inputs to the scores and hard filters; if Yahoo returns none of them the
# response is treated as a failed download rather than cached as empty data.
FUNDAMENTAL_FIELDS = [
    "trailingPE", "pegRatio", "trailingPegRatio", "priceToBook", "returnOnEquity", "returnOnAssets",
    "debtToEquity", "freeCashflow", "operatingMargins", "earningsQuarterlyGrowth", "revenueGrowth",
    "currentRatio",
]


def _fetch_once(yf_ticker: str) -> dict[str, Any]:
    t = yf.Ticker(yf_ticker)  # a fresh object: yfinance caches a failed fetch on the instance
    try:
        info = t.info or {}
    except Exception as err:
        raise classify_error(err) from err

    if not any(info.get(k) for k in ("symbol", "quoteType", "shortName", "longName")):
        raise FetchError("Yahoo Finance returned an empty response for this symbol", "no_data")
    if all(to_number(info.get(k)) is None for k in FUNDAMENTAL_FIELDS):
        raise FetchError("Yahoo Finance returned a quote but no fundamental data", "no_data")

    price = to_number(info.get("currentPrice")) or to_number(info.get("regularMarketPrice"))
    if price is None:
        try:
            price = to_number(getattr(t.fast_info, "last_price", None))
        except Exception:
            price = None
    if price is None or price <= 0:
        raise FetchError("Yahoo Finance returned company data but no current price (trading may be suspended)",
                         "no_price")

    record = {field_name: info.get(field_name) for field_name in YF_FIELDS}
    record["lastPrice"] = price
    record["fetched_at"] = now_ist().isoformat(timespec="seconds")
    return record


def fetch_fundamentals(yf_ticker: str, attempts: int = 3, base_delay: float = 2.0) -> dict[str, Any]:
    """Fetch raw fundamentals for one ticker, retrying transient failures.

    Raises FetchError with a readable reason and kind.
    """
    for attempt in range(attempts):
        try:
            return _fetch_once(yf_ticker)
        except FetchError as err:
            if err.kind not in RETRYABLE or attempt == attempts - 1:
                raise
            factor = 3 if err.kind == "throttled" else 1
            time.sleep(base_delay * (2 ** attempt) * factor)
    raise AssertionError("unreachable")


THROTTLE_ABORT_MESSAGE = (
    "Not downloaded: Yahoo Finance kept rate-limiting requests, so the download was stopped. "
    "Wait a few minutes and run the scan again."
)


def fetch_and_cache_base_data(
    stocks: list[tuple[str, str, str]],
    cache_path: str | Path,
    progress_callback: Callable[[int, int, str], None] | None = None,
    max_workers: int = 2,
    pause_between: float = 0.5,
    throttle_limit: int = 5,
    cooldown_seconds: float = 60.0,
    max_cooldowns: int = 2,
) -> tuple[pd.DataFrame, list[dict[str, str]], str | None]:
    """Fetch fundamentals for `stocks` and upsert them into the cache.

    When Yahoo throttles (`throttle_limit` throttled stocks in a row) all workers
    pause for `cooldown_seconds`; after `max_cooldowns` pauses the download stops.

    Returns (updated cache, failures, abort_reason). Stocks that fail keep any
    older cached row; the failure list says so.
    """
    cache = load_base_cache(cache_path)
    cached_tickers = set(cache["Ticker"])
    fetched: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    total = len(stocks)

    lock = threading.Lock()
    stop = threading.Event()
    state = {"streak": 0, "cooldowns": 0, "resume_at": 0.0}

    def wait_for_resume() -> None:
        while not stop.is_set():
            remaining = state["resume_at"] - time.time()
            if remaining <= 0:
                return
            time.sleep(min(remaining, 1.0))

    def task(yf_t: str) -> dict[str, Any]:
        while True:
            wait_for_resume()
            if stop.is_set():
                raise FetchError(THROTTLE_ABORT_MESSAGE, "skipped")
            try:
                row = fetch_fundamentals(yf_t)
            except FetchError as err:
                if err.kind != "throttled":
                    raise
                with lock:
                    state["streak"] += 1
                    if state["streak"] >= throttle_limit:
                        state["streak"] = 0
                        if state["cooldowns"] >= max_cooldowns:
                            stop.set()
                        else:
                            state["cooldowns"] += 1
                            state["resume_at"] = time.time() + cooldown_seconds
                    retry = state["resume_at"] > time.time()
                if retry:
                    continue  # try this stock again after the pause
                raise
            with lock:
                state["streak"] = 0
            time.sleep(pause_between)
            return row

    retry_later: list[tuple[str, str, str]] = []
    done_count = 0

    def record(stock: tuple[str, str, str], row: dict | None, exc: Exception | None, final: bool) -> None:
        nonlocal done_count
        yf_t, name, sector = stock
        base = yf_t.replace(".NS", "")
        if row is not None:
            row.update({"Ticker": base, "Name": name, "Sector": sector})
            fetched.append(row)
        else:
            err = classify_error(exc)
            if err.kind == "throttled" and not final:
                retry_later.append(stock)
                return
            reason = str(err) + (" — older cached data kept" if base in cached_tickers else "")
            failures.append({"Ticker": base, "Name": name, "Sector": sector, "Reason": reason})
        done_count += 1

    def report(name: str) -> None:
        if not progress_callback:
            return
        pause = state["resume_at"] - time.time()
        if pause > 0 and not stop.is_set():
            progress_callback(done_count, total, f"Yahoo Finance is rate-limiting; pausing {pause:.0f}s")
        elif name:
            progress_callback(done_count, total, name)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(task, stock[0]): stock for stock in stocks}
        pending = set(futures)
        while pending:
            finished, pending = wait(pending, timeout=1.0, return_when=FIRST_COMPLETED)
            last_name = ""
            for future in finished:
                stock = futures[future]
                try:
                    record(stock, future.result(), None, final=False)
                except Exception as exc:
                    record(stock, None, exc, final=False)
                last_name = stock[1]
            report(last_name)

    # Stocks throttled before a pause began get one more, sequential attempt.
    for stock in retry_later:
        report(f"retrying {stock[1]} after rate limiting")
        try:
            row = task(stock[0])
        except Exception as exc:
            record(stock, None, exc, final=True)
        else:
            record(stock, row, None, final=True)
        report(stock[1])

    if fetched:
        new_rows = pd.DataFrame(fetched)[BASE_COLUMNS]
        refreshed = set(new_rows["Ticker"])
        cache = pd.concat(
            [cache[~cache["Ticker"].isin(refreshed)], new_rows], ignore_index=True
        ) if not cache.empty else new_rows
        path = Path(cache_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        cache.to_csv(path, index=False)

    abort_reason = None
    if stop.is_set():
        skipped = sum(1 for f in failures if f["Reason"].startswith("Not downloaded"))
        abort_reason = (
            f"Yahoo Finance kept rate-limiting requests, so the download stopped early: {len(fetched)} downloaded, "
            f"{skipped} not attempted. Wait a few minutes and run the scan again; already-downloaded data is kept."
        )
    return cache, failures, abort_reason


def load_base_cache(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        return pd.DataFrame(columns=BASE_COLUMNS)
    df = pd.read_csv(path, dtype={"Ticker": str})
    for col in BASE_COLUMNS:
        if col not in df.columns:
            df[col] = None
    return df[BASE_COLUMNS].drop_duplicates("Ticker", keep="last").reset_index(drop=True)


def cache_age_summary(cache: pd.DataFrame, tickers: list[str]) -> dict[str, Any]:
    """Freshness of cached data for the given base tickers (no .NS)."""
    by_ticker = cache.set_index("Ticker")["fetched_at"].to_dict() if not cache.empty else {}
    missing, undated, times = [], [], []
    for tk in tickers:
        if tk not in by_ticker:
            missing.append(tk)
            continue
        ts = parse_timestamp(_text(by_ticker[tk]))
        if ts is None:
            undated.append(tk)
        else:
            times.append((tk, ts))
    return {"missing": missing, "undated": undated, "dated": times}


def tickers_needing_fetch(cache: pd.DataFrame, tickers: list[str], max_age_hours: float) -> list[str]:
    summary = cache_age_summary(cache, tickers)
    cutoff = now_ist() - timedelta(hours=max_age_hours)
    stale = [tk for tk, ts in summary["dated"] if ts < cutoff]
    return summary["missing"] + summary["undated"] + stale


# ─────────────────────────────────────────────────────────────────────────────
# SCAN
# ─────────────────────────────────────────────────────────────────────────────

def sort_scored(df: pd.DataFrame) -> pd.DataFrame:
    """Rated stocks by score (high first), then 'Insufficient Data' stocks."""
    if df.empty:
        return df
    insufficient = (df["Recommendation"] == INSUFFICIENT_DATA).astype(int)
    order = pd.DataFrame({"i": insufficient, "s": df["Score"]}).sort_values(
        ["i", "s"], ascending=[True, False], na_position="last"
    ).index
    return df.loc[order].reset_index(drop=True)


@dataclass
class ScanResult:
    scored: pd.DataFrame
    disqualified: pd.DataFrame
    unavailable: pd.DataFrame
    in_scope: int = 0
    notes: list[str] = field(default_factory=list)


def run_scan(
    stocks: list[tuple[str, str, str]],
    cache: pd.DataFrame,
    config: dict,
    fetch_failures: list[dict[str, str]] | None = None,
) -> ScanResult:
    """Score every in-scope stock that has cached data; account for the rest."""
    failure_reasons = {f["Ticker"]: f["Reason"] for f in (fetch_failures or [])}
    rows = cache.set_index("Ticker").to_dict(orient="index") if not cache.empty else {}

    scored, disqualified, unavailable = [], [], []
    for yf_t, name, sector in stocks:
        base = yf_t.replace(".NS", "")
        raw = rows.get(base)
        if raw is None:
            unavailable.append({
                "Ticker": base,
                "Name": name,
                "Sector": sector,
                "Reason": failure_reasons.get(base, "No fundamental data has been downloaded for this stock"),
            })
            continue
        record = score_stock(raw, base, name, sector, config)
        (disqualified if record["Status"] == "DISQUALIFIED" else scored).append(record)

    scored_df = sort_scored(pd.DataFrame(scored))
    return ScanResult(
        scored=scored_df,
        disqualified=pd.DataFrame(disqualified, columns=["Ticker", "Name", "Sector", "Data As Of", "Status", "Reason"]),
        unavailable=pd.DataFrame(unavailable, columns=["Ticker", "Name", "Sector", "Reason"]),
        in_scope=len(stocks),
    )


# ─────────────────────────────────────────────────────────────────────────────
# PRICE DATA (deep dive chart and accuracy verification)
# ─────────────────────────────────────────────────────────────────────────────

def fetch_price_history(yf_ticker: str, period: str = "1y") -> pd.DataFrame:
    try:
        df = yf.download(yf_ticker, period=period, progress=False, auto_adjust=False)
    except Exception:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


def reference_close_date(fetched_at: datetime) -> date:
    """Latest session whose official close was known when the data was fetched.

    Before 15:30 IST the latest settled close is from an earlier day.
    """
    local = fetched_at.astimezone(IST)
    if local.time() >= NSE_CLOSE:
        return local.date()
    return local.date() - timedelta(days=1)


def fetch_close_prices(yf_tickers: list[str], start: date) -> pd.DataFrame:
    """Daily closes (split-adjusted, not dividend-adjusted) from `start` to today.

    Columns are the requested tickers; tickers Yahoo could not serve are absent
    or entirely NaN.
    """
    end = now_ist().date() + timedelta(days=1)
    data = yf.download(
        yf_tickers,
        start=start.isoformat(),
        end=end.isoformat(),
        progress=False,
        auto_adjust=False,
        threads=True,
    )
    if data is None or data.empty:
        return pd.DataFrame()
    if isinstance(data.columns, pd.MultiIndex):
        closes = data["Close"]
    else:
        closes = data[["Close"]].rename(columns={"Close": yf_tickers[0]})
    if isinstance(closes, pd.Series):
        closes = closes.to_frame(yf_tickers[0])
    closes.index = pd.to_datetime(closes.index).date
    return closes


def period_return(series: pd.Series, ref_date: date) -> dict[str, Any] | None:
    """Return from the last close on/before `ref_date` to the latest close."""
    s = series.dropna()
    if s.empty:
        return None
    before = s[[d <= ref_date for d in s.index]]
    if before.empty:
        return None
    start_date, start_px = before.index[-1], float(before.iloc[-1])
    end_date, end_px = s.index[-1], float(s.iloc[-1])
    if start_px <= 0:
        return None
    return {
        "start_date": start_date,
        "start_price": start_px,
        "end_date": end_date,
        "end_price": end_px,
        "return_pct": (end_px - start_px) / start_px * 100,
    }
