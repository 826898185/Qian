from __future__ import annotations

from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .data_service import create_data_service
from .factor_engine import FactorConfig, detect_k13_patterns, latest_risk_signal

load_dotenv()

app = FastAPI(title="K13 Strategy API", version="0.1.0")
CFG = FactorConfig()
DATA = create_data_service()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "data_source": DATA.source}


@app.get("/api/symbols")
def symbols() -> dict[str, list[str]]:
    return {"symbols": DATA.list_symbols()}


@app.get("/api/signals")
def signals(lookback: int = 260) -> dict[str, Any]:
    return {
        "config": CFG.to_dict(),
        "signals": DATA.scan_latest_signals(CFG, lookback=lookback),
    }


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
