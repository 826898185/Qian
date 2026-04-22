from __future__ import annotations

import os
import re
from typing import Any

import requests


class EastmoneyWatchlistService:
    """Fetch and normalize watchlist symbols from Eastmoney Miaoxiang API."""

    API_URL = "https://mkapi2.dfcfs.com/finskillshub/api/claw/stock-screen"

    def __init__(self, apikey: str | None = None) -> None:
        self.apikey = (apikey or os.getenv("EASTMONEY_APIKEY", "")).strip()
        self.keyword = os.getenv("EASTMONEY_WATCHLIST_KEYWORD", "我的自选股").strip() or "我的自选股"
        self.page_size = max(20, int(os.getenv("EASTMONEY_WATCHLIST_PAGE_SIZE", "500")))

    @property
    def enabled(self) -> bool:
        return bool(self.apikey)

    @staticmethod
    def _normalize_symbol(raw: Any) -> str | None:
        if raw is None:
            return None
        value = str(raw).strip().upper()
        if not value:
            return None

        matched = re.match(r"^(\d{6})\.(SH|SZ|BJ)$", value)
        if matched:
            return value

        if re.match(r"^\d{6}$", value):
            if value.startswith(("4", "8")):
                return f"{value}.BJ"
            if value.startswith(("5", "6", "9")):
                return f"{value}.SH"
            return f"{value}.SZ"

        return None

    @staticmethod
    def _extract_codes_from_rows(rows: Any) -> set[str]:
        if not isinstance(rows, list):
            return set()

        code_keys = (
            "CODE",
            "SECURITY_CODE",
            "TS_CODE",
            "SYMBOL",
            "code",
            "securityCode",
            "symbol",
            "股票代码",
            "代码",
        )
        result: set[str] = set()
        for row in rows:
            if not isinstance(row, dict):
                continue
            found = None
            for key in code_keys:
                if key in row:
                    found = row.get(key)
                    break
            normalized = EastmoneyWatchlistService._normalize_symbol(found)
            if normalized:
                result.add(normalized)
        return result

    def fetch_watchlist_symbols(self) -> tuple[set[str], dict[str, Any]]:
        if not self.enabled:
            return set(), {"enabled": False, "message": "EASTMONEY_APIKEY 未配置"}

        payload = {"keyword": self.keyword, "pageNo": 1, "pageSize": self.page_size}
        headers = {"Content-Type": "application/json", "apikey": self.apikey}

        try:
            resp = requests.post(self.API_URL, headers=headers, json=payload, timeout=20)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            return set(), {"enabled": True, "message": f"东方财富接口请求失败: {exc}"}

        if not bool(data.get("success", False)) or int(data.get("status", -1)) != 0:
            return set(), {
                "enabled": True,
                "message": str(data.get("message", "东方财富接口返回异常")),
                "status": data.get("status"),
            }

        node = data.get("data", {}).get("data", {})
        result = node.get("allResults", {}).get("result", {})
        rows = result.get("dataList", [])
        symbols = self._extract_codes_from_rows(rows)

        meta = {
            "enabled": True,
            "keyword": self.keyword,
            "watchlist_count": len(symbols),
            "security_count": int(node.get("securityCount", 0) or 0),
            "message": "ok",
        }
        return symbols, meta


def annotate_signals_with_watchlist(
    signals: list[dict[str, Any]],
    watchlist_symbols: set[str],
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for row in signals:
        copied = dict(row)
        symbol = str(copied.get("symbol", "")).strip().upper()
        copied["is_watchlist"] = symbol in watchlist_symbols if symbol else False
        enriched.append(copied)
    return enriched
