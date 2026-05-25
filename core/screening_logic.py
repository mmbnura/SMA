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
    {"id": "pe", "label": "P/E", "base_max": 20, "score_col": "s_PE", "max_col": "m_PE"},
    {"id": "pb", "label": "P/B", "base_max": 15, "score_col": "s_PB", "max_col": "m_PB"},
    {"id": "roe", "label": "ROE", "base_max": 20, "score_col": "s_ROE", "max_col": "m_ROE"},
    {"id": "de", "label": "D/E", "base_max": 15, "score_col": "s_DE", "max_col": "m_DE"},
    {"id": "eps", "label": "EPS Growth", "base_max": 15, "score_col": "s_EPS", "max_col": "m_EPS"},
    {"id": "rev", "label": "Rev Growth", "base_max": 10, "score_col": "s_Rev", "max_col": "m_Rev"},
    {"id": "div", "label": "Div Yield", "base_max": 5, "score_col": "s_Div", "max_col": "m_Div"},
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
