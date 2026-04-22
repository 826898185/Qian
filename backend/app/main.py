from __future__ import annotations

from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .data_service import create_data_service
from .factor_engine import FactorConfig, detect_k13_patterns, latest_risk_signal
from .scanner import execute_scan_job
from .storage import K13Storage

load_dotenv()

app = FastAPI(title="K13 Strategy API", version="0.1.0")
CFG = FactorConfig()
DATA = create_data_service()
STORE = K13Storage()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, Any]:
    meta = DATA.metadata() if hasattr(DATA, "metadata") else {"source": DATA.source}
    return {"status": "ok", "data_source": DATA.source, "meta": meta}


@app.get("/api/symbols")
def symbols() -> dict[str, list[str]]:
    return {"symbols": DATA.list_symbols()}


@app.get("/api/signals")
def signals(lookback: int = 260) -> dict[str, Any]:
    return {
        "config": CFG.to_dict(),
        "meta": DATA.metadata() if hasattr(DATA, "metadata") else {"source": DATA.source},
        "signals": DATA.scan_latest_signals(CFG, lookback=lookback),
    }


@app.post("/api/scans/run")
def run_scan(lookback: int = 260) -> dict[str, Any]:
    result = execute_scan_job(
        data_service=DATA,
        cfg=CFG,
        storage=STORE,
        lookback=lookback,
    )
    return result


@app.get("/api/scans")
def list_scans(limit: int = 30) -> dict[str, Any]:
    return {"runs": STORE.list_recent_runs(limit=limit)}


@app.get("/api/scans/{run_id}")
def scan_detail(run_id: int) -> dict[str, Any]:
    detail = STORE.get_run_detail(run_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"scan run not found: {run_id}")
    return detail


@app.get("/api/stocks/{symbol}/patterns")
def stock_patterns(symbol: str, lookback: int = 180) -> dict[str, Any]:
    try:
        df = DATA.get_ohlcv(symbol=symbol, lookback=lookback)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    patterns = detect_k13_patterns(df, CFG)
    return {"symbol": symbol, "candles": df.to_dict(orient="records"), "patterns": patterns.to_dict(orient="records")}


@app.get("/api/stocks/{symbol}/risk")
def stock_risk(symbol: str, lookback: int = 180) -> dict[str, Any]:
    try:
        df = DATA.get_ohlcv(symbol=symbol, lookback=lookback)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    patterns = detect_k13_patterns(df, CFG)
    latest = None if patterns.empty else patterns.sort_values("three_idx").iloc[-1]
    risk = latest_risk_signal(df, latest)
    return {"symbol": symbol, "risk": risk}


@app.post("/api/config")
def update_config(payload: dict[str, Any]) -> dict[str, Any]:
    global CFG
    try:
        merged = {**CFG.to_dict(), **payload}
        CFG = FactorConfig(**merged)
    except TypeError as exc:
        raise HTTPException(status_code=400, detail=f"配置参数错误: {exc}") from exc
    return {"config": CFG.to_dict()}
