from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd


@dataclass
class FactorConfig:
    max_confirm_days: int = 9
    min_confirm_days: int = 4
    small_body_pct: float = 0.015
    big_body_pct: float = 0.06
    doji_body_pct: float = 0.002

    def to_dict(self) -> dict:
        return asdict(self)


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d["body"] = (d["close"] - d["open"]).abs()
    d["body_pct"] = d["body"] / d["close"].replace(0, np.nan)
    d["bull"] = d["close"] >= d["open"]
    d["bear"] = d["close"] < d["open"]
    d["doji"] = d["body_pct"] <= 0.002
    d["tr"] = np.maximum(
        d["high"] - d["low"],
        np.maximum(
            (d["high"] - d["close"].shift(1)).abs(),
            (d["low"] - d["close"].shift(1)).abs(),
        ),
    )
    d["atr14"] = d["tr"].rolling(14, min_periods=5).mean()
    d["vol_ma20"] = d["volume"].rolling(20, min_periods=5).mean()
    return d


def _is_fake_bear_newhigh(d: pd.DataFrame, idx: int) -> bool:
    if idx <= 0:
        return False
    is_fake_bear = d.loc[idx, "close"] < d.loc[idx, "open"]
    close_new_high = d.loc[idx, "close"] >= d.loc[:idx, "close"].max()
    return bool(is_fake_bear and close_new_high)


def _core1_candidates(d: pd.DataFrame, cfg: FactorConfig) -> list[int]:
    candidates: list[int] = []
    for i in range(1, len(d) - 3):
        prev_is_bear = bool(d.loc[i - 1, "bear"])
        this_is_bull = bool(d.loc[i, "bull"])
        body_ok = d.loc[i, "body_pct"] <= cfg.big_body_pct
        doji_ok = bool(d.loc[i, "doji"])

        # 上涨始于阳线（前一日偏弱，当前日偏强），十字星也可作为参考1
        if (prev_is_bear and this_is_bull and body_ok) or doji_ok:
            candidates.append(i)
    return candidates


def detect_k13_patterns(df: pd.DataFrame, cfg: FactorConfig) -> pd.DataFrame:
    d = add_features(df).reset_index(drop=True)
    if d.empty:
        return pd.DataFrame()

    patterns: list[dict] = []

    for core1 in _core1_candidates(d, cfg):
        core1_close = d.loc[core1, "close"]
        core1_open = d.loc[core1, "open"]
        core1_low = d.loc[core1, "low"]

        found = False
        end_i3 = min(core1 + cfg.max_confirm_days, len(d) - 1)
        start_i3 = core1 + 3
        if start_i3 > end_i3:
            continue

        for i3 in range(start_i3, end_i3 + 1):
            i1 = i3 - 2
            i2 = i3 - 1

            # 1/2/3 必须连续，且收盘都在核心1收盘之上
            if not (
                d.loc[i1, "close"] > core1_close
                and d.loc[i2, "close"] > core1_close
                and d.loc[i3, "close"] > core1_close
            ):
                continue

            stage_max_close = d.loc[core1:i3, "close"].max()
            cond_a = bool(d.loc[i3, "bull"] and d.loc[i3, "close"] >= stage_max_close)

            fake_days = [k for k in (i1, i2) if _is_fake_bear_newhigh(d, k)]
            cond_d = False
            if fake_days:
                cond_d = bool(d.loc[i3, "close"] > d.loc[fake_days, "open"].max())

            if not (cond_a or cond_d):
                continue

            # 如果盘中跌破核心1最低点，只有在“3”收盘创阶段新高时保留核心1有效性
            broke_core1_low = bool((d.loc[core1 + 1 : i3, "low"] < core1_low).any())
            if broke_core1_low and d.loc[i3, "close"] < stage_max_close:
                continue

            local_low_idx = int(d.loc[core1:i3, "low"].idxmin())
            days_from_low = i3 - local_low_idx + 1
            if not (cfg.min_confirm_days <= days_from_low <= cfg.max_confirm_days):
                continue

            body_strength = d.loc[core1, "body"] / (d.loc[core1, "atr14"] + 1e-9)
            momentum = (d.loc[i3, "close"] - core1_close) / (d.loc[core1, "atr14"] + 1e-9)
            vol_ratio = d.loc[i3, "volume"] / (d.loc[i3, "vol_ma20"] + 1e-9)
            time_penalty = (days_from_low - cfg.min_confirm_days) / (
                cfg.max_confirm_days - cfg.min_confirm_days + 1e-9
            )

            score = (
                40 * np.tanh(body_strength / 2.0)
                + 35 * np.tanh(momentum / 2.0)
                + 15 * np.tanh(vol_ratio - 1.0)
                - 10 * np.clip(time_penalty, 0, 1)
            )

            patterns.append(
                {
                    "core1_idx": int(core1),
                    "one_idx": int(i1),
                    "two_idx": int(i2),
                    "three_idx": int(i3),
                    "core1_date": str(d.loc[core1, "date"]),
                    "three_date": str(d.loc[i3, "date"]),
                    "core1_open": float(core1_open),
                    "core1_close": float(core1_close),
                    "core1_low": float(core1_low),
                    "three_open": float(d.loc[i3, "open"]),
                    "three_close": float(d.loc[i3, "close"]),
                    "days_from_low": int(days_from_low),
                    "score": float(score),
                }
            )
            found = True
            break

        # 超过确认期未命中，自动失效并寻找下一核心1
        if found:
            continue

    return pd.DataFrame(patterns)


def latest_risk_signal(df: pd.DataFrame, latest_pattern: pd.Series | None) -> dict:
    if latest_pattern is None:
        return {"level": "NO_PATTERN", "message": "暂无已确认1+3结构"}

    last = df.iloc[-1]
    c1_open = float(latest_pattern["core1_open"])
    c1_close = float(latest_pattern["core1_close"])
    c1_low = float(latest_pattern["core1_low"])
    three_open = float(latest_pattern["three_open"])
    three_close = float(latest_pattern["three_close"])
    close = float(last["close"])

    if close < c1_low:
        return {"level": "SELL_HARD", "message": "收盘跌破核心1最低点，下跌趋势形成"}
    if close < min(c1_open, c1_close):
        return {"level": "SELL", "message": "收盘跌破核心1实体支撑，趋势改变风险高"}
    if close < three_open:
        return {"level": "REDUCE", "message": "收盘跌破3开盘价，建议减仓观察"}
    if close < three_close:
        return {"level": "WARN", "message": "回落至3收盘价附近，注意短线承接"}
    return {"level": "HOLD", "message": "仍处于1+3结构支撑之上"}
