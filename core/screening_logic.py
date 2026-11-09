"""Screening logic configuration: metric definitions, weights, thresholds.

Settings live in data/screening_logic.json so scoring can be tuned without
code edits.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
SCREENING_CONFIG_PATH = DATA_DIR / "screening_logic.json"

CONFIG_VERSION = 2

# `column` is the numeric display column, `unit` how it is formatted.
METRIC_DEFINITIONS = [
    {
        "id": "pe",
        "label": "P/E",
        "column": "P/E",
        "unit": "x",
        "base_max": 12,
        "score_col": "s_PE",
        "max_col": "m_PE",
        "source": "Yahoo Finance `trailingPE` (price / trailing 12-month EPS)",
        "description": "Price-to-Earnings: market price per share divided by trailing 12-month earnings per share. Lower is cheaper. Zero or negative earnings score 0.",
        "good_range": "Full points at 10 or below, tapering to 0 at 60.",
    },
    {
        "id": "peg",
        "label": "PEG",
        "column": "PEG",
        "unit": "x",
        "base_max": 13,
        "score_col": "s_PEG",
        "max_col": "m_PEG",
        "source": "Yahoo Finance `pegRatio`, else `trailingPegRatio`",
        "description": "P/E divided by the earnings growth rate. Below 1 suggests the valuation is low relative to growth. Yahoo often does not publish this for Indian stocks; it is then marked Not available.",
        "good_range": "Full points at 0.75 or below, tapering to 0 at 3.0.",
    },
    {
        "id": "pb",
        "label": "P/B",
        "column": "P/B",
        "unit": "x",
        "base_max": 10,
        "score_col": "s_PB",
        "max_col": "m_PB",
        "source": "Yahoo Finance `priceToBook`",
        "description": "Price-to-Book: market price divided by book value per share. Negative book value scores 0.",
        "good_range": "Full points at 1.0 or below, tapering to 0 at 8.0.",
    },
    {
        "id": "roe",
        "label": "ROE",
        "column": "ROE %",
        "unit": "%",
        "base_max": 13,
        "score_col": "s_ROE",
        "max_col": "m_ROE",
        "source": "Yahoo Finance `returnOnEquity` (trailing 12 months)",
        "description": "Return on Equity: net income divided by shareholder equity.",
        "good_range": "0 points at 0%, 11 at 20%, full points at 40% or above.",
    },
    {
        "id": "roa",
        "label": "ROA",
        "column": "ROA %",
        "unit": "%",
        "base_max": 7,
        "score_col": "s_ROA",
        "max_col": "m_ROA",
        "source": "Yahoo Finance `returnOnAssets` (trailing 12 months)",
        "description": "Return on Assets: net income divided by total assets.",
        "good_range": "0 points at 0%, 6 at 15%, full points at 25% or above.",
    },
    {
        "id": "de",
        "label": "D/E",
        "column": "D/E",
        "unit": "x",
        "base_max": 10,
        "score_col": "s_DE",
        "max_col": "m_DE",
        "source": "Yahoo Finance `debtToEquity` (reported in %, converted to a ratio)",
        "description": "Debt-to-Equity: total debt divided by shareholder equity. Not applicable to the Financial Services sector, where borrowing is the business model; it is excluded from their score instead of being given assumed points.",
        "good_range": "Full points at 0.3x or below, 0 at 3.0x or above.",
    },
    {
        "id": "fcf_yield",
        "label": "FCF Yield",
        "column": "FCF Yield %",
        "unit": "%",
        "base_max": 10,
        "score_col": "s_FCF",
        "max_col": "m_FCF",
        "source": "Yahoo Finance `freeCashflow` / `marketCap`",
        "description": "Free cash flow divided by market capitalisation. Only computed when the financial statements and the share price are in the same currency.",
        "good_range": "0 points at 0%, 9 at 8%, full points at 15% or above.",
    },
    {
        "id": "op_margin",
        "label": "Op Margin",
        "column": "Op Margin %",
        "unit": "%",
        "base_max": 8,
        "score_col": "s_OpM",
        "max_col": "m_OpM",
        "source": "Yahoo Finance `operatingMargins` (trailing 12 months)",
        "description": "Operating income divided by revenue. Varies a lot by industry.",
        "good_range": "0 points at 0%, 5 at 15%, full points at 40% or above.",
    },
    {
        "id": "eps_growth",
        "label": "Earnings Growth",
        "column": "Earnings Growth %",
        "unit": "%",
        "base_max": 10,
        "score_col": "s_EPS",
        "max_col": "m_EPS",
        "source": "Yahoo Finance `earningsQuarterlyGrowth` (latest quarter vs same quarter last year)",
        "description": "Year-over-year growth in net earnings for the most recent quarter. A single quarter can be distorted by one-off items.",
        "good_range": "0 points at -10% or below, 5 at 10%, full points at 60% or above.",
    },
    {
        "id": "rev_growth",
        "label": "Revenue Growth",
        "column": "Revenue Growth %",
        "unit": "%",
        "base_max": 7,
        "score_col": "s_Rev",
        "max_col": "m_Rev",
        "source": "Yahoo Finance `revenueGrowth` (latest quarter vs same quarter last year)",
        "description": "Year-over-year revenue growth for the most recent quarter.",
        "good_range": "0 points at -5% or below, 4 at 10%, full points at 50% or above.",
    },
]

DEFAULT_RECOMMENDATION_THRESHOLDS = {
    "strong_buy": 75,
    "buy": 60,
    "hold": 45,
}

# Minimum share (in %) of the enabled, applicable weight that must have real
# data before a recommendation is issued.
DEFAULT_MIN_DATA_COVERAGE = 70

DEFAULT_SCREENING_CONFIG = {
    "version": CONFIG_VERSION,
    "metrics": [
        {
            "id": metric["id"],
            "label": metric["label"],
            "enabled": True,
            "weight": float(metric["base_max"]),
            "base_max": float(metric["base_max"]),
        }
        for metric in METRIC_DEFINITIONS
    ],
    "recommendation_thresholds": DEFAULT_RECOMMENDATION_THRESHOLDS,
    "min_data_coverage": DEFAULT_MIN_DATA_COVERAGE,
}


def get_default_config() -> dict[str, Any]:
    return deepcopy(DEFAULT_SCREENING_CONFIG)


def _clamp_weight(weight: Any, fallback: float) -> float:
    try:
        value = float(weight)
    except (TypeError, ValueError):
        return fallback
    if value != value:  # NaN
        return fallback
    return round(min(max(value, 0.0), 100.0), 2)


def validate_thresholds(raw: Any) -> tuple[dict[str, int], str | None]:
    """Return (thresholds, error). Falls back to defaults when invalid."""
    if not isinstance(raw, dict):
        return dict(DEFAULT_RECOMMENDATION_THRESHOLDS), None
    values: dict[str, int] = {}
    for key, fallback in DEFAULT_RECOMMENDATION_THRESHOLDS.items():
        try:
            values[key] = int(raw.get(key, fallback))
        except (TypeError, ValueError):
            return dict(DEFAULT_RECOMMENDATION_THRESHOLDS), f"Threshold '{key}' is not a whole number."
    if not (100 >= values["strong_buy"] > values["buy"] > values["hold"] >= 0):
        return (
            dict(DEFAULT_RECOMMENDATION_THRESHOLDS),
            "Thresholds must satisfy 100 >= Strong Buy > Buy > Hold >= 0.",
        )
    return values, None


def normalize_config(raw_config: dict[str, Any] | None) -> dict[str, Any]:
    default = get_default_config()
    if not isinstance(raw_config, dict):
        return default

    raw_lookup: dict[str, dict[str, Any]] = {}
    raw_metrics = raw_config.get("metrics")
    if isinstance(raw_metrics, list):
        for item in raw_metrics:
            if isinstance(item, dict) and item.get("id"):
                raw_lookup[str(item["id"])] = item

    normalized_metrics = []
    for metric in default["metrics"]:
        raw_metric = raw_lookup.get(metric["id"], {})
        normalized_metrics.append(
            {
                "id": metric["id"],
                "label": metric["label"],
                "enabled": bool(raw_metric.get("enabled", metric["enabled"])),
                "weight": _clamp_weight(raw_metric.get("weight", metric["weight"]), metric["weight"]),
                "base_max": float(metric["base_max"]),
            }
        )

    thresholds, _ = validate_thresholds(raw_config.get("recommendation_thresholds"))

    try:
        coverage = int(raw_config.get("min_data_coverage", DEFAULT_MIN_DATA_COVERAGE))
    except (TypeError, ValueError):
        coverage = DEFAULT_MIN_DATA_COVERAGE
    coverage = min(max(coverage, 0), 100)

    return {
        "version": CONFIG_VERSION,
        "metrics": normalized_metrics,
        "recommendation_thresholds": thresholds,
        "min_data_coverage": coverage,
    }


def save_screening_config(config: dict[str, Any], path: Path = SCREENING_CONFIG_PATH) -> dict[str, Any]:
    normalized = normalize_config(config)
    path.write_text(json.dumps(normalized, indent=2), encoding="utf-8")
    return normalized


def load_screening_config(path: Path = SCREENING_CONFIG_PATH) -> dict[str, Any]:
    if not path.exists():
        return save_screening_config(get_default_config(), path=path)

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return save_screening_config(get_default_config(), path=path)

    normalized = normalize_config(raw)
    if normalized != raw:
        save_screening_config(normalized, path=path)
    return normalized


def metric_lookup(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    metrics = config.get("metrics", []) if isinstance(config, dict) else []
    return {
        str(metric["id"]): metric
        for metric in metrics
        if isinstance(metric, dict) and metric.get("id")
    }
