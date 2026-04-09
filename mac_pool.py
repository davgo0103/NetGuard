"""
MAC 池管理模組
管理固定的 MAC 位址清單，追蹤每日使用狀態。
跨日後自動重置，可重新使用。
"""

import json
import logging
import time
from datetime import date, datetime
from pathlib import Path

logger = logging.getLogger("NetGuard")


class MacPool:
    """管理固定 MAC 清單的輪替與每日重置。

    每個 MAC 記錄包含：
    - mac: MAC 位址
    - throttled_date: 被限速的日期 (YYYY-MM-DD)，跨日後自動失效
    """

    def __init__(self, pool_path: Path, mac_list: list[str]):
        self.pool_path = pool_path
        self.mac_list = mac_list
        self.records: dict[str, dict] = {}
        self._load()

    def _load(self):
        if self.pool_path.exists():
            try:
                with open(self.pool_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.records = {r["mac"]: r for r in data if r["mac"] in self.mac_list}
                logger.info(f"已載入 MAC 池記錄")
            except Exception as e:
                logger.warning(f"載入 MAC 池失敗: {e}")
                self.records = {}

        # 確保所有 MAC 都有記錄
        for mac in self.mac_list:
            if mac not in self.records:
                self.records[mac] = {
                    "mac": mac,
                    "throttled_date": None,
                }

    def _save(self):
        try:
            with open(self.pool_path, "w", encoding="utf-8") as f:
                json.dump(list(self.records.values()), f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"儲存 MAC 池失敗: {e}")

    def _today(self) -> str:
        return date.today().isoformat()

    def is_throttled(self, mac: str) -> bool:
        """檢查 MAC 今天是否已被限速。"""
        rec = self.records.get(mac)
        if not rec:
            return False
        return rec.get("throttled_date") == self._today()

    def get_available(self) -> list[str]:
        """取得今天還沒被限速的 MAC 清單。"""
        return [mac for mac in self.mac_list if not self.is_throttled(mac)]

    def get_next_mac(self, current_mac: str = "") -> str | None:
        """取得下一個可用的 MAC。
        跳過目前正在用的和已被限速的。
        回傳 None 表示今天所有 MAC 都已用完。
        """
        available = self.get_available()

        # 排除目前正在用的
        candidates = [m for m in available if m != current_mac]

        if candidates:
            return candidates[0]

        # 如果排除自己後沒有了，但自己還可用（不應該發生，因為降速時會標記）
        if available:
            return available[0]

        return None

    def mark_throttled(self, mac: str):
        """標記 MAC 為今日已限速。"""
        if mac in self.records:
            self.records[mac]["throttled_date"] = self._today()
            self._save()
            logger.info(f"MAC {self._format(mac)} 已標記為今日限速")

    def daily_cleanup(self):
        """跨日重置：過去的限速標記自動失效（不需要主動清除）。"""
        today = self._today()
        reset_count = sum(
            1 for r in self.records.values()
            if r.get("throttled_date") and r["throttled_date"] != today
        )
        if reset_count > 0:
            logger.info(f"跨日重置：{reset_count} 個 MAC 已恢復可用")

    def get_available_count(self) -> int:
        return len(self.get_available())

    def get_throttled_count(self) -> int:
        return len(self.mac_list) - self.get_available_count()

    def get_summary(self) -> str:
        avail = self.get_available_count()
        total = len(self.mac_list)
        return f"MAC: {avail}/{total} 可用"

    @staticmethod
    def _format(mac: str) -> str:
        """格式化 MAC 為 XX-XX-XX-XX-XX-XX。"""
        mac = mac.upper().replace("-", "").replace(":", "")
        return "-".join(mac[i:i+2] for i in range(0, 12, 2))
