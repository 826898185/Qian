from __future__ import annotations

import os
import re
from typing import Any

import requests


class EastmoneyWatchlistService:
    """Fetch and normalize watchlist symbols from Eastmoney Miaoxiang API."""

    SELFSELECT_API_URL = "https://mkapi2.dfcfs.com/finskillshub/api/claw/self-select/get"
    LEGACY_SCREEN_API_URL = "https://mkapi2.dfcfs.com/finskillshub/api/claw/stock-screen"

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

        headers = {"Content-Type": "application/json", "apikey": self.apikey}

        # 1) 优先使用 mx_selfselect（账户自选股管理）接口
        try:
            selfselect_resp = requests.post(
                self.SELFSELECT_API_URL,
                headers=headers,
                timeout=20,
            )
            selfselect_resp.raise_for_status()
            selfselect_data = selfselect_resp.json()
        except Exception as exc:  # noqa: BLE001
            selfselect_data = {
                "status": -1,
                "message": f"self-select/get 请求失败: {exc}",
            }

        if int(selfselect_data.get("status", -1)) == 0:
            node = selfselect_data.get("data", {})
            result = node.get("allResults", {}).get("result", {})
            rows = result.get("dataList", [])
            symbols = self._extract_codes_from_rows(rows)
            meta = {
                "enabled": True,
                "source": "mx_selfselect",
                "watchlist_count": len(symbols),
                "security_count": int(node.get("securityCount", 0) or 0),
                "message": "ok",
            }
            return symbols, meta

        # 2) 回退到旧的 stock-screen 自然语言选股接口
        payload = {"keyword": self.keyword, "pageNo": 1, "pageSize": self.page_size}
        try:
            legacy_resp = requests.post(
                self.LEGACY_SCREEN_API_URL,
                headers=headers,
                json=payload,
                timeout=20,
            )
            legacy_resp.raise_for_status()
            legacy_data = legacy_resp.json()
        except Exception as exc:  # noqa: BLE001
            return set(), {
                "enabled": True,
                "source": "legacy_stock_screen",
                "message": f"东方财富接口请求失败: {exc}",
            }

        if not bool(legacy_data.get("success", False)) or int(legacy_data.get("status", -1)) != 0:
            return set(), {
                "enabled": True,
                "source": "legacy_stock_screen",
                "message": str(legacy_data.get("message", "东方财富接口返回异常")),
                "status": legacy_data.get("status"),
                "selfselect_status": selfselect_data.get("status"),
                "selfselect_message": selfselect_data.get("message"),
            }

        node = legacy_data.get("data", {}).get("data", {})
        result = node.get("allResults", {}).get("result", {})
        rows = result.get("dataList", [])
        symbols = self._extract_codes_from_rows(rows)

        meta = {
            "enabled": True,
            "source": "legacy_stock_screen",
            "keyword": self.keyword,
            "watchlist_count": len(symbols),
            "security_count": int(node.get("securityCount", 0) or 0),
            "message": "ok",
            "selfselect_status": selfselect_data.get("status"),
            "selfselect_message": selfselect_data.get("message"),
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
