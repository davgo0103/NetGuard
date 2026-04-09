"""
NetGuard 設定畫面
使用 tkinter 提供 MAC 清單管理與參數設定的 GUI。
"""

import json
import re
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path


def normalize_mac(mac: str) -> str:
    """將各種 MAC 格式統一為 12 碼大寫無分隔（如 0C9D9218AAC4）。"""
    cleaned = re.sub(r"[^0-9A-Fa-f]", "", mac)
    return cleaned.upper()


def format_mac(mac: str) -> str:
    """格式化為 XX-XX-XX-XX-XX-XX 顯示用。"""
    mac = normalize_mac(mac)
    if len(mac) != 12:
        return mac
    return "-".join(mac[i:i+2] for i in range(0, 12, 2))


def is_valid_mac(mac: str) -> bool:
    cleaned = normalize_mac(mac)
    return len(cleaned) == 12


class SettingsWindow:
    def __init__(self, config_path: Path, on_save=None):
        self.config_path = config_path
        self.on_save = on_save
        self.cfg = self._load_config()

        self.root = tk.Tk()
        self.root.title("NetGuard 設定")
        self.root.geometry("520x580")
        self.root.resizable(False, False)

        # 置中顯示
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() - 520) // 2
        y = (self.root.winfo_screenheight() - 580) // 2
        self.root.geometry(f"+{x}+{y}")

        self._build_ui()

    def _load_config(self) -> dict:
        defaults = {
            "speed_threshold_mbps": 50,
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
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    user_cfg = json.load(f)
                defaults.update(user_cfg)
            except Exception:
                pass
        return defaults

    def _save_config(self):
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self.cfg, f, indent=4, ensure_ascii=False)

    def _build_ui(self):
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # ── Tab 1: MAC 位址管理 ──
        mac_frame = ttk.Frame(notebook, padding=10)
        notebook.add(mac_frame, text=" MAC 位址管理 ")

        ttk.Label(mac_frame, text="已註冊的 MAC 位址清單：", font=("", 10)).pack(anchor=tk.W)
        ttk.Label(mac_frame, text="（僅限組織已註冊、可上網的 MAC）", foreground="gray").pack(anchor=tk.W)

        # MAC 清單
        list_frame = ttk.Frame(mac_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(5, 0))

        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.mac_listbox = tk.Listbox(
            list_frame, height=10, font=("Consolas", 11),
            yscrollcommand=scrollbar.set, selectmode=tk.SINGLE
        )
        self.mac_listbox.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.mac_listbox.yview)

        for mac in self.cfg.get("mac_list", []):
            self.mac_listbox.insert(tk.END, format_mac(mac))

        # 新增 MAC 輸入
        add_frame = ttk.Frame(mac_frame)
        add_frame.pack(fill=tk.X, pady=(10, 0))

        ttk.Label(add_frame, text="新增 MAC：").pack(side=tk.LEFT)
        self.mac_entry = ttk.Entry(add_frame, width=20, font=("Consolas", 11))
        self.mac_entry.pack(side=tk.LEFT, padx=5)
        self.mac_entry.bind("<Return>", lambda e: self._add_mac())

        ttk.Button(add_frame, text="新增", command=self._add_mac, width=6).pack(side=tk.LEFT)
        ttk.Button(add_frame, text="刪除選取", command=self._remove_mac, width=8).pack(side=tk.LEFT, padx=5)

        ttk.Label(mac_frame, text="格式: XX-XX-XX-XX-XX-XX 或 XXXXXXXXXXXX", foreground="gray").pack(anchor=tk.W, pady=(5, 0))

        # ── Tab 2: 監控設定 ──
        monitor_frame = ttk.Frame(notebook, padding=10)
        notebook.add(monitor_frame, text=" 監控設定 ")

        settings = [
            ("降速判定閾值 (Mbps)：", "speed_threshold_mbps", 50),
            ("測速間隔 (秒)：", "check_interval_seconds", 120),
            ("切換冷卻時間 (秒)：", "cooldown_seconds", 60),
            ("網卡名稱 (auto=自動)：", "adapter_name", "auto"),
        ]

        self.setting_vars = {}
        for i, (label, key, default) in enumerate(settings):
            ttk.Label(monitor_frame, text=label).grid(row=i, column=0, sticky=tk.W, pady=8)
            var = tk.StringVar(value=str(self.cfg.get(key, default)))
            self.setting_vars[key] = var
            entry = ttk.Entry(monitor_frame, textvariable=var, width=15, font=("Consolas", 10))
            entry.grid(row=i, column=1, sticky=tk.W, padx=10, pady=8)

        # 說明文字
        hints = [
            ("", ""),
            ("", ""),
            ("", ""),
            ("", ""),
            ("", ""),
            ("提示：", ""),
            ("• 正常網速 500~1000 Mbps，降速後 < 5 Mbps", ""),
            ("• 建議閾值設 50 Mbps，可有效判斷降速", ""),
            ("• 測速間隔建議 60~300 秒", ""),
        ]

        for i, (text, _) in enumerate(hints):
            if text:
                ttk.Label(monitor_frame, text=text, foreground="gray").grid(
                    row=len(settings) + i, column=0, columnspan=2, sticky=tk.W, pady=1
                )

        # 開機自動啟動
        self.autostart_var = tk.BooleanVar(value=self.cfg.get("auto_start", True))
        ttk.Checkbutton(
            monitor_frame, text="開機自動啟動", variable=self.autostart_var
        ).grid(row=len(settings), column=0, columnspan=2, sticky=tk.W, pady=(15, 0))

        # ── 底部按鈕 ──
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(fill=tk.X, padx=10, pady=(0, 10))

        ttk.Button(btn_frame, text="儲存並啟動", command=self._save_and_close).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="取消", command=self.root.destroy).pack(side=tk.RIGHT)

    def _add_mac(self):
        raw = self.mac_entry.get().strip()
        if not raw:
            return

        if not is_valid_mac(raw):
            messagebox.showerror("格式錯誤", f"無效的 MAC 位址：{raw}\n\n請輸入 12 位十六進位字元\n例如：0C-9D-92-18-AA-C4")
            return

        normalized = normalize_mac(raw)
        # 檢查重複
        existing = [normalize_mac(self.mac_listbox.get(i)) for i in range(self.mac_listbox.size())]
        if normalized in existing:
            messagebox.showwarning("重複", "此 MAC 位址已在清單中")
            return

        self.mac_listbox.insert(tk.END, format_mac(normalized))
        self.mac_entry.delete(0, tk.END)

    def _remove_mac(self):
        selection = self.mac_listbox.curselection()
        if not selection:
            messagebox.showinfo("提示", "請先選取要刪除的 MAC 位址")
            return
        self.mac_listbox.delete(selection[0])

    def _save_and_close(self):
        # 收集 MAC 清單
        mac_list = []
        for i in range(self.mac_listbox.size()):
            mac_list.append(normalize_mac(self.mac_listbox.get(i)))

        if not mac_list:
            messagebox.showerror("錯誤", "請至少新增一個 MAC 位址")
            return

        # 收集設定值
        self.cfg["mac_list"] = mac_list
        self.cfg["auto_start"] = self.autostart_var.get()

        for key, var in self.setting_vars.items():
            val = var.get().strip()
            if key == "adapter_name":
                self.cfg[key] = val
            else:
                try:
                    self.cfg[key] = int(val) if "." not in val else float(val)
                except ValueError:
                    messagebox.showerror("格式錯誤", f"「{key}」必須是數字")
                    return

        self._save_config()
        self.root.destroy()

        if self.on_save:
            self.on_save(self.cfg)

    def run(self):
        self.root.mainloop()
        return self.cfg


def open_settings(config_path: Path, on_save=None) -> dict | None:
    """開啟設定視窗，回傳儲存後的設定（取消則回傳 None）。"""
    window = SettingsWindow(config_path, on_save)
    window.run()
    return window.cfg


if __name__ == "__main__":
    # 獨立測試
    cfg = open_settings(Path(__file__).parent / "config.json")
    if cfg:
        print(f"MAC 清單: {cfg.get('mac_list', [])}")
