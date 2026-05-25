# screener.py — Fetch fundamentals from yfinance and score each stock

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
# SCORING FUNCTIONS  (max points shown for each)
# ─────────────────────────────────────────────────────────────────────────────

def score_pe(pe) -> tuple[int, str]:
    """P/E Ratio — max 20 pts. Lower is better."""
    if pe is None or pd.isna(pe) or pe <= 0:
        return 0, "N/A"
    v = float(pe)
    if v < 10:  return 20, f"{v:.1f}"
    if v < 15:  return 17, f"{v:.1f}"
    if v < 20:  return 14, f"{v:.1f}"
    if v < 25:  return 11, f"{v:.1f}"
    if v < 30:  return 8,  f"{v:.1f}"
    if v < 40:  return 5,  f"{v:.1f}"
    if v < 60:  return 2,  f"{v:.1f}"
    return 0, f"{v:.1f}"


def score_pb(pb) -> tuple[int, str]:
    """P/B Ratio — max 15 pts. Lower is better."""
    if pb is None or pd.isna(pb) or pb <= 0:
        return 0, "N/A"
    v = float(pb)
    if v < 1:   return 15, f"{v:.2f}"
    if v < 2:   return 12, f"{v:.2f}"
    if v < 3:   return 9,  f"{v:.2f}"
    if v < 5:   return 5,  f"{v:.2f}"
    return 2, f"{v:.2f}"


def score_roe(roe) -> tuple[int, str]:
    """Return on Equity — max 20 pts. Higher is better."""
    if roe is None or pd.isna(roe):
        return 0, "N/A"
    v = float(roe) * 100          # yfinance returns as decimal
    if v > 30:  return 20, f"{v:.1f}%"
    if v > 25:  return 17, f"{v:.1f}%"
    if v > 20:  return 14, f"{v:.1f}%"
    if v > 15:  return 10, f"{v:.1f}%"
    if v > 10:  return 6,  f"{v:.1f}%"
    if v > 0:   return 2,  f"{v:.1f}%"
    return 0, f"{v:.1f}%"


def score_de(de_raw, sector) -> tuple[int, str]:
    """Debt/Equity — max 15 pts. Lower is better.
    Banks/NBFC/Insurance get a neutral 7 (D/E is structurally high for them).
    yfinance returns D/E as a percentage value (e.g. 150 = 1.5×).
    """
    if sector in FINANCIAL_SECTORS:
        return 7, "N/A (Fin.)"
    if de_raw is None or pd.isna(de_raw):
        return 7, "N/A"           # neutral if missing
    de = float(de_raw) / 100      # normalise to ratio
    if de < 0.2:  return 15, f"{de:.2f}x"
    if de < 0.5:  return 12, f"{de:.2f}x"
    if de < 1.0:  return 8,  f"{de:.2f}x"
    if de < 2.0:  return 4,  f"{de:.2f}x"
    return 1, f"{de:.2f}x"


def score_eps_growth(g) -> tuple[int, str]:
    """EPS Growth YoY — max 15 pts. Higher is better."""
    if g is None or pd.isna(g):
        return 5, "N/A"           # neutral
    v = float(g) * 100
    if v > 30:  return 15, f"{v:.1f}%"
    if v > 20:  return 12, f"{v:.1f}%"
    if v > 10:  return 9,  f"{v:.1f}%"
    if v > 5:   return 6,  f"{v:.1f}%"
    if v > 0:   return 3,  f"{v:.1f}%"
    return 0, f"{v:.1f}%"


def score_rev_growth(g) -> tuple[int, str]:
    """Revenue Growth YoY — max 10 pts. Higher is better."""
    if g is None or pd.isna(g):
        return 3, "N/A"           # neutral
    v = float(g) * 100
    if v > 25:  return 10, f"{v:.1f}%"
    if v > 15:  return 8,  f"{v:.1f}%"
    if v > 10:  return 6,  f"{v:.1f}%"
    if v > 5:   return 4,  f"{v:.1f}%"
    if v > 0:   return 2,  f"{v:.1f}%"
    return 0, f"{v:.1f}%"


def score_div_yield(dy) -> tuple[int, str]:
    """Dividend Yield — max 5 pts. Higher is better."""
    if dy is None or pd.isna(dy) or float(dy) == 0:
        return 0, "0.00%"
    v = float(dy) * 100
    if v > 4:   return 5, f"{v:.2f}%"
    if v > 3:   return 4, f"{v:.2f}%"
    if v > 2:   return 3, f"{v:.2f}%"
    if v > 1:   return 2, f"{v:.2f}%"
    return 1, f"{v:.2f}%"


# ─────────────────────────────────────────────────────────────────────────────
# RECOMMENDATION LABEL
# ─────────────────────────────────────────────────────────────────────────────

def get_recommendation(score: int, thresholds: dict | None = None) -> tuple[str, str]:
    """Return (label, colour_hex) based on composite score."""
    cfg = thresholds or DEFAULT_RECOMMENDATION_THRESHOLDS
    strong_buy = int(cfg.get("strong_buy", DEFAULT_RECOMMENDATION_THRESHOLDS["strong_buy"]))
    buy = int(cfg.get("buy", DEFAULT_RECOMMENDATION_THRESHOLDS["buy"]))
    hold = int(cfg.get("hold", DEFAULT_RECOMMENDATION_THRESHOLDS["hold"]))

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
    """Fetch fundamentals from yfinance and return a scored record dict."""
    try:
        config = screening_config or load_screening_config()
        t = yf.Ticker(ticker)
        info = t.fast_info          # lightweight metadata first

        price = getattr(info, "last_price", None)
        if price is None or price == 0:
            return None             # skip if no live price

        full = t.info               # full metadata (heavier)

        pe        = full.get("trailingPE")
        pb        = full.get("priceToBook")
        roe       = full.get("returnOnEquity")
        de_raw    = full.get("debtToEquity")
        eps_g     = full.get("earningsGrowth")
        rev_g     = full.get("revenueGrowth")
        div_y     = full.get("dividendYield")
        mktcap    = full.get("marketCap")
        w52_hi    = full.get("fiftyTwoWeekHigh")
        w52_lo    = full.get("fiftyTwoWeekLow")

        # Score each metric
        pe_s,  pe_v  = score_pe(pe)
        pb_s,  pb_v  = score_pb(pb)
        roe_s, roe_v = score_roe(roe)
        de_s,  de_v  = score_de(de_raw, sector)
        eps_s, eps_v = score_eps_growth(eps_g)
        rev_s, rev_v = score_rev_growth(rev_g)
        div_s, div_v = score_div_yield(div_y)

        raw_scores = {
            "pe": pe_s,
            "pb": pb_s,
            "roe": roe_s,
            "de": de_s,
            "eps": eps_s,
            "rev": rev_s,
            "div": div_s,
        }
        weighted_scores, max_weights, total = _apply_metric_configuration(raw_scores, config)
        label, colour = get_recommendation(total, thresholds=config.get("recommendation_thresholds"))

        # 52-week position (0–100%)
        if w52_hi and w52_lo and price and (w52_hi - w52_lo) > 0:
            w52_pos = round((price - w52_lo) / (w52_hi - w52_lo) * 100, 1)
        else:
            w52_pos = None

        # Market cap bucket
        if mktcap:
            if mktcap >= 2e12:       cap_label = "Large (>₹2T)"
            elif mktcap >= 5e11:     cap_label = "Mid (₹0.5–2T)"
            else:                    cap_label = "Small (<₹0.5T)"
        else:
            cap_label = "N/A"

        return {
            # Identity
            "Ticker":         ticker.replace(".NS", ""),
            "Name":           name,
            "Sector":         sector,
            # Price info
            "Price (₹)":      round(price, 2),
            "52W High":       round(w52_hi, 2)  if w52_hi else None,
            "52W Low":        round(w52_lo, 2)  if w52_lo else None,
            "52W Position":   w52_pos,
            "Market Cap":     mktcap,
            "Cap Bucket":     cap_label,
            # Composite
            "Score":          total,
            "Recommendation": label,
            "Colour":         colour,
            # Display values
            "P/E":            pe_v,
            "P/B":            pb_v,
            "ROE":            roe_v,
            "D/E":            de_v,
            "EPS Growth":     eps_v,
            "Rev Growth":     rev_v,
            "Div Yield":      div_v,
            # Component scores (for radar chart)
            "s_PE":           weighted_scores["pe"],
            "s_PB":           weighted_scores["pb"],
            "s_ROE":          weighted_scores["roe"],
            "s_DE":           weighted_scores["de"],
            "s_EPS":          weighted_scores["eps"],
            "s_Rev":          weighted_scores["rev"],
            "s_Div":          weighted_scores["div"],
            "m_PE":           max_weights["pe"],
            "m_PB":           max_weights["pb"],
            "m_ROE":          max_weights["roe"],
            "m_DE":           max_weights["de"],
            "m_EPS":          max_weights["eps"],
            "m_Rev":          max_weights["rev"],
            "m_Div":          max_weights["div"],
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
