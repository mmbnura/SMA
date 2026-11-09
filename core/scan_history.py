import json
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_FILE = str(DATA_DIR / "scan_history.db")

# Columns added after the first release; created on demand for older databases.
_ADDED_COLUMNS = {
    "total_disqualified": "INTEGER",
    "total_unavailable": "INTEGER",
    "excluded_json": "TEXT",
    "config_json": "TEXT",
}


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(DB_FILE)


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS scan_runs (
                scan_id TEXT PRIMARY KEY,
                scan_type TEXT NOT NULL,
                created_at TEXT NOT NULL,
                selected_sectors TEXT NOT NULL,
                total_in_scope INTEGER NOT NULL,
                total_scored INTEGER NOT NULL,
                results_json TEXT NOT NULL
            )
            """
        )
        existing = {row[1] for row in conn.execute("PRAGMA table_info(scan_runs)")}
        for name, col_type in _ADDED_COLUMNS.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE scan_runs ADD COLUMN {name} {col_type}")


def _records_json(df: pd.DataFrame) -> str:
    if df is None or df.empty:
        return "[]"
    return df.to_json(orient="records", force_ascii=False)


def save_scan_run(
    scan_id: str,
    scan_type: str,
    created_at: str,
    selected_sectors: list[str],
    total_in_scope: int,
    results_df: pd.DataFrame,
    disqualified_df: pd.DataFrame,
    unavailable_df: pd.DataFrame,
    config: dict[str, Any],
) -> None:
    excluded = {
        "disqualified": json.loads(_records_json(disqualified_df)),
        "unavailable": json.loads(_records_json(unavailable_df)),
    }
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO scan_runs (
                scan_id, scan_type, created_at, selected_sectors,
                total_in_scope, total_scored, results_json,
                total_disqualified, total_unavailable, excluded_json, config_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                scan_id,
                scan_type,
                created_at,
                json.dumps(selected_sectors),
                int(total_in_scope),
                int(len(results_df)),
                _records_json(results_df),
                int(len(disqualified_df)),
                int(len(unavailable_df)),
                json.dumps(excluded, ensure_ascii=False),
                json.dumps(config),
            ),
        )


def delete_scan_run(scan_id: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM scan_runs WHERE scan_id = ?", (scan_id,))


def list_scan_runs(limit: int = 200) -> pd.DataFrame:
    query = """
        SELECT
            scan_id, scan_type, created_at, selected_sectors,
            total_in_scope, total_scored, total_disqualified, total_unavailable
        FROM scan_runs
        ORDER BY created_at DESC
        LIMIT ?
    """
    with _connect() as conn:
        df = pd.read_sql_query(query, conn, params=[limit])
    if df.empty:
        return df

    def _sector_count(raw: str) -> int | None:
        try:
            return len(json.loads(raw))
        except Exception:
            return None

    df["sector_count"] = df["selected_sectors"].apply(_sector_count)
    return df


def _loads(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


def load_scan_results(scan_id: str) -> pd.DataFrame:
    with _connect() as conn:
        row = conn.execute(
            "SELECT results_json FROM scan_runs WHERE scan_id = ?",
            (scan_id,),
        ).fetchone()
    records = _loads(row[0], []) if row else []
    return pd.DataFrame(records) if records else pd.DataFrame()


def get_scan_run(scan_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT
                scan_id, scan_type, created_at, selected_sectors,
                total_in_scope, total_scored, total_disqualified,
                total_unavailable, excluded_json, config_json
            FROM scan_runs
            WHERE scan_id = ?
            """,
            (scan_id,),
        ).fetchone()
    if not row:
        return None

    excluded = _loads(row[8], {})
    return {
        "scan_id": row[0],
        "scan_type": row[1],
        "created_at": row[2],
        "selected_sectors": _loads(row[3], []),
        "total_in_scope": row[4],
        "total_scored": row[5],
        # None for scans saved before these were recorded.
        "total_disqualified": row[6],
        "total_unavailable": row[7],
        "disqualified": pd.DataFrame(excluded.get("disqualified", [])),
        "unavailable": pd.DataFrame(excluded.get("unavailable", [])),
        "config": _loads(row[9], None),
        "is_legacy": row[8] is None,
    }
