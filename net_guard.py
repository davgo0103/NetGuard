"""
NetGuard - 網路守衛
自動偵測網速，降速時自動切換 MAC 位址。
針對每日 MAC 流量限制的網路環境設計。
Windows 系統托盤常駐程式。
"""

import ctypes
import json
import logging
import logging.handlers
import os
import sys
import threading
import time
import winreg
from datetime import date, datetime

from pathlib import Path

# 取得程式所在目錄（支援打包後的 exe）
if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).parent
else:
    APP_DIR = Path(__file__).parent

CONFIG_PATH = APP_DIR / "config.json"
ICON_SIZE = 64

# ── 載入設定 ──────────────────────────────────────────────

def load_config() -> dict:
    defaults = {
        "speed_threshold_mbps": 10,
        "check_interval_seconds": 120,
        "cooldown_seconds": 60,
        "adapter_name": "auto",
        "log_file": "net_guard.log",
        "max_log_size_mb": 5,
        "auto_start": True,
        "daily_reset_hour": 0,
        "mac_list": [],
        "mac_pool_file": "mac_pool.json",
    }
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                user_cfg = json.load(f)
            defaults.update(user_cfg)
        except Exception:
            pass
    return defaults


def save_config(cfg: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4, ensure_ascii=False)


# ── 日誌 ─────────────────────────────────────────────────

def setup_logging(cfg: dict) -> logging.Logger:
    log_path = APP_DIR / cfg["log_file"]
    logger = logging.getLogger("NetGuard")
    logger.setLevel(logging.DEBUG)

    handler = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=cfg["max_log_size_mb"] * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(handler)

    # 也輸出到 console（除錯用）
    if not getattr(sys, "frozen", False):
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        logger.addHandler(console)

    return logger


# ── 開機啟動 ──────────────────────────────────────────────

STARTUP_REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
STARTUP_KEY_NAME = "NetGuard"


def is_autostart_enabled() -> bool:
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_REG_PATH, 0, winreg.KEY_READ)
        winreg.QueryValueEx(key, STARTUP_KEY_NAME)
        winreg.CloseKey(key)
        return True
    except FileNotFoundError:
        return False


def set_autostart(enable: bool):
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_REG_PATH, 0, winreg.KEY_SET_VALUE)
        if enable:
            if getattr(sys, "frozen", False):
                exe_path = sys.executable
            else:
                exe_path = f'"{sys.executable}" "{Path(__file__).resolve()}"'
            winreg.SetValueEx(key, STARTUP_KEY_NAME, 0, winreg.REG_SZ, exe_path)
        else:
            try:
                winreg.DeleteValue(key, STARTUP_KEY_NAME)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except OSError as e:
        logging.getLogger("NetGuard").error(f"設定開機啟動失敗: {e}")


# ── 圖示 & 彈窗（使用 ui_theme）────────────────────────────

def create_icon_image(color: str = "green"):
    from ui_theme import create_tray_icon
    return create_tray_icon(color, ICON_SIZE)


def show_alert(title: str, message: str, alert_type: str = "warning", detail: str = ""):
    from ui_theme import show_alert as _show
    _show(title, message, alert_type, detail)


# ── 主控制器 ──────────────────────────────────────────────

class NetGuardController:
    """核心控制器：管理監控迴圈、MAC 切換邏輯、MAC 池。"""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.logger = logging.getLogger("NetGuard")
        self.running = False
        self.monitoring = True
        self.monitor_thread: threading.Thread | None = None
        self.last_switch_time: float = 0
        self.switch_count: int = 0
        self.current_mac: str = ""
        self.current_date: str = date.today().isoformat()
        self.pool_exhausted: bool = False
        self.status_text: str = "啟動中..."
        self.icon_color: str = "gray"
        self._tray = None
        # 連續網路失敗計數（連線失敗 / 測速失敗），達門檻後觸發 MAC 切換
        self.fail_count: int = 0
        self.max_fails_before_switch: int = 2

        from speed_test import SpeedMonitor
        from mac_pool import MacPool

        self.speed_monitor = SpeedMonitor(
            threshold_mbps=cfg["speed_threshold_mbps"],
            check_interval=cfg["check_interval_seconds"],
        )
        self.mac_pool = MacPool(APP_DIR / cfg["mac_pool_file"], cfg["mac_list"])

    def start(self):
        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        self.logger.info("NetGuard 已啟動")

    def stop(self):
        self.running = False
        self.logger.info("NetGuard 已停止")

    def toggle_monitoring(self):
        self.monitoring = not self.monitoring
        state = "啟用" if self.monitoring else "暫停"
        self.logger.info(f"監控已{state}")
        self.status_text = f"監控已{state}"
        self._update_tray()

    def manual_switch(self):
        """手動觸發 MAC 切換。"""
        self.logger.info("手動觸發 MAC 切換")
        self._do_mac_switch()

    def _check_daily_reset(self):
        """檢查是否跨日，跨日則重置 MAC 池。"""
        today = date.today().isoformat()
        if today != self.current_date:
            self.logger.info(f"跨日偵測: {self.current_date} -> {today}")
            self.current_date = today
            self.mac_pool.daily_cleanup()
            self.switch_count = 0
            self.pool_exhausted = False
            self.logger.info("MAC 池已重置，恢復監控")

    def _monitor_loop(self):
        # 啟動後等幾秒讓網路穩定
        time.sleep(10)

        while self.running:
            if not self.monitoring:
                self.icon_color = "gray"
                self.status_text = "監控已暫停"
                self._update_tray()
                time.sleep(5)
                continue

            # 檢查跨日重置
            self._check_daily_reset()

            # MAC 池用完，停止監控等跨日
            if self.pool_exhausted:
                time.sleep(30)
                continue

            # 先確認網路可用
            from speed_test import quick_connectivity_check
            if not quick_connectivity_check():
                self.fail_count += 1
                self.icon_color = "red"
                self.status_text = f"無網路連線 ({self.fail_count}/{self.max_fails_before_switch})"
                self._update_tray()
                self.logger.warning(
                    f"網路不通 (第 {self.fail_count}/{self.max_fails_before_switch} 次)"
                )
                if self.fail_count >= self.max_fails_before_switch:
                    self._handle_network_failure(f"連續 {self.fail_count} 次無法連線")
                else:
                    time.sleep(30)
                continue

            # 測速
            self.status_text = "測速中..."
            self.icon_color = "yellow"
            self._update_tray()

            speed, is_slow = self.speed_monitor.check_speed()

            if speed is None:
                self.fail_count += 1
                self.icon_color = "red"
                self.status_text = f"測速失敗 ({self.fail_count}/{self.max_fails_before_switch})"
                self._update_tray()
                self.logger.warning(
                    f"測速失敗 (第 {self.fail_count}/{self.max_fails_before_switch} 次)"
                )
                if self.fail_count >= self.max_fails_before_switch:
                    self._handle_network_failure(f"連續 {self.fail_count} 次測速失敗")
                else:
                    time.sleep(30)
                continue

            # 測速成功，重置失敗計數
            self.fail_count = 0

            if is_slow:
                # 降速：標記目前 MAC 為已限速，切換新 MAC
                if self.current_mac:
                    self.mac_pool.mark_throttled(self.current_mac)

                mac_display = self.mac_pool._format(self.current_mac) if self.current_mac else "未知"
                show_alert(
                    "NetGuard - 偵測到降速",
                    f"目前網速: {speed:.1f} Mbps\n"
                    f"低於閾值 {self.cfg['speed_threshold_mbps']} Mbps",
                    alert_type="warning",
                    detail=f"目前 MAC: {mac_display}  |  {self.mac_pool.get_summary()}\n正在自動切換 MAC 位址..."
                )

                # 檢查冷卻時間
                elapsed = time.time() - self.last_switch_time
                if elapsed >= self.cfg["cooldown_seconds"]:
                    pool_info = self.mac_pool.get_summary()
                    self.status_text = f"降速 {speed:.1f} Mbps | {pool_info}"
                    self.icon_color = "yellow"
                    self._update_tray()
                    self._do_mac_switch()
                else:
                    remaining = int(self.cfg["cooldown_seconds"] - elapsed)
                    self.status_text = f"降速 {speed:.1f} Mbps | 冷卻中 ({remaining}s)"
                    self.icon_color = "yellow"
                    self._update_tray()
            else:
                pool_info = self.mac_pool.get_summary()
                self.icon_color = "green"
                self.status_text = f"正常 {speed:.1f} Mbps | {pool_info}"
                self._update_tray()

            time.sleep(self.cfg["check_interval_seconds"])

    def _handle_network_failure(self, reason: str):
        """連續網路失敗時觸發：標記目前 MAC 為限速，切換下一個。"""
        if self.current_mac:
            self.mac_pool.mark_throttled(self.current_mac)

        mac_display = self.mac_pool._format(self.current_mac) if self.current_mac else "未知"
        self.logger.warning(f"{reason}，嘗試切換 MAC")
        show_alert(
            "NetGuard - 網路失敗",
            f"{reason}\n正在切換 MAC 位址...",
            alert_type="warning",
            detail=f"目前 MAC: {mac_display}  |  {self.mac_pool.get_summary()}"
        )

        self.fail_count = 0
        self._do_mac_switch()

    def _do_mac_switch(self):
        from mac_changer import set_mac_address, find_active_adapter, restart_adapter

        # 從固定 MAC 池取得下一個可用的
        next_mac = self.mac_pool.get_next_mac(self.current_mac)

        if not next_mac:
            total = len(self.cfg["mac_list"])
            self.logger.warning(f"今日所有 MAC 皆已限速 (0/{total})，暫停監控等跨日")
            self.pool_exhausted = True
            self.status_text = "今日 MAC 已全部用完，等待跨日重置"
            self.icon_color = "red"
            self._update_tray()
            show_alert(
                "NetGuard - MAC 位址已用完",
                f"今日 {total} 個 MAC 位址皆已達流量限制",
                alert_type="error",
                detail="目前網速將維持在限速狀態，跨日（00:00）後將自動重置"
            )
            return

        adapter = find_active_adapter(self.cfg["adapter_name"])
        if not adapter:
            self.logger.error("找不到可用的網路卡")
            self.status_text = "找不到網路卡"
            self.icon_color = "red"
            self._update_tray()
            return

        old_mac = self.current_mac or adapter.get("current_mac", "原始")
        fmt = self.mac_pool._format

        self.logger.info(f"切換 MAC: {fmt(old_mac) if old_mac else '原始'} -> {fmt(next_mac)}")

        if not set_mac_address(adapter, next_mac):
            self.status_text = "MAC 切換失敗（寫入登錄檔）"
            self.icon_color = "red"
            self._update_tray()
            return

        if not restart_adapter(adapter):
            self.status_text = "MAC 切換失敗（重啟網卡）"
            self.icon_color = "red"
            self._update_tray()
            return

        # 切換成功，等待網路穩定後驗證
        self.current_mac = next_mac
        self.switch_count += 1
        self.last_switch_time = time.time()

        fmt_mac = fmt(next_mac)
        self.status_text = f"已切換至 {fmt_mac}，驗證中..."
        self.icon_color = "yellow"
        self.logger.info(f"MAC 切換成功 (今日第{self.switch_count}次)，等待驗證")
        self._update_tray()

        # 等網路重新連線
        time.sleep(5)

        # 驗證新 MAC 是否可用
        verify_speed, verify_slow = self.speed_monitor.check_speed()

        if verify_speed is None:
            # 測速失敗，可能網路還沒恢復，先當作成功
            pool_info = self.mac_pool.get_summary()
            self.status_text = f"已切換至 {fmt_mac}（驗證失敗）| {pool_info}"
            self.icon_color = "yellow"
            self._update_tray()
            self.logger.warning(f"切換後驗證測速失敗，保留 {fmt_mac}")
            show_alert(
                "NetGuard - MAC 已切換",
                f"已切換至: {fmt_mac}\n驗證測速失敗，請留意網速",
                alert_type="warning",
                detail=self.mac_pool.get_summary()
            )
        elif verify_slow:
            # 新 MAC 也是慢的，標記為限速並繼續切換下一個
            self.logger.warning(f"{fmt_mac} 驗證失敗: {verify_speed:.1f} Mbps，標記限速")
            self.mac_pool.mark_throttled(next_mac)
            show_alert(
                "NetGuard - MAC 驗證失敗",
                f"{fmt_mac} 速度僅 {verify_speed:.1f} Mbps\n已標記為限速，自動切換下一個",
                alert_type="warning",
                detail=self.mac_pool.get_summary()
            )
            # 遞迴切換下一個（冷卻時間已更新，不會無限迴圈因為 MAC 會用完）
            self._do_mac_switch()
        else:
            # 驗證通過
            pool_info = self.mac_pool.get_summary()
            self.status_text = f"已切換至 {fmt_mac} ({verify_speed:.0f} Mbps) | {pool_info}"
            self.icon_color = "green"
            self._update_tray()
            self.logger.info(f"{fmt_mac} 驗證通過: {verify_speed:.1f} Mbps")
            show_alert(
                "NetGuard - MAC 已切換",
                f"已切換至: {fmt_mac}\n"
                f"驗證速度: {verify_speed:.1f} Mbps ✓",
                alert_type="success",
                detail=pool_info
            )

    def _update_tray(self):
        if self._tray:
            try:
                self._tray.icon = create_icon_image(self.icon_color)
                self._tray.title = f"NetGuard - {self.status_text}"
            except Exception:
                pass


# ── 系統托盤 ──────────────────────────────────────────────

def run_tray(controller: NetGuardController):
    import pystray

    def on_toggle(icon, item):
        controller.toggle_monitoring()

    def on_manual_switch(icon, item):
        threading.Thread(target=controller.manual_switch, daemon=True).start()

    def on_restore_mac(icon, item):
        from mac_changer import restore_original_mac
        threading.Thread(
            target=lambda: restore_original_mac(controller.cfg["adapter_name"]),
            daemon=True,
        ).start()

    def on_toggle_autostart(icon, item):
        current = is_autostart_enabled()
        set_autostart(not current)

    def on_open_log(icon, item):
        log_path = APP_DIR / controller.cfg["log_file"]
        if log_path.exists():
            os.startfile(str(log_path))

    def on_open_settings(icon, item):
        """開啟 GUI 設定畫面。"""
        def _open():
            from settings_gui import open_settings
            new_cfg = open_settings(CONFIG_PATH)
            if new_cfg and new_cfg.get("mac_list"):
                controller.cfg = new_cfg
                controller.mac_pool = __import__("mac_pool").MacPool(
                    APP_DIR / new_cfg["mac_pool_file"], new_cfg["mac_list"]
                )
                controller.speed_monitor.threshold_mbps = new_cfg["speed_threshold_mbps"]
                controller.speed_monitor.check_interval = new_cfg["check_interval_seconds"]
                controller.logger.info("設定已更新")
        threading.Thread(target=_open, daemon=True).start()

    def on_open_config(icon, item):
        if CONFIG_PATH.exists():
            os.startfile(str(CONFIG_PATH))

    def on_quit(icon, item):
        controller.stop()
        icon.stop()

    def get_monitoring_text(item):
        return "暫停監控" if controller.monitoring else "恢復監控"

    def get_autostart_checked(item):
        return is_autostart_enabled()

    def get_status_text(item):
        return controller.status_text

    def get_pool_text(item):
        return controller.mac_pool.get_summary()

    menu = pystray.Menu(
        pystray.MenuItem(get_status_text, None, enabled=False),
        pystray.MenuItem(get_pool_text, None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(get_monitoring_text, on_toggle),
        pystray.MenuItem("立即切換 MAC", on_manual_switch),
        pystray.MenuItem("恢復原始 MAC", on_restore_mac),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("開機自動啟動", on_toggle_autostart, checked=get_autostart_checked),
        pystray.MenuItem("設定", on_open_settings),
        pystray.MenuItem("開啟日誌", on_open_log),
        pystray.MenuItem("開啟設定檔 (JSON)", on_open_config),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("結束", on_quit),
    )

    icon = pystray.Icon(
        "NetGuard",
        icon=create_icon_image("gray"),
        title=f"NetGuard - {controller.status_text}",
        menu=menu,
    )

    controller._tray = icon

    # 設定開機啟動（首次執行時）
    if controller.cfg.get("auto_start") and not is_autostart_enabled():
        set_autostart(True)

    controller.start()
    icon.run()


# ── 入口 ─────────────────────────────────────────────────

def main():
    cfg = load_config()
    setup_logging(cfg)
    logger = logging.getLogger("NetGuard")

    # 檢查管理員權限
    try:
        if not ctypes.windll.shell32.IsUserAnAdmin():
            logger.warning("未以管理員身份執行，MAC 切換可能失敗")
            if getattr(sys, "frozen", False):
                ctypes.windll.shell32.ShellExecuteW(
                    None, "runas", sys.executable, "", None, 1
                )
            else:
                ctypes.windll.shell32.ShellExecuteW(
                    None, "runas", sys.executable, f'"{Path(__file__).resolve()}"', None, 1
                )
            sys.exit(0)
    except Exception as e:
        logger.warning(f"權限檢查失敗: {e}")

    # 首次執行或 MAC 清單為空：開啟設定畫面
    if not cfg.get("mac_list"):
        logger.info("MAC 清單為空，開啟設定畫面")
        from settings_gui import open_settings
        cfg = open_settings(CONFIG_PATH)
        if not cfg or not cfg.get("mac_list"):
            logger.info("使用者未設定 MAC，程式結束")
            return
        # 重新載入（settings_gui 已儲存）
        cfg = load_config()

    logger.info("=" * 40)
    logger.info("NetGuard 啟動")
    logger.info(f"MAC 清單: {len(cfg['mac_list'])} 個")
    logger.info(f"閾值: {cfg['speed_threshold_mbps']} Mbps")
    logger.info(f"間隔: {cfg['check_interval_seconds']}s")
    logger.info(f"冷卻: {cfg['cooldown_seconds']}s")
    logger.info("=" * 40)

    controller = NetGuardController(cfg)
    run_tray(controller)


if __name__ == "__main__":
    main()
