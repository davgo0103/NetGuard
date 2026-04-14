"""
網速偵測模組
使用台灣 speedtest 伺服器的小檔測速，每次約消耗 0.2~5 MB。
"""

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


# 台灣 speedtest 伺服器
_SPEED_SERVERS = [
    ("http://nt-speed.kbro.com.tw:8080/speedtest", "凱擘 台南"),
    ("http://phc-speed.twmbroadband.com:8080/speedtest", "台灣大 彰化"),
    ("http://tp1-speed.twnoc.net:8080/speedtest", "TWNOC 台北"),
]


def _download(url: str, timeout: int) -> tuple[int, float] | None:
    """下載檔案，回傳 (bytes, seconds) 或 None。"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        start = time.perf_counter()
        resp = urllib.request.urlopen(req, timeout=timeout)
        total = 0
        while True:
            chunk = resp.read(65536)
            if not chunk:
                break
            total += len(chunk)
        elapsed = time.perf_counter() - start
        if total < 10_000 or elapsed <= 0:
            return None
        return total, elapsed
    except Exception:
        return None


def measure_download_speed(timeout: int = 15) -> float | None:
    """
    兩階段測速：
    1. 先下載小檔（~250KB）快速判斷速度
    2. 若速度 > 10 Mbps，再下載大檔（~4.5MB）取得更準確結果
    每次消耗約 0.25 ~ 5 MB。
    """
    _patch_stdio()

    for base, name in _SPEED_SERVERS:
        # 第一階段：小檔快速探測（~250KB）
        small_url = f"{base}/random350x350.jpg"
        result = _download(small_url, timeout=8)
        if not result:
            logger.debug(f"伺服器 {name} 無回應，嘗試下一台")
            continue

        total_bytes, elapsed = result
        mbps = (total_bytes * 8) / (elapsed * 1_000_000)

        # 若速度很低（被限速），小檔結果就夠用了
        if mbps < 10:
            logger.info(f"測速: {mbps:.2f} Mbps ({total_bytes/1000:.0f} KB / {elapsed:.1f}s) [{name}]")
            return mbps

        # 第二階段：速度正常，用大檔測更準確
        big_url = f"{base}/random1500x1500.jpg"
        result2 = _download(big_url, timeout=timeout)
        if result2:
            total_bytes, elapsed = result2
            mbps = (total_bytes * 8) / (elapsed * 1_000_000)

        logger.info(f"測速: {mbps:.2f} Mbps ({total_bytes/1000000:.1f} MB / {elapsed:.1f}s) [{name}]")
        return mbps

    logger.warning("所有測速伺服器皆失敗")
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
            urllib.request.urlopen(req, timeout=3)
            return True
        except Exception:
            continue
    return False


def measure_system_bandwidth(interval: float = 2.0) -> float:
    """
    測量系統目前的網路下載頻寬（Mbps），取 interval 秒內的平均值。
    用於判斷使用者是否正在大量下載，避免測速時誤判為限速。
    """
    try:
        import psutil
        c1 = psutil.net_io_counters()
        time.sleep(interval)
        c2 = psutil.net_io_counters()
        recv_mbps = (c2.bytes_recv - c1.bytes_recv) * 8 / (interval * 1_000_000)
        logger.debug(f"系統目前下載頻寬: {recv_mbps:.2f} Mbps")
        return recv_mbps
    except Exception as e:
        logger.debug(f"讀取系統頻寬失敗: {e}")
        return 0.0


class SpeedMonitor:
    """持續監控網速的類別。"""

    # 系統頻寬高於此值時視為「使用者正在下載」，跳過測速（Mbps）
    BUSY_THRESHOLD_MBPS = 5.0

    def __init__(self, threshold_mbps: float = 10.0, check_interval: int = 180):
        self.threshold_mbps = threshold_mbps
        self.check_interval = check_interval
        self.last_speed: float | None = None
        self.last_check_time: float = 0
        self.history: list[tuple[float, float]] = []
        self.max_history = 50
        self.skipped_busy: bool = False  # 上次是否因使用者下載而跳過

    def is_system_busy(self) -> tuple[bool, float]:
        """檢查系統是否正在大量使用網路。回傳 (is_busy, current_mbps)。"""
        bandwidth = measure_system_bandwidth(interval=2.0)
        return bandwidth >= self.BUSY_THRESHOLD_MBPS, bandwidth

    def check_speed(self) -> tuple[float | None, bool]:
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
        recent = self.history[-last_n:]
        if not recent:
            return None
        return sum(s for _, s in recent) / len(recent)

    def get_status_text(self) -> str:
        if self.last_speed is None:
            return "尚未測速"
        status = f"目前: {self.last_speed:.1f} Mbps"
        avg = self.get_average_speed()
        if avg is not None:
            status += f" | 平均: {avg:.1f} Mbps"
        status += f" | 閾值: {self.threshold_mbps} Mbps"
        return status
