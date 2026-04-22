from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


def _db_path() -> str:
    configured = os.getenv("K13_DB_PATH", "").strip()
    if configured:
        return configured
    return str(Path(__file__).resolve().parents[1] / "data" / "k13.db")


class K13Storage:
    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or _db_path()
        db_dir = Path(self.db_path).resolve().parent
        db_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS scan_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_ts TEXT NOT NULL,
                    trade_date TEXT,
                    data_source TEXT NOT NULL,
                    lookback_days INTEGER NOT NULL,
                    universe_size INTEGER NOT NULL,
                    signal_count INTEGER NOT NULL,
                    meta_json TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS signal_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    symbol TEXT NOT NULL,
                    core1_date TEXT,
                    three_date TEXT,
                    days_from_low INTEGER,
                    score REAL,
                    risk_level TEXT,
                    risk_message TEXT,
                    core1_open REAL,
                    core1_close REAL,
                    core1_low REAL,
                    three_open REAL,
                    three_close REAL,
                    FOREIGN KEY(run_id) REFERENCES scan_runs(id)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_signal_run_id ON signal_snapshots(run_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_signal_symbol ON signal_snapshots(symbol)"
            )

    def save_scan_run(
        self,
        *,
        data_source: str,
        lookback_days: int,
        universe_size: int,
        signal_count: int,
        trade_date: str | None,
        meta_json: str,
    ) -> int:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO scan_runs (run_ts, trade_date, data_source, lookback_days, universe_size, signal_count, meta_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (now, trade_date, data_source, lookback_days, universe_size, signal_count, meta_json),
            )
            return int(cur.lastrowid)

    def save_signal_snapshots(self, run_id: int, signals: list[dict[str, Any]]) -> int:
        if not signals:
            return 0

        rows = []
        for row in signals:
            rows.append(
                (
                    run_id,
                    row.get("symbol"),
                    row.get("core1_date"),
                    row.get("three_date"),
                    row.get("days_from_low"),
                    row.get("score"),
                    row.get("risk_level"),
                    row.get("risk_message"),
                    row.get("core1_open"),
                    row.get("core1_close"),
                    row.get("core1_low"),
                    row.get("three_open"),
                    row.get("three_close"),
                )
            )

        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO signal_snapshots (
                    run_id, symbol, core1_date, three_date, days_from_low, score,
                    risk_level, risk_message, core1_open, core1_close, core1_low, three_open, three_close
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
        return len(rows)

    def list_recent_runs(self, limit: int = 30) -> list[dict[str, Any]]:
        with self._connect() as conn:
            cur = conn.execute(
                """
                SELECT id, run_ts, trade_date, data_source, lookback_days, universe_size, signal_count
                FROM scan_runs
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            )
            return [dict(row) for row in cur.fetchall()]

    def get_run_detail(self, run_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            run = conn.execute(
                """
                SELECT id, run_ts, trade_date, data_source, lookback_days, universe_size, signal_count, meta_json
                FROM scan_runs
                WHERE id = ?
                """,
                (run_id,),
            ).fetchone()
            if run is None:
                return None

            run_dict = dict(run)
            meta_raw = run_dict.get("meta_json")
            try:
                run_dict["meta"] = json.loads(meta_raw) if meta_raw else {}
            except json.JSONDecodeError:
                run_dict["meta"] = {"raw": meta_raw}
            run_dict.pop("meta_json", None)

            signals = conn.execute(
                """
                SELECT symbol, core1_date, three_date, days_from_low, score, risk_level, risk_message,
                       core1_open, core1_close, core1_low, three_open, three_close
                FROM signal_snapshots
                WHERE run_id = ?
                ORDER BY score DESC
                """,
                (run_id,),
            ).fetchall()

            return {"run": run_dict, "signals": [dict(row) for row in signals]}
