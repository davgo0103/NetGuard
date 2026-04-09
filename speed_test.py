"""
網速偵測模組
使用 speedtest.net 最近伺服器測量實際下載速度。
"""

import io
import logging
import os
import sys
import time
import urllib.request

logger = logging.getLogger("NetGuard")


def _patch_stdio():
    """windowed exe 模式下 sys.stdout/stderr 為 None，補上 devnull。"""
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")


def measure_download_speed(timeout: int = 60) -> float | None:
    """使用 speedtest-cli 測量下載速度，回傳 Mbps，失敗回傳 None。"""
    _patch_stdio()
    try:
        import speedtest
        st = speedtest.Speedtest()
        st.get_best_server()
        download_bps = st.download()  # bits per second
        mbps = download_bps / 1_000_000
        server = st.best.get("sponsor", "未知")
        city = st.best.get("name", "")
        logger.info(f"測速: {mbps:.2f} Mbps (伺服器: {server} - {city})")
        return mbps
    except Exception as e:
        logger.warning(f"speedtest-cli 測速失敗: {e}")
        return None


def quick_connectivity_check() -> bool:
    """快速檢查網路是否可用（不測速）。"""
    test_hosts = [
        "http://www.google.com",
        "http://www.msftconnecttest.com/connecttest.txt",
        "http://www.baidu.com",
    ]
    for host in test_hosts:
        try:
            req = urllib.request.Request(host, headers={"User-Agent": "NetGuard/1.0"})
            urllib.request.urlopen(req, timeout=5)
            return True
        except Exception:
            continue
    return False


class SpeedMonitor:
    """持續監控網速的類別。"""

    def __init__(self, threshold_mbps: float = 10.0, check_interval: int = 180):
        self.threshold_mbps = threshold_mbps
        self.check_interval = check_interval
        self.last_speed: float | None = None
        self.last_check_time: float = 0
        self.history: list[tuple[float, float]] = []  # (timestamp, speed_mbps)
        self.max_history = 50

    def check_speed(self) -> tuple[float | None, bool]:
        """執行一次測速。
        回傳 (速度Mbps或None, 是否低於閾值)。
        """
        speed = measure_download_speed()
        self.last_check_time = time.time()
        self.last_speed = speed

        if speed is not None:
            self.history.append((time.time(), speed))
            if len(self.history) > self.max_history:
                self.history = self.history[-self.max_history:]

        is_slow = speed is not None and speed < self.threshold_mbps
        if is_slow:
            logger.warning(f"網速低於閾值: {speed:.2f} Mbps < {self.threshold_mbps} Mbps")
        return speed, is_slow

    def get_average_speed(self, last_n: int = 5) -> float | None:
        """取得最近 N 次測速的平均值。"""
        recent = self.history[-last_n:]
        if not recent:
            return None
        return sum(s for _, s in recent) / len(recent)

    def get_status_text(self) -> str:
        """取得目前狀態的文字描述。"""
        if self.last_speed is None:
            return "尚未測速"
        status = f"目前: {self.last_speed:.1f} Mbps"
        avg = self.get_average_speed()
        if avg is not None:
            status += f" | 平均: {avg:.1f} Mbps"
        status += f" | 閾值: {self.threshold_mbps} Mbps"
        return status
