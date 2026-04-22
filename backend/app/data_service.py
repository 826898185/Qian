from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
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

    # previous day is weak, core1 is a small bullish candle
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

    # consecutive 1/2/3 closes above core1 close
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


def _generate_symbol_data(symbol: str, periods: int = 260, seed: int = 42) -> pd.DataFrame:
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


class DataService:
    def __init__(self) -> None:
        symbols = ["600519.SH", "000858.SZ", "300750.SZ", "601318.SH", "002594.SZ"]
        self._data: dict[str, pd.DataFrame] = {}
        for idx, symbol in enumerate(symbols):
            self._data[symbol] = _generate_symbol_data(symbol, seed=42 + idx * 9)

    def list_symbols(self) -> list[str]:
        return list(self._data.keys())

    def get_ohlcv(self, symbol: str) -> pd.DataFrame:
        if symbol not in self._data:
            raise KeyError(f"Symbol not found: {symbol}")
        return self._data[symbol].copy()

    def get_patterns(self, symbol: str, cfg: FactorConfig) -> pd.DataFrame:
        df = self.get_ohlcv(symbol)
        return detect_k13_patterns(df, cfg)

    def get_latest_risk(self, symbol: str, cfg: FactorConfig) -> dict[str, Any]:
        price_df = self.get_ohlcv(symbol)
        patterns = self.get_patterns(symbol, cfg)
        latest_pattern = patterns.iloc[-1] if not patterns.empty else None
        return latest_risk_signal(price_df, latest_pattern)

    def scan_latest_signals(self, cfg: FactorConfig) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for symbol in self.list_symbols():
            patterns = self.get_patterns(symbol, cfg)
            if patterns.empty:
                continue

            latest = patterns.iloc[-1].to_dict()
            risk = self.get_latest_risk(symbol, cfg)
            latest["symbol"] = symbol
            latest["risk_level"] = risk["level"]
            latest["risk_message"] = risk["message"]
            result.append(latest)

        result.sort(key=lambda row: row["score"], reverse=True)
        return result

    @staticmethod
    def config_to_json(cfg: FactorConfig) -> dict[str, Any]:
        return asdict(cfg)
