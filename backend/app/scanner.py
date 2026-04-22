from __future__ import annotations

import json
from typing import Any

from .factor_engine import FactorConfig
from .storage import K13Storage
from .watchlist_service import annotate_signals_with_watchlist


def execute_scan_job(
    *,
    data_service: Any,
    cfg: FactorConfig,
    storage: K13Storage,
    lookback: int,
    watchlist_symbols: set[str] | None = None,
    watchlist_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    meta = data_service.metadata() if hasattr(data_service, "metadata") else {"source": data_service.source}
    signals = data_service.scan_latest_signals(cfg, lookback=lookback)
    wl_symbols = watchlist_symbols or set()
    wl_meta = watchlist_meta or {}
    signals = annotate_signals_with_watchlist(signals, wl_symbols)
    watchlist_count_in_signals = sum(1 for row in signals if bool(row.get("is_watchlist")))
    meta["watchlist"] = {
        **wl_meta,
        "matched_in_signals": watchlist_count_in_signals,
    }

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
