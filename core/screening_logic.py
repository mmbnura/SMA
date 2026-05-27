"""Screening logic configuration helpers.

This module stores editable scoring settings in a JSON file so the app can
change screening behavior without code edits.
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

METRIC_DEFINITIONS = [
    {
        "id": "pe",
        "label": "P/E",
        "base_max": 12,
        "score_col": "s_PE",
        "max_col": "m_PE",
        "description": "Price-to-Earnings ratio: Market price per share divided by earnings per share. Lower values indicate cheaper valuations.",
        "good_range": "< 25 (15-20 is attractive for value investing)",
    },
    {
        "id": "peg",
        "label": "PEG",
        "base_max": 13,
        "score_col": "s_PEG",
        "max_col": "m_PEG",
        "description": "PEG Ratio: P/E divided by expected earnings growth rate. Helps identify undervalued growth stocks.",
        "good_range": "< 1.0 (closer to 0.5-1.0 is ideal)",
    },
    {
        "id": "pb",
        "label": "P/B",
        "base_max": 10,
        "score_col": "s_PB",
        "max_col": "m_PB",
        "description": "Price-to-Book ratio: Market price per share divided by book value per share. Lower values suggest better value.",
        "good_range": "1.0 - 3.0 (< 1.0 may indicate undervaluation or distress)",
    },
    {
        "id": "roe",
        "label": "ROE",
        "base_max": 13,
        "score_col": "s_ROE",
        "max_col": "m_ROE",
        "description": "Return on Equity: Net income divided by shareholder equity. Measures how efficiently company uses shareholder capital.",
        "good_range": "> 15% (above 20% is excellent)",
    },
    {
        "id": "roa",
        "label": "ROA",
        "base_max": 7,
        "score_col": "s_ROA",
        "max_col": "m_ROA",
        "description": "Return on Assets: Net income divided by total assets. Measures how efficiently company uses all assets.",
        "good_range": "> 5% (above 10% is strong)",
    },
    {
        "id": "de",
        "label": "D/E",
        "base_max": 10,
        "score_col": "s_DE",
        "max_col": "m_DE",
        "description": "Debt-to-Equity ratio: Total debt divided by total equity. Lower values indicate less financial leverage and lower risk.",
        "good_range": "< 1.0 (0.3-0.7 is healthy for most industries)",
    },
    {
        "id": "fcf_yield",
        "label": "FCF Yield",
        "base_max": 10,
        "score_col": "s_FCF",
        "max_col": "m_FCF",
        "description": "Free Cash Flow Yield: Operating cash flow minus capital expenditures, divided by market cap. Shows cash available to shareholders.",
        "good_range": "> 5% (above 8% is attractive)",
    },
    {
        "id": "op_margin",
        "label": "Op Margin",
        "base_max": 8,
        "score_col": "s_OpM",
        "max_col": "m_OpM",
        "description": "Operating Margin: Operating income divided by revenue. Measures operational efficiency and pricing power.",
        "good_range": "> 10% (above 15% is excellent, varies by industry)",
    },
    {
        "id": "eps_growth",
        "label": "EPS Growth",
        "base_max": 10,
        "score_col": "s_EPS",
        "max_col": "m_EPS",
        "description": "Earnings Per Share Growth: Year-over-year or 3-5 year average growth rate. Indicates company earnings expansion.",
        "good_range": "> 10% annually (15%+ is strong growth)",
    },
    {
        "id": "rev_growth",
        "label": "Rev Growth",
        "base_max": 7,
        "score_col": "s_Rev",
        "max_col": "m_Rev",
        "description": "Revenue Growth: Year-over-year or 3-5 year average growth rate. Shows top-line expansion and business scale.",
        "good_range": "> 10% annually (15%+ indicates strong growth)",
    },
]

DEFAULT_RECOMMENDATION_THRESHOLDS = {
    "strong_buy": 75,
    "buy": 60,
    "hold": 45,
}

DEFAULT_SCREENING_CONFIG = {
    "version": 1,
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
}


def get_default_config() -> dict[str, Any]:
    return deepcopy(DEFAULT_SCREENING_CONFIG)


def _clamp_weight(weight: Any, fallback: float) -> float:
    try:
        value = float(weight)
    except (TypeError, ValueError):
        return fallback
    if value < 0:
        return 0.0
    return round(value, 2)


def normalize_config(raw_config: dict[str, Any] | None) -> dict[str, Any]:
    default = get_default_config()
    if not isinstance(raw_config, dict):
        return default

    raw_metrics = raw_config.get("metrics")
    raw_lookup: dict[str, dict[str, Any]] = {}
    if isinstance(raw_metrics, list):
        for item in raw_metrics:
            if isinstance(item, dict) and item.get("id"):
                raw_lookup[str(item["id"])] = item

    normalized_metrics: list[dict[str, Any]] = []
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

    raw_thresholds = raw_config.get("recommendation_thresholds", {})
    thresholds: dict[str, int] = {}
    for key, fallback in DEFAULT_RECOMMENDATION_THRESHOLDS.items():
        try:
            thresholds[key] = int(raw_thresholds.get(key, fallback))
        except (TypeError, ValueError):
            thresholds[key] = fallback

    return {
        "version": int(raw_config.get("version", default["version"])),
        "metrics": normalized_metrics,
        "recommendation_thresholds": thresholds,
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
