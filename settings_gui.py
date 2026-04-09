"""
NetGuard 設定畫面 — CustomTkinter 現代化 UI。
"""

import json
import re
import sys
from pathlib import Path

import customtkinter as ctk
from PIL import Image

from ui_theme import (
    show_alert, font, mono,
    ACCENT, ACCENT_HI, GREEN, YELLOW, RED,
    BG_DARK, BG_BANNER, BG_CARD, BG_ROW, BG_ROW_SEL, BORDER,
    TEXT_WHITE, TEXT_PRIMARY, TEXT_DIM, TEXT_MUTED,
)

# 程式目錄
if getattr(sys, "frozen", False):
    _APP_DIR = Path(sys.executable).parent
else:
    _APP_DIR = Path(__file__).parent


def normalize_mac(mac: str) -> str:
    return re.sub(r"[^0-9A-Fa-f]", "", mac).upper()

def format_mac(mac: str) -> str:
    mac = normalize_mac(mac)
    if len(mac) != 12:
        return mac
    return "-".join(mac[i:i+2] for i in range(0, 12, 2))

def is_valid_mac(mac: str) -> bool:
    return len(normalize_mac(mac)) == 12


class SettingsWindow:
    def __init__(self, config_path: Path, on_save=None):
        self.config_path = config_path
        self.on_save = on_save
        self.cfg = self._load_config()
        self.saved = False

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.win = ctk.CTk()
        self.win.title("NetGuard")
        self.win.geometry("600x760")
        self.win.resizable(False, False)
        self.win.configure(fg_color=BG_DARK)

        # 視窗 icon
        logo_path = _APP_DIR / "logo.png"
        if logo_path.exists():
            try:
                from PIL import ImageTk
                icon = Image.open(logo_path).resize((32, 32), Image.LANCZOS)
                self._icon_ref = ImageTk.PhotoImage(icon)
                self.win.iconphoto(True, self._icon_ref)
            except Exception:
                pass

        # 置中
        self.win.update_idletasks()
        x = (self.win.winfo_screenwidth() - 600) // 2
        y = (self.win.winfo_screenheight() - 760) // 2
        self.win.geometry(f"+{x}+{y}")

        self._build()

    def _load_config(self) -> dict:
        d = {
            "speed_threshold_mbps": 10, "check_interval_seconds": 120,
            "cooldown_seconds": 60, "adapter_name": "auto",
            "log_file": "net_guard.log", "max_log_size_mb": 5,
            "auto_start": True, "daily_reset_hour": 0,
            "mac_list": [], "mac_pool_file": "mac_pool.json",
        }
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    d.update(json.load(f))
            except Exception:
                pass
        return d

    def _save_config(self):
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self.cfg, f, indent=4, ensure_ascii=False)

    # ── 建構 UI ──

    def _build(self):
        # Banner
        banner = ctk.CTkFrame(self.win, height=80, corner_radius=0, fg_color=BG_BANNER)
        banner.pack(fill="x")
        banner.pack_propagate(False)

        banner_content = ctk.CTkFrame(banner, fg_color="transparent")
        banner_content.pack(fill="both", expand=True, padx=28)

        # Logo
        logo_row = ctk.CTkFrame(banner_content, fg_color="transparent")
        logo_row.pack(fill="x", pady=(16, 0))

        logo_path = _APP_DIR / "logo.png"
        if logo_path.exists():
            try:
                logo_img = ctk.CTkImage(Image.open(logo_path), size=(48, 48))
                ctk.CTkLabel(logo_row, image=logo_img, text="").pack(side="left", padx=(0, 14))
            except Exception:
                pass

        text_frame = ctk.CTkFrame(logo_row, fg_color="transparent")
        text_frame.pack(side="left", fill="y")
        ctk.CTkLabel(text_frame, text="NetGuard",
                     font=font(22, "bold"),
                     text_color=ACCENT).pack(anchor="w")
        ctk.CTkLabel(text_frame, text="網路速度監控  ·  MAC 自動切換",
                     font=font(11),
                     text_color=TEXT_DIM).pack(anchor="w")

        # Accent 線
        ctk.CTkFrame(self.win, height=3, corner_radius=0, fg_color=ACCENT).pack(fill="x")

        # Tabview
        self.tabs = ctk.CTkTabview(self.win, corner_radius=8,
                                    fg_color=BG_DARK,
                                    segmented_button_fg_color=BG_BANNER,
                                    segmented_button_selected_color=ACCENT,
                                    segmented_button_unselected_color=BG_ROW)
        self.tabs.pack(fill="both", expand=True, padx=20, pady=(12, 0))

        tab_mac = self.tabs.add("\U0001F4E1  MAC 位址")
        tab_cfg = self.tabs.add("\u2699  監控設定")

        self._build_mac_tab(tab_mac)
        self._build_settings_tab(tab_cfg)

        # 底部按鈕
        footer = ctk.CTkFrame(self.win, height=64, corner_radius=0, fg_color=BG_BANNER)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)

        btn_row = ctk.CTkFrame(footer, fg_color="transparent")
        btn_row.pack(expand=True)

        ctk.CTkButton(btn_row, text="\u2714  儲存並啟動", width=180, height=40,
                      font=font(14, "bold"),
                      fg_color=ACCENT, hover_color=ACCENT_HI,
                      command=self._save_and_close).pack(side="right", padx=(12, 0))
        ctk.CTkButton(btn_row, text="取消", width=100, height=40,
                      font=font(13),
                      fg_color=BG_ROW, hover_color="#444a70",
                      command=self.win.destroy).pack(side="right")

    # ── MAC 分頁 ──

    def _build_mac_tab(self, parent):
        # 標題
        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.pack(fill="x", padx=12, pady=(8, 0))
        ctk.CTkLabel(header, text="\U0001F4E1  已註冊的 MAC 位址",
                     font=font(15, "bold"),
                     text_color=TEXT_WHITE).pack(anchor="w")
        ctk.CTkLabel(header, text="僅限組織已註冊、可正常上網的 MAC 位址",
                     font=font(11),
                     text_color=TEXT_DIM).pack(anchor="w", pady=(2, 0))

        # 列表區
        list_frame = ctk.CTkFrame(parent, corner_radius=8, fg_color=BG_CARD)
        list_frame.pack(fill="both", expand=True, padx=12, pady=(10, 0))

        # 列表頭
        list_header = ctk.CTkFrame(list_frame, fg_color="transparent", height=28)
        list_header.pack(fill="x", padx=16, pady=(10, 0))
        ctk.CTkLabel(list_header, text="MAC 位址", font=font(11),
                     text_color=TEXT_MUTED).pack(side="left")
        self.count_label = ctk.CTkLabel(list_header, text=f"{len(self.cfg.get('mac_list',[]))} 個",
                                         font=font(11), text_color=TEXT_MUTED)
        self.count_label.pack(side="right")

        # ScrollableFrame 顯示 MAC 列表
        self.mac_scroll = ctk.CTkScrollableFrame(list_frame, corner_radius=0,
                                                  fg_color="transparent")
        self.mac_scroll.pack(fill="both", expand=True, padx=8, pady=(4, 8))

        self.mac_rows: list[ctk.CTkFrame] = []
        for mac in self.cfg.get("mac_list", []):
            self._add_mac_row(format_mac(mac))

        # 輸入區
        input_frame = ctk.CTkFrame(parent, fg_color="transparent")
        input_frame.pack(fill="x", padx=12, pady=(12, 4))

        self.mac_entry = ctk.CTkEntry(input_frame, height=38,
                                       placeholder_text="輸入 MAC 位址，例如 0C-9D-92-18-AA-C4",
                                       font=mono(12),
                                       fg_color=BG_ROW, border_color=BORDER,
                                       text_color=TEXT_WHITE)
        self.mac_entry.pack(fill="x", pady=(0, 8))
        self.mac_entry.bind("<Return>", lambda e: self._add_mac())

        # 按鈕列
        btn_row = ctk.CTkFrame(input_frame, fg_color="transparent")
        btn_row.pack(fill="x")

        ctk.CTkButton(btn_row, text="\u2795  新增", width=140, height=36,
                      font=font(12, "bold"),
                      fg_color=ACCENT, hover_color=ACCENT_HI,
                      command=self._add_mac).pack(side="left")

        ctk.CTkButton(btn_row, text="\u2796  刪除選取", width=140, height=36,
                      font=font(12, "bold"),
                      fg_color="#3a1b1b", hover_color=RED,
                      text_color=RED,
                      command=self._remove_mac).pack(side="left", padx=(10, 0))

    def _add_mac_row(self, mac_text: str):
        """在清單中新增一筆 MAC。"""
        row = ctk.CTkFrame(self.mac_scroll, height=36, corner_radius=6,
                            fg_color=BG_ROW, cursor="hand2")
        row.pack(fill="x", pady=2)
        row.pack_propagate(False)

        lbl = ctk.CTkLabel(row, text=f"  \U0001F4CD  {mac_text}",
                            font=mono(13),
                            text_color=TEXT_PRIMARY, anchor="w")
        lbl.pack(fill="x", padx=12, pady=4)

        # 點擊選取
        row._selected = False
        def toggle(event=None):
            for r in self.mac_rows:
                r._selected = False
                r.configure(fg_color=BG_ROW)
            row._selected = True
            row.configure(fg_color=BG_ROW_SEL)

        row.bind("<Button-1>", toggle)
        lbl.bind("<Button-1>", toggle)

        self.mac_rows.append(row)

    # ── 設定分頁 ──

    def _build_settings_tab(self, parent):
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=4, pady=4)

        # 標題
        ctk.CTkLabel(scroll, text="\U0001F4CA  監控參數",
                     font=font(15, "bold"),
                     text_color=TEXT_WHITE).pack(anchor="w", padx=12, pady=(4, 10))

        settings = [
            ("\U0001F4C9", "降速閾值", "低於此速度觸發 MAC 切換", "speed_threshold_mbps", 10, "Mbps"),
            ("\u23F1\uFE0F",  "測速間隔", "每隔多久測一次速度", "check_interval_seconds", 120, "秒"),
            ("\u2744\uFE0F",  "冷卻時間", "兩次切換之間的最短間隔", "cooldown_seconds", 60, "秒"),
            ("\U0001F5A5\uFE0F", "網卡名稱", "auto = 自動偵測連線中的網卡", "adapter_name", "auto", ""),
        ]

        self.setting_entries = {}
        for icon_text, label, hint, key, default, unit in settings:
            card = ctk.CTkFrame(scroll, corner_radius=8, fg_color=BG_CARD)
            card.pack(fill="x", padx=12, pady=(0, 6))

            # 使用 grid 精確對齊
            inner = ctk.CTkFrame(card, fg_color="transparent")
            inner.pack(fill="x", padx=16, pady=12)
            inner.columnconfigure(1, weight=1)

            # 圖示（row 0-1, col 0）固定寬度，垂直置中
            ctk.CTkLabel(inner, text=icon_text, font=font(18), width=28,
                         text_color=ACCENT).grid(row=0, column=0, rowspan=2,
                                                  padx=(0, 8), sticky="w")

            # 標籤（row 0, col 1）靠左
            ctk.CTkLabel(inner, text=label, font=font(13, "bold"),
                         text_color=TEXT_WHITE).grid(row=0, column=1, sticky="w")

            # 提示（row 1, col 1）靠左
            ctk.CTkLabel(inner, text=hint, font=font(11),
                         text_color=TEXT_DIM).grid(row=1, column=1, sticky="w", pady=(2, 0))

            # 輸入框 + 單位（row 0-1, col 2）垂直置中靠右
            right = ctk.CTkFrame(inner, fg_color="transparent")
            right.grid(row=0, column=2, rowspan=2, sticky="e", padx=(12, 0))

            entry = ctk.CTkEntry(right, width=90, height=32, justify="center",
                                  font=mono(12),
                                  fg_color=BG_ROW, border_color=BORDER,
                                  text_color=TEXT_WHITE)
            entry.insert(0, str(self.cfg.get(key, default)))
            entry.pack(side="left", padx=(0, 4))
            self.setting_entries[key] = entry

            # 統一加上單位佔位，確保所有行對齊
            ctk.CTkLabel(right, text=unit if unit else "", font=font(11),
                         text_color=TEXT_DIM, width=36).pack(side="left")

        # 分隔
        ctk.CTkFrame(scroll, height=1, fg_color=BORDER).pack(fill="x", padx=12, pady=10)

        # 其他設定
        ctk.CTkLabel(scroll, text="\u2699  其他設定",
                     font=font(15, "bold"),
                     text_color=TEXT_WHITE).pack(anchor="w", padx=12, pady=(0, 8))

        auto_card = ctk.CTkFrame(scroll, corner_radius=8, fg_color=BG_CARD)
        auto_card.pack(fill="x", padx=12, pady=(0, 6))

        self.autostart_var = ctk.BooleanVar(value=self.cfg.get("auto_start", True))
        ctk.CTkCheckBox(auto_card, text="  \U0001F680  開機自動啟動 NetGuard",
                         font=font(13),
                         text_color=TEXT_PRIMARY,
                         variable=self.autostart_var,
                         fg_color=ACCENT, hover_color=ACCENT_HI
                         ).pack(padx=16, pady=12, anchor="w")

        # 提示
        tips_frame = ctk.CTkFrame(scroll, corner_radius=8, fg_color="#1a2a1a",
                                   border_width=1, border_color="#2a4a2a")
        tips_frame.pack(fill="x", padx=12, pady=(10, 4))

        ctk.CTkLabel(tips_frame, text="\U0001F4A1  提示",
                     font=font(13, "bold"),
                     text_color=YELLOW).pack(anchor="w", padx=16, pady=(10, 4))

        for t in [
            "\u2022  正常網速 500~1000 Mbps，降速後 < 5 Mbps",
            "\u2022  建議閾值設 10 Mbps，可準確判斷降速",
            "\u2022  測速間隔建議 60~300 秒",
        ]:
            ctk.CTkLabel(tips_frame, text=f"   {t}", font=font(11),
                         text_color=TEXT_DIM).pack(anchor="w", padx=16, pady=1)

        # 底部間距
        ctk.CTkLabel(tips_frame, text="").pack(pady=2)

    # ── MAC 操作 ──

    def _update_count(self):
        self.count_label.configure(text=f"{len(self.mac_rows)} 個")

    def _add_mac(self):
        raw = self.mac_entry.get().strip()
        if not raw:
            return
        if not is_valid_mac(raw):
            show_alert("格式錯誤", f"無效的 MAC 位址：{raw}",
                       alert_type="error",
                       detail="請輸入 12 位十六進位字元，例如 0C-9D-92-18-AA-C4")
            return

        normalized = normalize_mac(raw)
        existing = self._get_mac_list()
        if normalized in existing:
            show_alert("重複", "此 MAC 位址已在清單中", alert_type="warning")
            return

        self._add_mac_row(format_mac(normalized))
        self.mac_entry.delete(0, "end")
        self._update_count()

    def _remove_mac(self):
        for i, row in enumerate(self.mac_rows):
            if row._selected:
                row.destroy()
                self.mac_rows.pop(i)
                self._update_count()
                return
        show_alert("提示", "請先在清單中選取要刪除的項目", alert_type="info")

    def _get_mac_list(self) -> list[str]:
        result = []
        for row in self.mac_rows:
            for child in row.winfo_children():
                if isinstance(child, ctk.CTkLabel):
                    text = child.cget("text").strip()
                    text = text.replace("\U0001F4CD", "").strip()
                    result.append(normalize_mac(text))
        return result

    def _save_and_close(self):
        mac_list = self._get_mac_list()
        if not mac_list:
            show_alert("錯誤", "請至少新增一個 MAC 位址", alert_type="error")
            return

        self.cfg["mac_list"] = mac_list
        self.cfg["auto_start"] = self.autostart_var.get()

        for key, entry in self.setting_entries.items():
            val = entry.get().strip()
            if key == "adapter_name":
                self.cfg[key] = val
            else:
                try:
                    self.cfg[key] = int(val) if "." not in val else float(val)
                except ValueError:
                    show_alert("格式錯誤", f"「{key}」必須是數字", alert_type="error")
                    return

        self.saved = True
        self._save_config()
        self.win.destroy()
        if self.on_save:
            self.on_save(self.cfg)

    def run(self):
        self.win.mainloop()
        return self.cfg


def open_settings(config_path: Path, on_save=None) -> dict | None:
    w = SettingsWindow(config_path, on_save)
    w.run()
    return w.cfg if w.saved else None


if __name__ == "__main__":
    cfg = open_settings(Path(__file__).parent / "config.json")
    if cfg:
        print(f"MAC: {cfg.get('mac_list', [])}")
