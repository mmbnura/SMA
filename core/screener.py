# screener.py — Fetch fundamentals from yfinance and score each stock with new 10-metric logic

import time
import yfinance as yf
import pandas as pd
import numpy as np
from core.screening_logic import (
    DEFAULT_RECOMMENDATION_THRESHOLDS,
    METRIC_DEFINITIONS,
    load_screening_config,
    metric_lookup,
)
from core.tickers import FINANCIAL_SECTORS

# ─────────────────────────────────────────────────────────────────────────────
# HARD FILTERS (Disqualify before scoring)
# ─────────────────────────────────────────────────────────────────────────────

def apply_hard_filters(full_info: dict, sector: str) -> tuple[bool, str]:
    """
    Check hard filters. Returns (is_disqualified, reason).
    If disqualified=True, do not score the stock.
    """
    current_ratio = full_info.get("currentRatio")
    roe = full_info.get("returnOnEquity")
    de_raw = full_info.get("debtToEquity")
    free_cf = full_info.get("freeCashflow")
    op_margin = full_info.get("operatingMargins")

    # Filter 1: Current Ratio < 0.8
    if current_ratio is not None and not pd.isna(current_ratio):
        if float(current_ratio) < 0.8:
            return True, "Current ratio < 0.8 (liquidity risk)"

    # Filter 2: ROE negative for 2+ consecutive years
    # (Simplified: if latest ROE is negative, assume sustained losses)
    if roe is not None and not pd.isna(roe) and float(roe) < 0:
        return True, "ROE negative (sustained losses)"

    # Filter 3: D/E > 3.0 for non-financial (skip for Banking/NBFC)
    if sector not in FINANCIAL_SECTORS:
        if de_raw is not None and not pd.isna(de_raw):
            de = float(de_raw) / 100  # normalize to ratio
            if de > 3.0:
                return True, "D/E > 3.0 (excessive leverage)"

    # Filter 4: Free cash flow negative AND operating margin < 0
    if free_cf is not None and not pd.isna(free_cf) and float(free_cf) < 0:
        if op_margin is not None and not pd.isna(op_margin):
            if float(op_margin) < 0:
                return True, "Negative FCF + negative op margin (cash burn)"

    return False, ""


# ─────────────────────────────────────────────────────────────────────────────
# SCORING FUNCTIONS  (max points shown for each)
# ─────────────────────────────────────────────────────────────────────────────

def score_pe(pe) -> tuple[float, str]:
    """P/E Ratio — max 12 pts. Inverse capped curve."""
    if pe is None or pd.isna(pe) or pe <= 0:
        return 0.0, "N/A"
    v = float(pe)
    if v <= 10:
        return 12.0, f"{v:.1f}"
    if v <= 20:
        return 12.0 - (v - 10) * (12 - 9) / 10, f"{v:.1f}"  # linear 12→9
    if v <= 40:
        return 9.0 - (v - 20) * (9 - 4) / 20, f"{v:.1f}"    # linear 9→4
    if v <= 60:
        return 4.0 - (v - 40) * 4 / 20, f"{v:.1f}"          # linear 4→0
    return 0.0, f"{v:.1f}"


def score_peg(peg) -> tuple[float, str]:
    """PEG Ratio — max 13 pts. Inverse capped curve."""
    if peg is None or pd.isna(peg) or peg <= 0:
        return 0.0, "N/A"
    v = float(peg)
    if v <= 0.75:
        return 13.0, f"{v:.2f}"
    if v <= 1.5:
        return 13.0 - (v - 0.75) * (13 - 7) / 0.75, f"{v:.2f}"  # linear 13→7
    if v <= 3.0:
        return 7.0 - (v - 1.5) * 7 / 1.5, f"{v:.2f}"             # linear 7→0
    return 0.0, f"{v:.2f}"


def score_pb(pb) -> tuple[float, str]:
    """P/B Ratio — max 10 pts. Inverse capped curve."""
    if pb is None or pd.isna(pb) or pb <= 0:
        return 0.0, "N/A"
    v = float(pb)
    if v <= 1.0:
        return 10.0, f"{v:.2f}"
    if v <= 3.0:
        return 10.0 - (v - 1.0) * (10 - 6) / 2.0, f"{v:.2f}"  # linear 10→6
    if v <= 8.0:
        return 6.0 - (v - 3.0) * 6 / 5.0, f"{v:.2f}"          # linear 6→0
    return 0.0, f"{v:.2f}"


def score_roe(roe) -> tuple[float, str]:
    """Return on Equity — max 13 pts. Log ascending curve."""
    if roe is None or pd.isna(roe):
        return 0.0, "N/A"
    v = float(roe) * 100  # yfinance returns as decimal
    if v < 0:
        return 0.0, f"{v:.1f}%"
    if v <= 8:
        return v * 5 / 8, f"{v:.1f}%"                          # linear 0→5
    if v <= 20:
        return 5.0 + (v - 8) * (11 - 5) / 12, f"{v:.1f}%"      # linear 5→11
    if v <= 40:
        return 11.0 + (v - 20) * (13 - 11) / 20, f"{v:.1f}%"   # linear 11→13
    return 13.0, f"{v:.1f}%"


def score_roa(roa) -> tuple[float, str]:
    """Return on Assets — max 7 pts. Log ascending curve."""
    if roa is None or pd.isna(roa):
        return 0.0, "N/A"
    v = float(roa) * 100
    if v < 0:
        return 0.0, f"{v:.1f}%"
    if v <= 5:
        return v * 3 / 5, f"{v:.1f}%"                          # linear 0→3
    if v <= 15:
        return 3.0 + (v - 5) * (6 - 3) / 10, f"{v:.1f}%"       # linear 3→6
    if v <= 25:
        return 6.0 + (v - 15) * (7 - 6) / 10, f"{v:.1f}%"      # linear 6→7
    return 7.0, f"{v:.1f}%"


def score_de(de_raw, sector) -> tuple[float, str]:
    """Debt-to-Equity — max 10 pts. Inverse exp curve.
    Banking/NBFC/Insurance get sector_neutral score of 5.
    yfinance returns D/E as a percentage (e.g. 150 = 1.5×).
    """
    if sector in FINANCIAL_SECTORS:
        return 5.0, "N/A (Fin.)"
    if de_raw is None or pd.isna(de_raw):
        return 0.0, "N/A"
    de = float(de_raw) / 100
    if de <= 0.3:
        return 10.0, f"{de:.2f}x"
    if de <= 1.0:
        return 10.0 - (de - 0.3) * (10 - 6) / 0.7, f"{de:.2f}x"  # linear 10→6
    if de <= 2.0:
        return 6.0 - (de - 1.0) * (6 - 3) / 1.0, f"{de:.2f}x"    # linear 6→3
    if de <= 3.0:
        return 3.0 - (de - 2.0) * 3, f"{de:.2f}x"               # linear 3→0
    return 0.0, f"{de:.2f}x"


def score_fcf_yield(market_cap, free_cf) -> tuple[float, str]:
    """FCF Yield — max 10 pts. Log ascending curve.
    Yield = (freeCashflow / marketCap) * 100
    """
    if market_cap is None or free_cf is None or pd.isna(market_cap) or pd.isna(free_cf):
        return 0.0, "N/A"
    if market_cap <= 0:
        return 0.0, "N/A"
    yield_pct = (float(free_cf) / float(market_cap)) * 100
    if yield_pct < 0:
        return 0.0, f"{yield_pct:.2f}%"
    if yield_pct <= 2:
        return yield_pct * 3 / 2, f"{yield_pct:.2f}%"                     # linear 0→3
    if yield_pct <= 8:
        return 3.0 + (yield_pct - 2) * (9 - 3) / 6, f"{yield_pct:.2f}%"   # linear 3→9
    if yield_pct <= 15:
        return 9.0 + (yield_pct - 8) * (10 - 9) / 7, f"{yield_pct:.2f}%"  # linear 9→10
    return 10.0, f"{yield_pct:.2f}%"


def score_op_margin(op_margin) -> tuple[float, str]:
    """Operating Margin — max 8 pts. Log ascending curve."""
    if op_margin is None or pd.isna(op_margin):
        return 0.0, "N/A"
    v = float(op_margin) * 100
    if v < 0:
        return 0.0, f"{v:.1f}%"
    if v <= 5:
        return v * 2 / 5, f"{v:.1f}%"                          # linear 0→2
    if v <= 15:
        return 2.0 + (v - 5) * (5 - 2) / 10, f"{v:.1f}%"       # linear 2→5
    if v <= 25:
        return 5.0 + (v - 15) * (7 - 5) / 10, f"{v:.1f}%"      # linear 5→7
    if v <= 40:
        return 7.0 + (v - 25) * (8 - 7) / 15, f"{v:.1f}%"      # linear 7→8
    return 8.0, f"{v:.1f}%"


def score_eps_growth(eps_g) -> tuple[float, str]:
    """EPS Growth — max 10 pts. Log ascending with negative penalty."""
    if eps_g is None or pd.isna(eps_g):
        return 0.0, "N/A"
    v = float(eps_g) * 100
    if v < -10:
        return 0.0, f"{v:.1f}%"
    if v <= 0:
        return (v + 10) * 2 / 10, f"{v:.1f}%"                   # linear 0→2
    if v <= 10:
        return 2.0 + v * (5 - 2) / 10, f"{v:.1f}%"              # linear 2→5
    if v <= 25:
        return 5.0 + (v - 10) * (9 - 5) / 15, f"{v:.1f}%"       # linear 5→9
    if v <= 60:
        return 9.0 + (v - 25) * (10 - 9) / 35, f"{v:.1f}%"      # linear 9→10
    return 10.0, f"{v:.1f}%"


def score_rev_growth(rev_g) -> tuple[float, str]:
    """Revenue Growth — max 7 pts. Log ascending."""
    if rev_g is None or pd.isna(rev_g):
        return 0.0, "N/A"
    v = float(rev_g) * 100
    if v < -5:
        return 0.0, f"{v:.1f}%"
    if v <= 0:
        return (v + 5) * 1 / 5, f"{v:.1f}%"                     # linear 0→1
    if v <= 10:
        return 1.0 + v * (4 - 1) / 10, f"{v:.1f}%"              # linear 1→4
    if v <= 20:
        return 4.0 + (v - 10) * (6 - 4) / 10, f"{v:.1f}%"       # linear 4→6
    if v <= 50:
        return 6.0 + (v - 20) * (7 - 6) / 30, f"{v:.1f}%"       # linear 6→7
    return 7.0, f"{v:.1f}%"


# ─────────────────────────────────────────────────────────────────────────────
# RECOMMENDATION LABEL
# ─────────────────────────────────────────────────────────────────────────────

def get_recommendation(score: int, thresholds: dict | None = None) -> tuple[str, str]:
    """Return (label, colour_hex) based on composite score."""
    cfg = thresholds or DEFAULT_RECOMMENDATION_THRESHOLDS
    strong_buy = int(cfg.get("strong_buy", 75))
    buy = int(cfg.get("buy", 60))
    hold = int(cfg.get("hold", 45))

    if score >= strong_buy:
        return "Strong Buy", "#00c853"
    if score >= buy:
        return "Buy", "#ffd600"
    if score >= hold:
        return "Hold", "#ff6d00"
    return "Avoid", "#d50000"


REC_EMOJI = {
    "Strong Buy": "🟢",
    "Buy":        "🟡",
    "Hold":       "🟠",
    "Avoid":      "🔴",
}


def _apply_metric_configuration(
    raw_scores: dict[str, float],
    config: dict,
) -> tuple[dict[str, float], dict[str, float], int]:
    """Apply metric enable/weight config and return weighted metric scores and final 0-100 score."""
    lookup = metric_lookup(config)
    weighted_scores: dict[str, float] = {}
    max_weights: dict[str, float] = {}
    weighted_total = 0.0
    max_total = 0.0

    for metric in METRIC_DEFINITIONS:
        metric_id = metric["id"]
        base_max = float(metric["base_max"])
        metric_cfg = lookup.get(metric_id, {})
        enabled = bool(metric_cfg.get("enabled", True))
        weight = float(metric_cfg.get("weight", base_max)) if enabled else 0.0
        weight = max(0.0, weight)

        raw = float(raw_scores.get(metric_id, 0.0))
        raw = max(0.0, min(base_max, raw))
        weighted = (raw / base_max * weight) if base_max > 0 else 0.0

        weighted_scores[metric_id] = round(weighted, 2)
        max_weights[metric_id] = round(weight, 2)
        weighted_total += weighted
        max_total += weight

    final_score = int(round((weighted_total / max_total) * 100)) if max_total > 0 else 0
    final_score = max(0, min(100, final_score))
    return weighted_scores, max_weights, final_score

# ─────────────────────────────────────────────────────────────────────────────
# MAIN FETCH + SCORE FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

def fetch_and_score(
    ticker: str,
    name: str,
    sector: str,
    screening_config: dict | None = None,
) -> dict | None:
    """Fetch fundamentals from yfinance and return a scored record dict.
    Applies hard filters first; returns None if disqualified.
    """
    try:
        config = screening_config or load_screening_config()
        t = yf.Ticker(ticker)
        info = t.fast_info

        price = getattr(info, "last_price", None)
        if price is None or price == 0:
            return None

        full = t.info

        # ─ APPLY HARD FILTERS ─
        is_disq, disq_reason = apply_hard_filters(full, sector)
        if is_disq:
            return {
                "Ticker": ticker.replace(".NS", ""),
                "Name": name,
                "Sector": sector,
                "Status": "DISQUALIFIED",
                "Reason": disq_reason,
            }

        # ─ FETCH ALL FIELDS ─
        pe = full.get("trailingPE")
        peg = full.get("pegRatio")
        pb = full.get("priceToBook")
        roe = full.get("returnOnEquity")
        roa = full.get("returnOnAssets")
        de_raw = full.get("debtToEquity")
        market_cap = full.get("marketCap")
        free_cf = full.get("freeCashflow")
        op_margin = full.get("operatingMargins")
        eps_g = full.get("earningsQuarterlyGrowth")
        rev_g = full.get("revenueGrowth")
        w52_hi = full.get("fiftyTwoWeekHigh")
        w52_lo = full.get("fiftyTwoWeekLow")

        # ─ SCORE EACH METRIC ─
        pe_s, pe_v = score_pe(pe)
        peg_s, peg_v = score_peg(peg)
        pb_s, pb_v = score_pb(pb)
        roe_s, roe_v = score_roe(roe)
        roa_s, roa_v = score_roa(roa)
        de_s, de_v = score_de(de_raw, sector)
        fcf_s, fcf_v = score_fcf_yield(market_cap, free_cf)
        op_s, op_v = score_op_margin(op_margin)
        eps_s, eps_v = score_eps_growth(eps_g)
        rev_s, rev_v = score_rev_growth(rev_g)

        raw_scores = {
            "pe": pe_s,
            "peg": peg_s,
            "pb": pb_s,
            "roe": roe_s,
            "roa": roa_s,
            "de": de_s,
            "fcf_yield": fcf_s,
            "op_margin": op_s,
            "eps_growth": eps_s,
            "rev_growth": rev_s,
        }
        weighted_scores, max_weights, total = _apply_metric_configuration(raw_scores, config)
        label, colour = get_recommendation(total, thresholds=config.get("recommendation_thresholds"))

        # 52-week position
        if w52_hi and w52_lo and price and (w52_hi - w52_lo) > 0:
            w52_pos = round((price - w52_lo) / (w52_hi - w52_lo) * 100, 1)
        else:
            w52_pos = None

        # Market cap bucket
        if market_cap:
            if market_cap >= 2e12:       cap_label = "Large (>₹2T)"
            elif market_cap >= 5e11:     cap_label = "Mid (₹0.5–2T)"
            else:                        cap_label = "Small (<₹0.5T)"
        else:
            cap_label = "N/A"

        return {
            # Identity
            "Ticker":         ticker.replace(".NS", ""),
            "Name":           name,
            "Sector":         sector,
            "Status":         "SCORED",
            # Price info
            "Price (₹)":      round(price, 2),
            "52W High":       round(w52_hi, 2)  if w52_hi else None,
            "52W Low":        round(w52_lo, 2)  if w52_lo else None,
            "52W Position":   w52_pos,
            "Market Cap":     market_cap,
            "Cap Bucket":     cap_label,
            # Composite
            "Score":          total,
            "Recommendation": label,
            "Colour":         colour,
            # Display values
            "P/E":            pe_v,
            "PEG":            peg_v,
            "P/B":            pb_v,
            "ROE":            roe_v,
            "ROA":            roa_v,
            "D/E":            de_v,
            "FCF Yield":      fcf_v,
            "Op Margin":      op_v,
            "EPS Growth":     eps_v,
            "Rev Growth":     rev_v,
            # Component scores (for radar chart)
            "s_PE":           weighted_scores["pe"],
            "s_PEG":          weighted_scores["peg"],
            "s_PB":           weighted_scores["pb"],
            "s_ROE":          weighted_scores["roe"],
            "s_ROA":          weighted_scores["roa"],
            "s_DE":           weighted_scores["de"],
            "s_FCF":          weighted_scores["fcf_yield"],
            "s_OpM":          weighted_scores["op_margin"],
            "s_EPS":          weighted_scores["eps_growth"],
            "s_Rev":          weighted_scores["rev_growth"],
            "m_PE":           max_weights["pe"],
            "m_PEG":          max_weights["peg"],
            "m_PB":           max_weights["pb"],
            "m_ROE":          max_weights["roe"],
            "m_ROA":          max_weights["roa"],
            "m_DE":           max_weights["de"],
            "m_FCF":          max_weights["fcf_yield"],
            "m_OpM":          max_weights["op_margin"],
            "m_EPS":          max_weights["eps_growth"],
            "m_Rev":          max_weights["rev_growth"],
        }
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# HELPER: fetch 1-year price history for deep-dive chart
# ─────────────────────────────────────────────────────────────────────────────

def fetch_price_history(ticker: str) -> pd.DataFrame:
    try:
        df = yf.download(ticker, period="1y", progress=False, auto_adjust=True)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df
    except Exception:
        return pd.DataFrame()


def fetch_price_returns(tickers: list[str], start_date: str) -> dict[str, float]:
    """
    Fetch price returns for a list of tickers from start_date to today.
    Returns a dict of {ticker: return_percentage}.
    NIFTY 50 is stored under key "^NSEI".
    """
    from datetime import date as _date
    end_date = _date.today().strftime("%Y-%m-%d")  # Always use actual today
    results = {}

    # Add NIFTY 50 to the fetch list
    all_tickers = ["^NSEI"] + [t if t.endswith(".NS") else f"{t}.NS" for t in tickers]

    try:
        data = yf.download(all_tickers, start=start_date, end=end_date, progress=False, auto_adjust=True)
        if data.empty:
            return {}

        if isinstance(data.columns, pd.MultiIndex):
            prices = data["Close"]
        else:
            prices = data[["Close"]]

        for ticker in all_tickers:
            try:
                # Handle single vs multi ticker return from yfinance
                if isinstance(prices, pd.Series):
                    series = prices
                else:
                    series = prices[ticker]

                series = series.dropna()
                if len(series) >= 2:
                    p_start = series.iloc[0]
                    p_end = series.iloc[-1]
                    ret = float((p_end - p_start) / p_start * 100)
                    if ticker == "^NSEI":
                        results["^NSEI"] = ret          # FIX: was "NIFTY50", now "^NSEI"
                    else:
                        results[ticker.replace(".NS", "")] = ret
                else:
                    results[ticker.replace(".NS", "")] = np.nan
            except Exception:
                results[ticker.replace(".NS", "")] = np.nan
    except Exception:
        pass

    return results


def calculate_outperformance(stock_return: float, nifty_return: float) -> float:
    if pd.isna(stock_return) or pd.isna(nifty_return):
        return np.nan
    return stock_return - nifty_return


# ─────────────────────────────────────────────────────────────────────────────
# TWO-STEP SCREENING: Download base data → Cache locally → Apply scoring
# ─────────────────────────────────────────────────────────────────────────────

def fetch_and_cache_base_data(
    stocks: list[tuple[str, str, str]],
    output_path: str,
    progress_callback=None,
) -> tuple[pd.DataFrame, int, int]:
    """
    Fetch raw fundamental data from yfinance for all stocks and cache to CSV.
    Returns (dataframe, total_fetched, total_failed)
    
    Args:
        stocks: List of (ticker, name, sector) tuples
        output_path: Path to save base_data.csv
        progress_callback: Optional callable(i, total, ticker, name) for UI updates
    """
    from pathlib import Path
    
    base_data = []
    total_failed = 0
    
    for i, (ticker, name, sector) in enumerate(stocks):
        if progress_callback:
            progress_callback(i, len(stocks), ticker, name)
        
        try:
            t = yf.Ticker(ticker)
            info = t.fast_info
            price = getattr(info, "last_price", None)
            
            if price is None or price == 0:
                total_failed += 1
                continue
            
            full = t.info
            
            # Store all fundamental data
            record = {
                "Ticker": ticker.replace(".NS", ""),
                "Name": name,
                "Sector": sector,
                "trailingPE": full.get("trailingPE"),
                "pegRatio": full.get("pegRatio"),
                "priceToBook": full.get("priceToBook"),
                "returnOnEquity": full.get("returnOnEquity"),
                "returnOnAssets": full.get("returnOnAssets"),
                "debtToEquity": full.get("debtToEquity"),
                "marketCap": full.get("marketCap"),
                "freeCashflow": full.get("freeCashflow"),
                "operatingMargins": full.get("operatingMargins"),
                "earningsQuarterlyGrowth": full.get("earningsQuarterlyGrowth"),
                "revenueGrowth": full.get("revenueGrowth"),
                "lastPrice": price,
                "fiftyTwoWeekHigh": full.get("fiftyTwoWeekHigh"),
                "fiftyTwoWeekLow": full.get("fiftyTwoWeekLow"),
                "currentRatio": full.get("currentRatio"),
            }
            base_data.append(record)
            time.sleep(0.05)  # Rate limit
        
        except Exception:
            total_failed += 1
            continue
    
    # Save to CSV
    df = pd.DataFrame(base_data)
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_file, index=False)
    
    return df, len(base_data), total_failed


def score_from_cached_base_data(
    base_data_path: str,
    sector_filter: list[str] | None = None,
    screening_config: dict | None = None,
) -> pd.DataFrame:
    """
    Load cached base data and apply scoring + filtering.
    Returns scored dataframe ready for display.
    
    Args:
        base_data_path: Path to base_data.csv
        sector_filter: Optional list of sectors to filter
        screening_config: Optional screening config (uses default if None)
    """
    config = screening_config or load_screening_config()
    
    # Load cached base data
    base_df = pd.read_csv(base_data_path)
    
    # Filter by sector if provided
    if sector_filter:
        base_df = base_df[base_df["Sector"].isin(sector_filter)]
    
    results = []
    for _, row in base_df.iterrows():
        ticker = row["Ticker"]
        name = row["Name"]
        sector = row["Sector"]
        
        # Build full_info dict from cached data
        full_info = {
            "trailingPE": row.get("trailingPE"),
            "pegRatio": row.get("pegRatio"),
            "priceToBook": row.get("priceToBook"),
            "returnOnEquity": row.get("returnOnEquity"),
            "returnOnAssets": row.get("returnOnAssets"),
            "debtToEquity": row.get("debtToEquity"),
            "marketCap": row.get("marketCap"),
            "freeCashflow": row.get("freeCashflow"),
            "operatingMargins": row.get("operatingMargins"),
            "earningsQuarterlyGrowth": row.get("earningsQuarterlyGrowth"),
            "revenueGrowth": row.get("revenueGrowth"),
            "fiftyTwoWeekHigh": row.get("fiftyTwoWeekHigh"),
            "fiftyTwoWeekLow": row.get("fiftyTwoWeekLow"),
            "currentRatio": row.get("currentRatio"),
        }
        
        # Apply hard filters
        is_disq, disq_reason = apply_hard_filters(full_info, sector)
        if is_disq:
            continue
        
        # Extract metrics
        price = row.get("lastPrice")
        pe = full_info.get("trailingPE")
        peg = full_info.get("pegRatio")
        pb = full_info.get("priceToBook")
        roe = full_info.get("returnOnEquity")
        roa = full_info.get("returnOnAssets")
        de_raw = full_info.get("debtToEquity")
        market_cap = full_info.get("marketCap")
        free_cf = full_info.get("freeCashflow")
        op_margin = full_info.get("operatingMargins")
        eps_g = full_info.get("earningsQuarterlyGrowth")
        rev_g = full_info.get("revenueGrowth")
        w52_hi = full_info.get("fiftyTwoWeekHigh")
        w52_lo = full_info.get("fiftyTwoWeekLow")
        
        # Score metrics
        pe_s, pe_v = score_pe(pe)
        peg_s, peg_v = score_peg(peg)
        pb_s, pb_v = score_pb(pb)
        roe_s, roe_v = score_roe(roe)
        roa_s, roa_v = score_roa(roa)
        de_s, de_v = score_de(de_raw, sector)
        fcf_s, fcf_v = score_fcf_yield(market_cap, free_cf)
        op_s, op_v = score_op_margin(op_margin)
        eps_s, eps_v = score_eps_growth(eps_g)
        rev_s, rev_v = score_rev_growth(rev_g)
        
        raw_scores = {
            "pe": pe_s,
            "peg": peg_s,
            "pb": pb_s,
            "roe": roe_s,
            "roa": roa_s,
            "de": de_s,
            "fcf_yield": fcf_s,
            "op_margin": op_s,
            "eps_growth": eps_s,
            "rev_growth": rev_s,
        }
        weighted_scores, max_weights, total = _apply_metric_configuration(raw_scores, config)
        label, colour = get_recommendation(total, thresholds=config.get("recommendation_thresholds"))
        
        # 52-week position
        if w52_hi and w52_lo and price and (w52_hi - w52_lo) > 0:
            w52_pos = round((price - w52_lo) / (w52_hi - w52_lo) * 100, 1)
        else:
            w52_pos = None
        
        # Market cap bucket
        if market_cap:
            if market_cap >= 2e12:       cap_label = "Large (>₹2T)"
            elif market_cap >= 5e11:     cap_label = "Mid (₹0.5–2T)"
            else:                        cap_label = "Small (<₹0.5T)"
        else:
            cap_label = "N/A"
        
        result = {
            "Ticker": ticker,
            "Name": name,
            "Sector": sector,
            "Status": "SCORED",
            "Price (Rs)": round(price, 2) if price else None,
            "52W High": round(w52_hi, 2) if w52_hi else None,
            "52W Low": round(w52_lo, 2) if w52_lo else None,
            "52W Position": w52_pos,
            "Market Cap": market_cap,
            "Cap Bucket": cap_label,
            "Score": total,
            "Recommendation": label,
            "Colour": colour,
            "P/E": pe_v,
            "PEG": peg_v,
            "P/B": pb_v,
            "ROE": roe_v,
            "ROA": roa_v,
            "D/E": de_v,
            "FCF Yield": fcf_v,
            "Op Margin": op_v,
            "EPS Growth": eps_v,
            "Rev Growth": rev_v,
            "s_PE": weighted_scores["pe"],
            "s_PEG": weighted_scores["peg"],
            "s_PB": weighted_scores["pb"],
            "s_ROE": weighted_scores["roe"],
            "s_ROA": weighted_scores["roa"],
            "s_DE": weighted_scores["de"],
            "s_FCF": weighted_scores["fcf_yield"],
            "s_OpM": weighted_scores["op_margin"],
            "s_EPS": weighted_scores["eps_growth"],
            "s_Rev": weighted_scores["rev_growth"],
            "m_PE": max_weights["pe"],
            "m_PEG": max_weights["peg"],
            "m_PB": max_weights["pb"],
            "m_ROE": max_weights["roe"],
            "m_ROA": max_weights["roa"],
            "m_DE": max_weights["de"],
            "m_FCF": max_weights["fcf_yield"],
            "m_OpM": max_weights["op_margin"],
            "m_EPS": max_weights["eps_growth"],
            "m_Rev": max_weights["rev_growth"],
        }
        results.append(result)
    
    return pd.DataFrame(results)