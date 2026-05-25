import json
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_FILE = str(DATA_DIR / "scan_history.db")


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


def save_scan_run(
    scan_id: str,
    scan_type: str,
    created_at: str,
    selected_sectors: list[str],
    total_in_scope: int,
    total_scored: int,
    results_df: pd.DataFrame,
) -> None:
    records = results_df.to_dict(orient="records")
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO scan_runs (
                scan_id, scan_type, created_at, selected_sectors,
                total_in_scope, total_scored, results_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                scan_id,
                scan_type,
                created_at,
                json.dumps(selected_sectors),
                int(total_in_scope),
                int(total_scored),
                json.dumps(records),
            ),
        )


def list_scan_runs(limit: int = 200) -> pd.DataFrame:
    query = """
        SELECT
            scan_id, scan_type, created_at, selected_sectors,
            total_in_scope, total_scored
        FROM scan_runs
        ORDER BY created_at DESC
        LIMIT ?
    """
    with _connect() as conn:
        df = pd.read_sql_query(query, conn, params=[limit])
    if df.empty:
        return df

    def _sector_count(raw: str) -> int:
        try:
            return len(json.loads(raw))
        except Exception:
            return 0

    df["sector_count"] = df["selected_sectors"].apply(_sector_count)
    return df


def load_scan_results(scan_id: str) -> pd.DataFrame:
    with _connect() as conn:
        row = conn.execute(
            "SELECT results_json FROM scan_runs WHERE scan_id = ?",
            (scan_id,),
        ).fetchone()
    if not row:
        return pd.DataFrame()
    try:
        records = json.loads(row[0])
    except Exception:
        records = []
    if not records:
        return pd.DataFrame()
    return pd.DataFrame(records)


def get_scan_run(scan_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT
                scan_id, scan_type, created_at, selected_sectors,
                total_in_scope, total_scored
            FROM scan_runs
            WHERE scan_id = ?
            """,
            (scan_id,),
        ).fetchone()
    if not row:
        return None

    sectors = []
    try:
        sectors = json.loads(row[3])
    except Exception:
        pass

    return {
        "scan_id": row[0],
        "scan_type": row[1],
        "created_at": row[2],
        "selected_sectors": sectors,
        "total_in_scope": row[4],
        "total_scored": row[5],
    }
