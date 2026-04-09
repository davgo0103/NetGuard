"""
NetGuard UI 主題 — 字體 / 配色 / Windows 系統通知 / 托盤圖示。
"""

import sys
import threading
from pathlib import Path

import customtkinter as ctk
from PIL import Image, ImageDraw
from winotify import Notification, audio

# ── 程式目錄（用於找 logo）────────────────────────────────────
if getattr(sys, "frozen", False):
    _APP_DIR = Path(sys.executable).parent
else:
    _APP_DIR = Path(__file__).parent

# ── 字體 ─────────────────────────────────────────────────
# 中文用微軟正黑體，等寬用 Cascadia Mono（fallback Consolas）

FONT_FAMILY = "Microsoft JhengHei UI"
MONO_FAMILY = "Cascadia Mono"

def font(size=13, weight="normal"):
    return ctk.CTkFont(family=FONT_FAMILY, size=size, weight=weight)

def mono(size=13):
    return ctk.CTkFont(family=MONO_FAMILY, size=size)

# ── 配色 ─────────────────────────────────────────────────

ACCENT      = "#00b4d8"
ACCENT_HI   = "#0096c7"
GREEN       = "#00e676"
YELLOW      = "#ffca28"
RED         = "#ff5252"
BG_DARK     = "#0f1117"
BG_BANNER   = "#161929"
BG_CARD     = "#1c2033"
BG_ROW      = "#222740"
BG_ROW_SEL  = "#1a3548"
BORDER      = "#2d3250"
TEXT_WHITE   = "#eef0f6"
TEXT_PRIMARY = "#c8cce0"
TEXT_DIM     = "#7a7f9a"
TEXT_MUTED   = "#505470"

# ── 通知系統（Windows 系統通知）─────────────────────────────

_ALERT_ICON = {
    "warning": "\u26A0",
    "error":   "\u2716",
    "success": "\u2714",
    "info":    "\u2139",
}


def show_alert(title: str, message: str, alert_type: str = "warning", detail: str = ""):
    """使用 Windows 系統通知顯示訊息。"""
    threading.Thread(target=lambda: _show_toast(title, message, alert_type, detail),
                     daemon=True).start()


def _show_toast(title, message, alert_type, detail):
    try:
        icon_char = _ALERT_ICON.get(alert_type, _ALERT_ICON["info"])
        display_title = f"{icon_char} {title.replace('NetGuard - ', '')}"

        body = message
        if detail:
            body += f"\n{detail}"

        # 找 logo 作為通知圖示
        icon_path = _APP_DIR / "logo.png"
        icon_str = str(icon_path) if icon_path.exists() else ""

        toast = Notification(
            app_id="NetGuard",
            title=display_title,
            msg=body,
            icon=icon_str,
            duration="long",
        )
        toast.set_audio(audio.Default, loop=False)
        toast.show()
    except Exception:
        pass


# ── 托盤圖示 ──────────────────────────────────────────────

def create_tray_icon(color: str = "green", size: int = 64):
    cmap = {
        "green":  ("#00e676", "#00c853", "#1b5e20"),
        "yellow": ("#ffca28", "#ffa000", "#4e3a00"),
        "red":    ("#ff5252", "#d32f2f", "#4a0000"),
        "gray":   ("#78849e", "#5c6480", "#2a2e40"),
    }
    light, mid, dark = cmap.get(color, cmap["green"])

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    p = 2

    d.rounded_rectangle([p, p, size-p, size-p], radius=size//5, fill=dark)
    d.rounded_rectangle([p+2, p+2, size-p-2, size-p-2], radius=size//5-1, fill=mid)

    cx = size // 2
    bolt = [
        (cx + 2, 12), (cx - 7, cx + 1), (cx - 1, cx + 1),
        (cx - 4, size - 12), (cx + 7, cx - 1), (cx + 1, cx - 1),
    ]
    d.polygon(bolt, fill="#ffffff")

    dot_r = 7
    dx, dy = size - dot_r - 5, size - dot_r - 5
    d.ellipse([dx-dot_r, dy-dot_r, dx+dot_r, dy+dot_r], fill=light, outline=dark, width=2)

    return img
