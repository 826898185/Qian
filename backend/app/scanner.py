from __future__ import annotations

import json
from typing import Any

from .factor_engine import FactorConfig
from .storage import K13Storage


def execute_scan_job(
    *,
    data_service: Any,
    cfg: FactorConfig,
    storage: K13Storage,
    lookback: int,
) -> dict[str, Any]:
    meta = data_service.metadata() if hasattr(data_service, "metadata") else {"source": data_service.source}
    signals = data_service.scan_latest_signals(cfg, lookback=lookback)

    trade_date = meta.get("latest_trade_date")
    run_id = storage.save_scan_run(
        data_source=str(meta.get("source", data_service.source)),
        lookback_days=int(lookback),
        universe_size=int(meta.get("universe_size", len(data_service.list_symbols()))),
        signal_count=len(signals),
        trade_date=trade_date,
        meta_json=json.dumps(meta, ensure_ascii=False),
    )
    saved_count = storage.save_signal_snapshots(run_id, signals)

    return {
        "run_id": run_id,
        "saved_signals": saved_count,
        "meta": meta,
        "signal_count": len(signals),
        "signals": signals,
    }
