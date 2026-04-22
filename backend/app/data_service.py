from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

from .factor_engine import FactorConfig, detect_k13_patterns, latest_risk_signal


def _inject_k13_pattern(df: pd.DataFrame, core1_idx: int) -> pd.DataFrame:
    """Inject a bullish 1+3 pattern to make demo data deterministic."""
    d = df.copy()
    if core1_idx < 2 or core1_idx + 5 >= len(d):
        return d

    prev_idx = core1_idx - 1
    i1, i2, i3 = core1_idx + 1, core1_idx + 2, core1_idx + 3

    prev_close = float(d.loc[prev_idx, "close"])
    d.loc[prev_idx, "open"] = round(prev_close * 1.01, 2)
    d.loc[prev_idx, "close"] = round(prev_close * 0.99, 2)
    d.loc[prev_idx, "high"] = round(max(d.loc[prev_idx, "open"], d.loc[prev_idx, "close"]) * 1.01, 2)
    d.loc[prev_idx, "low"] = round(min(d.loc[prev_idx, "open"], d.loc[prev_idx, "close"]) * 0.99, 2)

    c1_open = round(prev_close * 0.995, 2)
    c1_close = round(prev_close * 1.01, 2)
    d.loc[core1_idx, "open"] = c1_open
    d.loc[core1_idx, "close"] = c1_close
    d.loc[core1_idx, "high"] = round(c1_close * 1.01, 2)
    d.loc[core1_idx, "low"] = round(c1_open * 0.995, 2)

    close1 = round(c1_close * 1.02, 2)
    close2 = round(c1_close * 1.03, 2)
    close3 = round(c1_close * 1.05, 2)

    d.loc[i1, "open"] = round(c1_close * 1.005, 2)
    d.loc[i1, "close"] = close1
    d.loc[i1, "high"] = round(close1 * 1.01, 2)
    d.loc[i1, "low"] = round(min(d.loc[i1, "open"], close1) * 0.997, 2)

    d.loc[i2, "open"] = round(close1 * 1.001, 2)
    d.loc[i2, "close"] = close2
    d.loc[i2, "high"] = round(close2 * 1.01, 2)
    d.loc[i2, "low"] = round(min(d.loc[i2, "open"], close2) * 0.997, 2)

    d.loc[i3, "open"] = round(close2 * 1.002, 2)
    d.loc[i3, "close"] = close3
    d.loc[i3, "high"] = round(close3 * 1.01, 2)
    d.loc[i3, "low"] = round(min(d.loc[i3, "open"], close3) * 0.998, 2)

    return d


def _generate_symbol_data(periods: int = 260, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(end=datetime.today().date(), periods=periods)

    base_price = rng.uniform(8, 80)
    drift = rng.uniform(0.0002, 0.0012)
    noise = rng.normal(0, 0.02, periods)
    close = [base_price]
    for i in range(1, periods):
        close.append(max(2.0, close[-1] * (1 + drift + noise[i])))
    close = np.array(close)

    open_ = close * (1 + rng.normal(0, 0.006, periods))
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0.01, 0.004, periods)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0.01, 0.004, periods)))
    volume = rng.integers(8_000_000, 80_000_000, periods)

    df = pd.DataFrame(
        {
            "date": dates.strftime("%Y-%m-%d"),
            "open": np.round(open_, 2),
            "high": np.round(high, 2),
            "low": np.round(low, 2),
            "close": np.round(close, 2),
            "volume": volume.astype(int),
        }
    )
    return _inject_k13_pattern(df, core1_idx=120)


class BaseDataService:
    source: str = "base"

    def list_symbols(self) -> list[str]:
        raise NotImplementedError

    def get_ohlcv(self, symbol: str, lookback: int = 260) -> pd.DataFrame:
        raise NotImplementedError

    def get_patterns(self, symbol: str, cfg: FactorConfig, lookback: int = 260) -> pd.DataFrame:
        df = self.get_ohlcv(symbol=symbol, lookback=lookback)
        return detect_k13_patterns(df, cfg)

    def get_latest_risk(self, symbol: str, cfg: FactorConfig, lookback: int = 260) -> dict[str, Any]:
        price_df = self.get_ohlcv(symbol=symbol, lookback=lookback)
        patterns = detect_k13_patterns(price_df, cfg)
        latest_pattern = patterns.iloc[-1] if not patterns.empty else None
        return latest_risk_signal(price_df, latest_pattern)

    def scan_latest_signals(self, cfg: FactorConfig, lookback: int = 260) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for symbol in self.list_symbols():
            try:
                df = self.get_ohlcv(symbol=symbol, lookback=lookback)
            except Exception:
                continue

            patterns = detect_k13_patterns(df, cfg)
            if patterns.empty:
                continue

            latest = patterns.iloc[-1].to_dict()
            risk = latest_risk_signal(df, latest_pattern=patterns.iloc[-1])
            latest["symbol"] = symbol
            latest["risk_level"] = risk["level"]
            latest["risk_message"] = risk["message"]
            result.append(latest)

        result.sort(key=lambda row: row["score"], reverse=True)
        return result


class DemoDataService(BaseDataService):
    source = "demo"

    def __init__(self) -> None:
        symbols = ["600519.SH", "000858.SZ", "300750.SZ", "601318.SH", "002594.SZ"]
        self._data: dict[str, pd.DataFrame] = {}
        for idx, symbol in enumerate(symbols):
            self._data[symbol] = _generate_symbol_data(seed=42 + idx * 9)

    def list_symbols(self) -> list[str]:
        return list(self._data.keys())

    def get_ohlcv(self, symbol: str, lookback: int = 260) -> pd.DataFrame:
        if symbol not in self._data:
            raise KeyError(f"Symbol not found: {symbol}")
        df = self._data[symbol].copy()
        if lookback > 0:
            df = df.tail(lookback).reset_index(drop=True)
        return df


class TushareDataService(BaseDataService):
    source = "tushare"

    def __init__(self, token: str, symbols: list[str] | None = None, scan_limit: int = 60, default_lookback: int = 260) -> None:
        if not token:
            raise ValueError("K13_DATA_SOURCE=tushare 时必须提供 TUSHARE_TOKEN。")

        try:
            import tushare as ts
        except ImportError as exc:
            raise RuntimeError("未安装 tushare，请先执行 pip install -r backend/requirements.txt") from exc

        self._pro = ts.pro_api(token)
        self._default_lookback = max(60, int(default_lookback))
        self._scan_limit = max(1, int(scan_limit))
        self._validate_token()
        self._symbols = symbols if symbols else self._load_default_symbols()
        if not self._symbols:
            raise RuntimeError("Tushare 股票池为空，请设置 K13_SYMBOLS 或检查 token 权限。")

    def _validate_token(self) -> None:
        """Fail fast with clear message when token is invalid."""
        today = datetime.today().strftime("%Y%m%d")
        try:
            _ = self._pro.trade_cal(exchange="", start_date=today, end_date=today)
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"Tushare 鉴权失败，请检查 TUSHARE_TOKEN：{exc}") from exc

    def _load_default_symbols(self) -> list[str]:
        df = self._pro.stock_basic(
            exchange="",
            list_status="L",
            fields="ts_code,name,list_date",
        )
        if df is None or df.empty:
            return []
        df = df.sort_values("ts_code")
        return df["ts_code"].head(self._scan_limit).tolist()

    def list_symbols(self) -> list[str]:
        return list(self._symbols)

    def get_ohlcv(self, symbol: str, lookback: int = 260) -> pd.DataFrame:
        lookback_days = max(30, int(lookback or self._default_lookback))
        end_dt = datetime.today().date()
        start_dt = end_dt - timedelta(days=lookback_days * 2)

        raw = self._pro.daily(
            ts_code=symbol,
            start_date=start_dt.strftime("%Y%m%d"),
            end_date=end_dt.strftime("%Y%m%d"),
            fields="ts_code,trade_date,open,high,low,close,vol",
        )
        if raw is None or raw.empty:
            raise KeyError(f"Symbol not found or no data: {symbol}")

        raw = raw.sort_values("trade_date").reset_index(drop=True)
        raw = raw.rename(columns={"trade_date": "date", "vol": "volume"})
        raw["date"] = pd.to_datetime(raw["date"], format="%Y%m%d").dt.strftime("%Y-%m-%d")
        raw["volume"] = (pd.to_numeric(raw["volume"], errors="coerce").fillna(0) * 100).astype(int)

        for col in ("open", "high", "low", "close"):
            raw[col] = pd.to_numeric(raw[col], errors="coerce")

        df = raw[["date", "open", "high", "low", "close", "volume"]].dropna().reset_index(drop=True)
        if lookback_days > 0:
            df = df.tail(lookback_days).reset_index(drop=True)
        return df


def _env_symbols() -> list[str]:
    raw = os.getenv("K13_SYMBOLS", "")
    if not raw.strip():
        return []
    symbols = [item.strip().upper() for item in raw.split(",") if item.strip()]
    return list(dict.fromkeys(symbols))


def create_data_service() -> BaseDataService:
    source = os.getenv("K13_DATA_SOURCE", "demo").strip().lower()
    if source == "demo":
        return DemoDataService()

    if source == "tushare":
        token = os.getenv("TUSHARE_TOKEN", "").strip()
        scan_limit = int(os.getenv("K13_SCAN_LIMIT", "60"))
        lookback = int(os.getenv("K13_LOOKBACK_DAYS", "260"))
        return TushareDataService(
            token=token,
            symbols=_env_symbols(),
            scan_limit=scan_limit,
            default_lookback=lookback,
        )

    raise ValueError(f"Unsupported K13_DATA_SOURCE: {source}. 可选: demo / tushare")
