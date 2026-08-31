from __future__ import annotations

import ctypes
import json
import logging
import os
from logging.handlers import RotatingFileHandler
import threading
import time
from ctypes import wintypes
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import mss
import tkinter as tk
from tkinter import colorchooser, filedialog, font as tkfont
from PIL import Image, ImageChops, ImageStat, ImageTk

from classifier import ButtonStateClassifier, Classification
from runtime_paths import app_base_dir, ensure_user_data_dirs, user_data_dir


APP_NAME = "Turnlight"
APP_VERSION = "0.9.1-beta"
APP_MODEL_ID = "Turnlight.Local"
APP_DIR = app_base_dir()
DATA_DIR = user_data_dir()
CONFIG_PATH = DATA_DIR / "config.json"
LOG_PATH = DATA_DIR / "turnlight.log"
STATUS_PATH = DATA_DIR / "status.json"
SAMPLES_DIR = DATA_DIR / "samples"
ICON_PNG_DIR = APP_DIR / "assets" / "icons" / "png"
APP_ICON_PATH = APP_DIR / "assets" / "app" / "turnlight.ico"
APP_WIDTH = 474
APP_HEIGHT = 230
APP_EXPANDED_HEIGHT = 626
PERSONALIZATION_WIDTH = 416
PERSONALIZATION_HEIGHT = 580
PERSONALIZATION_GAP = 6
APP_PERSONALIZATION_WIDTH = APP_WIDTH + PERSONALIZATION_GAP + PERSONALIZATION_WIDTH
DEFAULT_ALERT_TITLE = "Agent finished"
DEFAULT_ALERT_SUBTITLE = "Your AI task is ready."
ALERT_TITLE_MAX_CHARS = 32
ALERT_SUBTITLE_MAX_CHARS = 48

BG = "#020106"
TITLE_BG = "#05040b"
PANEL = "#07050c"
PANEL_SOFT = "#100d18"
TEXT = "#ffffff"
MUTED = "#d6d1df"
BORDER = "#b9b5c4"
HOVER_BORDER = "#ffffff"
ACCENT = "#201a2b"
READY = "#ffffff"
BADGE_BG = "#181420"
BADGE_ACTIVE = "#0f3523"
CTA_CONFIG = "#221e2b"
CTA_PAUSE = "#2d2936"
CTA_START = "#34303d"
DISABLED_FILL = "#15131a"
DISABLED_BORDER = "#595463"
BAR_ARROW = "#0f3523"
BAR_BUSY = "#382b12"
BAR_MISSING = "#32181f"
ALERT_ORANGE = "#000000"
ALERT_CARD = "#05040a"
ALERT_BUTTON = "#282430"
ALERT_BUTTON_HOVER = "#3a3544"


DEFAULT_CONFIG: dict[str, Any] = {
    "region": None,
    "selection_padding": 6,
    "interval_ms": 500,
    "classifier_threshold": 0.78,
    "classifier_margin": 0.035,
    "stable_samples": 3,
    "busy_stable_samples": 3,
    "arrow_transition_samples": 1,
    "cooldown_seconds": 5,
    "system_view_suppression_seconds": 5,
    "visual_interruption_threshold": 0.42,
    "pause_after_alert": False,
    "window_position": None,
    "alert_color": None,
    "alert_title": DEFAULT_ALERT_TITLE,
    "alert_subtitle": DEFAULT_ALERT_SUBTITLE,
    "sound_enabled": True,
    "custom_sound_path": None,
    "alert_screen_mode": "multi",
}


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", RECT),
        ("rcWork", RECT),
        ("dwFlags", wintypes.DWORD),
    ]


def set_dpi_awareness() -> None:
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def set_app_user_model_id() -> None:
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_MODEL_ID)
    except Exception:
        pass


def normalize_monitor_rects(monitors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, monitor in enumerate(monitors):
        try:
            left = int(monitor["left"])
            top = int(monitor["top"])
            if "right" in monitor and "bottom" in monitor:
                right = int(monitor["right"])
                bottom = int(monitor["bottom"])
            else:
                right = left + int(monitor["width"])
                bottom = top + int(monitor["height"])
            width = right - left
            height = bottom - top
        except (KeyError, TypeError, ValueError):
            continue
        if width <= 0 or height <= 0:
            continue
        normalized.append(
            {
                "left": left,
                "top": top,
                "right": right,
                "bottom": bottom,
                "width": width,
                "height": height,
                "primary": bool(monitor.get("primary", False)),
                "orientation": "vertical" if height > width else "horizontal",
                "source": str(monitor.get("source", "unknown")),
                "index": int(monitor.get("index", index + 1)),
            }
        )
    return normalized


def virtual_screen() -> dict[str, int]:
    with mss.mss() as sct:
        monitor = sct.monitors[0]
        return {
            "left": int(monitor["left"]),
            "top": int(monitor["top"]),
            "width": int(monitor["width"]),
            "height": int(monitor["height"]),
            "right": int(monitor["left"]) + int(monitor["width"]),
            "bottom": int(monitor["top"]) + int(monitor["height"]),
            "primary": True,
            "source": "mss_virtual",
        }


def physical_monitors() -> list[dict[str, int]]:
    with mss.mss() as sct:
        return [
            {
                "left": int(monitor["left"]),
                "top": int(monitor["top"]),
                "width": int(monitor["width"]),
                "height": int(monitor["height"]),
                "right": int(monitor["left"]) + int(monitor["width"]),
                "bottom": int(monitor["top"]) + int(monitor["height"]),
                "primary": index == 0,
                "source": "mss",
                "index": index + 1,
            }
            for index, monitor in enumerate(sct.monitors[1:])
        ]


def windows_monitors() -> list[dict[str, int]]:
    monitors: list[dict[str, int]] = []
    user32 = ctypes.windll.user32
    monitor_enum_proc = ctypes.WINFUNCTYPE(
        wintypes.BOOL,
        wintypes.HMONITOR,
        wintypes.HDC,
        ctypes.POINTER(RECT),
        wintypes.LPARAM,
    )

    def callback(hmonitor: int, _hdc: int, _rect: ctypes.POINTER(RECT), _data: int) -> int:
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        if user32.GetMonitorInfoW(hmonitor, ctypes.byref(info)):
            rect = info.rcMonitor
            monitors.append(
                {
                    "left": int(rect.left),
                    "top": int(rect.top),
                    "right": int(rect.right),
                    "bottom": int(rect.bottom),
                    "width": int(rect.right - rect.left),
                    "height": int(rect.bottom - rect.top),
                    "primary": bool(info.dwFlags & 1),
                    "source": "win32",
                    "index": len(monitors) + 1,
                }
            )
        return 1

    user32.EnumDisplayMonitors(0, 0, monitor_enum_proc(callback), 0)
    return normalize_monitor_rects(monitors)


def all_display_monitors() -> list[dict[str, Any]]:
    try:
        monitors = windows_monitors()
        if monitors:
            logging.info("Display monitors from Win32: %s", monitors)
            return monitors
    except Exception:
        logging.exception("Could not enumerate monitors with Win32")

    try:
        monitors = normalize_monitor_rects(physical_monitors())
        if monitors:
            logging.info("Display monitors from MSS: %s", monitors)
            return monitors
    except Exception:
        logging.exception("Could not enumerate monitors with MSS")

    monitor = normalize_monitor_rects([virtual_screen()])
    logging.info("Display monitors from virtual fallback: %s", monitor)
    return monitor


def monitors_for_alert(mode: str) -> list[dict[str, Any]]:
    monitors = all_display_monitors()
    if mode == "primary":
        for monitor in monitors:
            if monitor.get("primary"):
                return [monitor]
        return monitors[:1]
    return monitors


def primary_monitor() -> dict[str, int]:
    try:
        monitors = all_display_monitors()
        for monitor in monitors:
            if monitor.get("primary"):
                return monitor
        if monitors:
            return monitors[0]
    except Exception:
        logging.exception("Could not get primary monitor with Win32")

    monitors = physical_monitors()
    if monitors:
        return monitors[0]
    return virtual_screen()


def get_window_rect(hwnd: int) -> dict[str, int] | None:
    if not hwnd:
        return None
    rect = RECT()
    if not ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    return {
        "left": int(rect.left),
        "top": int(rect.top),
        "right": int(rect.right),
        "bottom": int(rect.bottom),
        "width": int(rect.right - rect.left),
        "height": int(rect.bottom - rect.top),
    }


def rect_matches(expected: dict[str, Any], actual: dict[str, int] | None, tolerance: int = 2) -> bool:
    if actual is None:
        return False
    return (
        abs(int(expected["left"]) - int(actual["left"])) <= tolerance
        and abs(int(expected["top"]) - int(actual["top"])) <= tolerance
        and abs(int(expected["width"]) - int(actual["width"])) <= tolerance
        and abs(int(expected["height"]) - int(actual["height"])) <= tolerance
    )


def set_window_rect(hwnd: int, rect: dict[str, Any], *, topmost: bool = True) -> dict[str, int] | None:
    if not hwnd:
        return None
    user32 = ctypes.windll.user32
    hwnd_insert_after = -1 if topmost else 0
    swp_showwindow = 0x0040
    user32.SetWindowPos(
        hwnd,
        hwnd_insert_after,
        int(rect["left"]),
        int(rect["top"]),
        int(rect["width"]),
        int(rect["height"]),
        swp_showwindow,
    )
    actual = get_window_rect(hwnd)
    if rect_matches(rect, actual):
        return actual

    user32.MoveWindow(
        hwnd,
        int(rect["left"]),
        int(rect["top"]),
        int(rect["width"]),
        int(rect["height"]),
        True,
    )
    actual = get_window_rect(hwnd)
    if not rect_matches(rect, actual):
        logging.warning("Window rect mismatch. expected=%s actual=%s", rect, actual)
    return actual


def rects_intersect(a: dict[str, int], b: dict[str, int]) -> bool:
    return (
        int(a["left"]) < int(b["left"]) + int(b["width"])
        and int(a["left"]) + int(a["width"]) > int(b["left"])
        and int(a["top"]) < int(b["top"]) + int(b["height"])
        and int(a["top"]) + int(a["height"]) > int(b["top"])
    )


def monitor_at_point(x: int, y: int, monitors: list[dict[str, Any]]) -> dict[str, Any] | None:
    for monitor in monitors:
        if (
            int(monitor["left"]) <= x < int(monitor["right"])
            and int(monitor["top"]) <= y < int(monitor["bottom"])
        ):
            return monitor
    return None


def valid_window_position(position: Any, width: int = APP_WIDTH, height: int = APP_HEIGHT) -> tuple[int, int] | None:
    if not isinstance(position, dict):
        return None
    try:
        left = int(position["left"])
        top = int(position["top"])
    except (KeyError, TypeError, ValueError):
        return None

    window_rect = {"left": left, "top": top, "width": width, "height": height}
    monitors = windows_monitors() or physical_monitors() or [virtual_screen()]
    if any(rects_intersect(window_rect, monitor) for monitor in monitors):
        return left, top
    return None


def cursor_position() -> tuple[int, int]:
    point = POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
    return int(point.x), int(point.y)


def key_is_down(virtual_key: int) -> bool:
    try:
        return bool(ctypes.windll.user32.GetAsyncKeyState(virtual_key) & 0x8000)
    except Exception:
        return False


def task_view_hotkey_is_down() -> bool:
    vk_tab = 0x09
    vk_lwin = 0x5B
    vk_rwin = 0x5C
    return key_is_down(vk_tab) and (key_is_down(vk_lwin) or key_is_down(vk_rwin))


def foreground_window_info() -> dict[str, str | int] | None:
    try:
        user32 = ctypes.windll.user32
        hwnd = int(user32.GetForegroundWindow())
        if not hwnd:
            return None

        class_buffer = ctypes.create_unicode_buffer(256)
        title_buffer = ctypes.create_unicode_buffer(512)
        user32.GetClassNameW(hwnd, class_buffer, len(class_buffer))
        user32.GetWindowTextW(hwnd, title_buffer, len(title_buffer))
        return {
            "hwnd": hwnd,
            "class_name": class_buffer.value,
            "title": title_buffer.value,
        }
    except Exception:
        logging.exception("Could not inspect foreground window")
        return None


def task_view_foreground_reason() -> str | None:
    info = foreground_window_info()
    if info is None:
        return None

    class_name = str(info.get("class_name", ""))
    title = str(info.get("title", ""))
    haystack = f"{class_name} {title}".lower()
    markers = (
        "multitaskingview",
        "task view",
        "vista de tareas",
        "xamlexplorerhostislandwindow",
    )
    if any(marker in haystack for marker in markers):
        return f"task_view_foreground class={class_name!r} title={title!r}"
    return None


def clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


def global_to_local(x: int, y: int, screen: dict[str, int]) -> tuple[int, int]:
    return x - int(screen["left"]), y - int(screen["top"])


def region_from_points(start: tuple[int, int], end: tuple[int, int], screen: dict[str, int], padding: int) -> dict[str, int]:
    screen_left = int(screen["left"])
    screen_top = int(screen["top"])
    screen_right = screen_left + int(screen["width"])
    screen_bottom = screen_top + int(screen["height"])

    x1 = clamp(start[0], screen_left, screen_right)
    y1 = clamp(start[1], screen_top, screen_bottom)
    x2 = clamp(end[0], screen_left, screen_right)
    y2 = clamp(end[1], screen_top, screen_bottom)

    left = clamp(min(x1, x2) - padding, screen_left, screen_right)
    top = clamp(min(y1, y2) - padding, screen_top, screen_bottom)
    right = clamp(max(x1, x2) + padding, screen_left, screen_right)
    bottom = clamp(max(y1, y2) + padding, screen_top, screen_bottom)

    return {"left": left, "top": top, "width": right - left, "height": bottom - top}


def make_appwindow(hwnd: int) -> None:
    if not hwnd:
        return
    user32 = ctypes.windll.user32
    gwl_exstyle = -20
    ws_ex_toolwindow = 0x00000080
    ws_ex_appwindow = 0x00040000
    swp_nomove = 0x0002
    swp_nosize = 0x0001
    swp_nozorder = 0x0004
    swp_framechanged = 0x0020

    style = user32.GetWindowLongW(hwnd, gwl_exstyle)
    style = (style & ~ws_ex_toolwindow) | ws_ex_appwindow
    user32.SetWindowLongW(hwnd, gwl_exstyle, style)
    user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, swp_nomove | swp_nosize | swp_nozorder | swp_framechanged)


def get_toplevel_hwnd(widget: tk.Misc) -> int:
    widget.update_idletasks()
    hwnd = int(widget.winfo_id())
    parent = ctypes.windll.user32.GetParent(hwnd)
    return int(parent or hwnd)


def apply_rounded_window(hwnd: int, width: int, height: int, radius: int = 22) -> None:
    if not hwnd or width <= 0 or height <= 0:
        return
    gdi32 = ctypes.windll.gdi32
    user32 = ctypes.windll.user32
    region = gdi32.CreateRoundRectRgn(0, 0, width + 1, height + 1, radius, radius)
    if region:
        result = user32.SetWindowRgn(hwnd, region, True)
        if not result:
            gdi32.DeleteObject(region)


def load_config() -> dict[str, Any]:
    ensure_user_data_dirs()
    config = DEFAULT_CONFIG.copy()
    if CONFIG_PATH.exists():
        try:
            loaded = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                config.update(loaded)
        except Exception:
            logging.exception("Could not read config.json")
    return config


def save_config(config: dict[str, Any]) -> None:
    ensure_user_data_dirs()
    CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")


def alert_color(config: dict[str, Any]) -> str:
    value = config.get("alert_color")
    return str(value) if isinstance(value, str) and value.startswith("#") else ALERT_ORANGE


def clean_alert_text(value: str, max_chars: int) -> str:
    return value.replace("\r", " ").replace("\n", " ")[:max_chars]


def image_delta(a: Image.Image, b: Image.Image) -> float:
    first = a.convert("L").resize((32, 32), Image.Resampling.BILINEAR)
    second = b.convert("L").resize((32, 32), Image.Resampling.BILINEAR)
    diff = ImageChops.difference(first, second)
    return ImageStat.Stat(diff).mean[0] / 255.0


def alert_text_value(
    config: dict[str, Any],
    key: str,
    default: str,
    max_chars: int,
    *,
    allow_empty: bool = False,
) -> str:
    value = config.get(key)
    if not isinstance(value, str):
        return default
    text = " ".join(clean_alert_text(value, max_chars).split())
    if not text and not allow_empty:
        return default
    return text


def alert_title(config: dict[str, Any]) -> str:
    return alert_text_value(config, "alert_title", DEFAULT_ALERT_TITLE, ALERT_TITLE_MAX_CHARS)


def alert_subtitle(config: dict[str, Any]) -> str:
    return alert_text_value(
        config,
        "alert_subtitle",
        DEFAULT_ALERT_SUBTITLE,
        ALERT_SUBTITLE_MAX_CHARS,
        allow_empty=True,
    )


def ensure_runtime_assets() -> None:
    required = [ICON_PNG_DIR / "app-icon.png", ICON_PNG_DIR / "settings.png", APP_ICON_PATH]
    if all(path.exists() for path in required):
        return
    try:
        from prepare_assets import main as prepare_assets

        prepare_assets()
    except Exception:
        logging.exception("Could not prepare runtime assets")


class RoundedPanel(tk.Canvas):
    def __init__(
        self,
        parent: tk.Widget,
        *,
        bg: str,
        radius: int = 24,
        border: str = BORDER,
        border_width: int = 5,
        padding: int = 16,
        canvas_bg: str = BG,
        **kwargs: Any,
    ) -> None:
        super().__init__(parent, bg=canvas_bg, highlightthickness=0, bd=0, **kwargs)
        self.fill = bg
        self.radius = radius
        self.border = border
        self.border_width = border_width
        self.padding = padding
        self.inner = tk.Frame(self, bg=bg)
        self.inner_id = self.create_window(0, 0, window=self.inner, anchor="nw")
        self.bind("<Configure>", self._redraw)

    def _rounded_rect(self, x1: int, y1: int, x2: int, y2: int, r: int, **kwargs: Any) -> None:
        points = [
            x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
            x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
            x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
        ]
        self.create_polygon(points, smooth=True, splinesteps=24, **kwargs)

    def _redraw(self, _event: tk.Event | None = None) -> None:
        self.delete("shape")
        w = max(2, self.winfo_width())
        h = max(2, self.winfo_height())
        inset = max(2, self.border_width // 2)
        self._rounded_rect(
            inset,
            inset,
            w - inset,
            h - inset,
            self.radius,
            fill=self.fill,
            outline=self.border,
            width=self.border_width,
            tags="shape",
        )
        self.coords(self.inner_id, self.padding, self.padding)
        self.itemconfigure(
            self.inner_id,
            width=max(1, w - self.padding * 2),
            height=max(1, h - self.padding * 2),
        )
        self.tag_lower("shape")


class RoundedButton(tk.Canvas):
    def __init__(
        self,
        parent: tk.Widget,
        text: str,
        command: Callable[[], None],
        *,
        fill: str = PANEL_SOFT,
        active: str = "#201a2c",
        radius: int = 18,
        font_size: int = 11,
        canvas_bg: str = PANEL,
        icon: ImageTk.PhotoImage | None = None,
        icon_position: str = "top",
        border_width: int = 4,
        icon_x_offset: int = 0,
        icon_y_offset: int = 0,
        text_y_offset: int = 0,
        text_line_spacing: int = 0,
    ) -> None:
        super().__init__(parent, bg=canvas_bg, highlightthickness=0, bd=0, width=116, height=74, cursor="hand2")
        self.text = text
        self.command = command
        self.fill = fill
        self.active = active
        self.border = BORDER
        self.radius = radius
        self.font_size = font_size
        self.current = fill
        self.enabled = True
        self.icon = icon
        self.icon_position = icon_position
        self.border_width = border_width
        self.icon_x_offset = icon_x_offset
        self.icon_y_offset = icon_y_offset
        self.text_y_offset = text_y_offset
        self.text_line_spacing = text_line_spacing
        self.bind("<Configure>", self._draw)
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<Button-1>", self._click)

    def _rounded_rect(self, x1: int, y1: int, x2: int, y2: int, r: int, **kwargs: Any) -> None:
        points = [
            x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
            x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
            x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
        ]
        self.create_polygon(points, smooth=True, splinesteps=24, **kwargs)

    def _draw(self, _event: tk.Event | None = None) -> None:
        self.delete("all")
        w = max(2, self.winfo_width())
        h = max(2, self.winfo_height())
        fill = self.current if self.enabled else DISABLED_FILL
        border = self.border if self.enabled else DISABLED_BORDER
        text_fill = TEXT if self.enabled else MUTED
        radius = min(self.radius, max(8, (h - 8) // 2))
        inset = max(3, self.border_width)
        self._rounded_rect(inset, inset, w - inset, h - inset, radius, fill=fill, outline=border, width=self.border_width)
        if self.icon is not None and not self.text.strip():
            self.create_image(w // 2, h // 2, image=self.icon)
            return
        if self.icon is not None and self.icon_position == "left":
            gap = 0
            icon_slot = 24
            text_width = max(82, w - 92)
            group_width = icon_slot + gap + text_width
            start_x = max(18, (w - group_width) // 2)
            icon_x = start_x + icon_slot // 2
            text_center = start_x + icon_slot + gap + text_width // 2
            self.create_image(icon_x + self.icon_x_offset, h // 2, image=self.icon)
            if "\n" in self.text and self.text_line_spacing:
                font_spec = ("Segoe UI", self.font_size, "bold")
                line_height = tkfont.Font(font=font_spec).metrics("linespace")
                lines = self.text.splitlines()
                line_step = max(8, line_height + self.text_line_spacing)
                first_y = h // 2 - ((len(lines) - 1) * line_step) / 2
                for index, line in enumerate(lines):
                    self.create_text(
                        text_center,
                        first_y + index * line_step,
                        text=line,
                        fill=text_fill,
                        font=font_spec,
                        width=text_width,
                        justify="center",
                        anchor="center",
                    )
                return
            self.create_text(
                text_center,
                h // 2,
                text=self.text,
                fill=text_fill,
                font=("Segoe UI", self.font_size, "bold"),
                width=text_width,
                justify="center",
                anchor="center",
            )
            return
        if self.icon is not None:
            self.create_image(w // 2, max(20, h // 2 - 20 + self.icon_y_offset), image=self.icon)
            text_y = min(h - 20, h // 2 + 14 + self.text_y_offset)
        else:
            text_y = h // 2
        self.create_text(
            w // 2,
            text_y,
            text=self.text,
            fill=text_fill,
            font=("Segoe UI", self.font_size, "bold"),
            width=max(86, w - 28),
            justify="center",
            anchor="center",
        )

    def _enter(self, _event: tk.Event) -> None:
        if not self.enabled:
            return
        self.current = self.active
        self.border = HOVER_BORDER
        self._draw()

    def _leave(self, _event: tk.Event) -> None:
        if not self.enabled:
            return
        self.current = self.fill
        self.border = BORDER
        self._draw()

    def set_icon(self, icon: ImageTk.PhotoImage | None) -> None:
        self.icon = icon
        self._draw()

    def _click(self, _event: tk.Event) -> None:
        if self.enabled:
            self.command()

    def set_enabled(self, enabled: bool) -> None:
        if self.enabled == enabled:
            return
        self.enabled = enabled
        self.configure(cursor="hand2" if enabled else "arrow")
        self.current = self.fill
        self.border = BORDER
        self._draw()


class StatusBadge(tk.Canvas):
    def __init__(self, parent: tk.Widget, variable: tk.StringVar) -> None:
        super().__init__(parent, bg=PANEL, highlightthickness=0, bd=0, width=136, height=42)
        self.variable = variable
        self.variable.trace_add("write", lambda *_args: self._draw())
        self.bind("<Configure>", self._draw)

    def _rounded_rect(self, x1: int, y1: int, x2: int, y2: int, r: int, **kwargs: Any) -> None:
        points = [
            x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
            x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
            x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
        ]
        self.create_polygon(points, smooth=True, splinesteps=18, **kwargs)

    def _draw(self, _event: tk.Event | None = None) -> None:
        self.delete("all")
        w = max(2, self.winfo_width())
        h = max(2, self.winfo_height())
        label = self.variable.get()
        fill = BADGE_ACTIVE if label.lower().startswith("watch") else BADGE_BG
        self._rounded_rect(3, 3, w - 3, h - 3, max(14, h // 2 - 3), fill=fill, outline=BORDER, width=3)
        self.create_text(w // 2, h // 2 - 1, text=label, fill=TEXT, font=("Segoe UI", 12, "bold"), justify="center", anchor="center")


class DetectionBar(tk.Canvas):
    def __init__(self, parent: tk.Widget, variable: tk.StringVar) -> None:
        super().__init__(parent, bg=PANEL, highlightthickness=0, bd=0, width=516, height=34)
        self.variable = variable
        self.variable.trace_add("write", lambda *_args: self._draw())
        self.bind("<Configure>", self._draw)

    def _rounded_rect(self, x1: int, y1: int, x2: int, y2: int, r: int, **kwargs: Any) -> None:
        points = [
            x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
            x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
            x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
        ]
        self.create_polygon(points, smooth=True, splinesteps=18, **kwargs)

    def _draw(self, _event: tk.Event | None = None) -> None:
        self.delete("all")
        w = max(2, self.winfo_width())
        h = max(2, self.winfo_height())
        label = self.variable.get()
        if label in {"Ready arrow", "Ready arrow detected", "Arrow detected"}:
            fill = BAR_ARROW
        elif label in {"Busy", "Busy detected"}:
            fill = BAR_BUSY
        else:
            fill = BAR_MISSING
        self._rounded_rect(4, 4, w - 4, h - 4, max(12, h // 2 - 4), fill=fill, outline=BORDER, width=4)
        self.create_text(w // 2, h // 2 - 1, text=label, fill=TEXT, font=("Segoe UI", 12, "bold"), justify="center", anchor="center")


class TurnlightApp:
    def __init__(self) -> None:
        ensure_runtime_assets()
        self.config = load_config()
        self.root = tk.Tk()
        self.root.title(APP_NAME)
        saved_position = valid_window_position(self.config.get("window_position"))
        if saved_position is None:
            self.root.geometry(f"{APP_WIDTH}x{APP_HEIGHT}")
        else:
            self.root.geometry(f"{APP_WIDTH}x{APP_HEIGHT}{saved_position[0]:+d}{saved_position[1]:+d}")
        self.root.minsize(APP_WIDTH, APP_HEIGHT)
        self.root.maxsize(APP_PERSONALIZATION_WIDTH, APP_EXPANDED_HEIGHT)
        self.root.resizable(False, False)
        self.root.overrideredirect(True)
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.bind("<Escape>", self._handle_escape)
        if APP_ICON_PATH.exists():
            try:
                self.root.iconbitmap(str(APP_ICON_PATH))
            except Exception:
                logging.exception("Could not set app icon")
        self.drag_offset = (0, 0)
        self.shell_configured = False
        self.shell_refresh_done = False
        self.auto_start_attempted = False
        self.settings_open = False
        self.settings_panel: RoundedPanel | None = None
        self.settings_inner: tk.Frame | None = None
        self.personalization_open = False
        self.personalization_panel: RoundedPanel | None = None
        self.custom_sound_text: tk.StringVar | None = None
        self.alert_title_text: tk.StringVar | None = None
        self.alert_subtitle_text: tk.StringVar | None = None
        self.updating_alert_text = False
        self.alert_pending = False
        self.alert_active = False
        self.alert_windows: list[tk.Toplevel] = []
        self.alert_sound_stop: threading.Event | None = None
        self.alert_sound_thread: threading.Thread | None = None
        self.alert_suppressed_until = 0.0
        self.alert_suppression_reason: str | None = None
        self.last_visual_delta = 0.0

        self.running = threading.Event()
        self.shutdown = threading.Event()
        self.lock = threading.Lock()
        self.last_current: Image.Image | None = None
        self.last_alert_at = 0.0
        self.stable_count = 0
        self.busy_streak = 0
        self.arrow_streak = 0
        self.armed_after_busy = False
        self.last_watcher_state = "unknown"
        self.last_classification: Classification | None = None
        self.last_error: str | None = None
        self.last_sample_at = 0.0
        self.preview_photo: ImageTk.PhotoImage | None = None
        self.icons: dict[str, ImageTk.PhotoImage] = {}
        self.classifier = ButtonStateClassifier(
            samples_dir=SAMPLES_DIR,
            threshold=float(self.config.get("classifier_threshold", 0.78)),
            margin=float(self.config.get("classifier_margin", 0.035)),
        )

        self.action_text = tk.StringVar(value="Paused")
        self.toggle_text = tk.StringVar(value="Start")
        self.detection_text = tk.StringVar(value="No sample")
        self.preview_hint = tk.StringVar(value="The captured area will appear here.")

        self._load_icons()
        self._build_ui()
        self.root.after(50, lambda: self.configure_window_shell(0))
        self.watcher_thread = threading.Thread(target=self._watch_loop, daemon=True)

    def start(self) -> None:
        self.watcher_thread.start()
        self.root.after(300, self._ui_tick)
        self.root.after(700, self._preview_tick)
        self.write_status()
        self.root.mainloop()

    def _load_icons(self) -> None:
        names = [
            "app-icon",
            "settings",
            "dark-mode",
            "bright-mode",
            "crosshair",
            "play",
            "pause",
            "camera",
            "busy-stop",
            "ready-arrow",
            "ignored",
            "bell",
            "palette",
            "volume-on",
            "volume-off",
            "check-circle",
            "eye",
            "status-dot",
            "close",
            "minimize",
            "folder",
            "refresh",
            "info",
            "monitor",
            "single-monitor",
            "spark",
        ]
        for name in names:
            path = ICON_PNG_DIR / f"{name}.png"
            if not path.exists():
                continue
            try:
                size = 22
                if name == "app-icon":
                    size = 30
                elif name in {"close", "minimize"}:
                    size = 18
                elif name in {"check-circle", "spark"}:
                    size = 46
                elif name in {"crosshair", "play", "pause", "settings", "dark-mode", "bright-mode", "busy-stop", "ready-arrow", "ignored", "bell", "palette", "volume-on", "volume-off", "folder", "refresh", "monitor", "single-monitor"}:
                    size = 32
                image = Image.open(path).convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)
                self.icons[name] = ImageTk.PhotoImage(image)
            except Exception:
                logging.exception("Could not load icon %s", name)

    def icon(self, name: str) -> ImageTk.PhotoImage | None:
        return self.icons.get(name)

    def icon_sized(self, name: str, size: int) -> ImageTk.PhotoImage | None:
        key = f"{name}:{size}"
        if key in self.icons:
            return self.icons[key]
        path = ICON_PNG_DIR / f"{name}.png"
        if not path.exists():
            return self.icon(name)
        try:
            image = Image.open(path).convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)
            self.icons[key] = ImageTk.PhotoImage(image)
            return self.icons[key]
        except Exception:
            logging.exception("Could not load icon %s at %s", name, size)
            return self.icon(name)

    def icon_cropped_sized(self, name: str, size: int) -> ImageTk.PhotoImage | None:
        key = f"{name}:cropped:{size}"
        if key in self.icons:
            return self.icons[key]
        path = ICON_PNG_DIR / f"{name}.png"
        if not path.exists():
            return self.icon_sized(name, size)
        try:
            image = Image.open(path).convert("RGBA")
            bbox = image.getbbox()
            if bbox is not None:
                image = image.crop(bbox)
            image = image.resize((size, size), Image.Resampling.LANCZOS)
            self.icons[key] = ImageTk.PhotoImage(image)
            return self.icons[key]
        except Exception:
            logging.exception("Could not load cropped icon %s at %s", name, size)
            return self.icon_sized(name, size)

    def _build_ui(self) -> None:
        self._build_titlebar()

        self.shell = tk.Frame(self.root, bg=BG, padx=6, pady=5)
        self.shell.pack(fill="both", expand=True)

        self.left_column = tk.Frame(self.shell, bg=BG)
        self.left_column.pack(side="left", anchor="nw")

        main = RoundedPanel(self.left_column, bg=PANEL, radius=20, border_width=5, padding=10, width=APP_WIDTH - 12)
        main.pack(fill="x")
        main.configure(height=180)

        capture_card = RoundedPanel(
            main.inner,
            bg=PANEL_SOFT,
            radius=24,
            border=BORDER,
            border_width=5,
            padding=8,
            width=126,
            height=144,
        )
        capture_card.place(x=10, y=10, width=126, height=144)
        tk.Label(capture_card.inner, text="Captured Area", bg=PANEL_SOFT, fg=TEXT, font=("Segoe UI", 10, "bold")).place(x=3, y=0)

        preview_panel = RoundedPanel(capture_card.inner, bg=PANEL, radius=17, border=BORDER, border_width=5, padding=3, width=88, height=88)
        preview_panel.place(x=11, y=30, width=88, height=88)
        self.preview_canvas = tk.Canvas(preview_panel.inner, width=82, height=82, bg=PANEL, highlightthickness=0, bd=0)
        self.preview_canvas.place(x=0, y=0, width=82, height=82)
        self.preview_canvas.create_text(41, 41, text="No area", fill=MUTED, font=("Segoe UI", 8, "bold"), tags="hint")

        StatusBadge(main.inner, self.action_text).place(x=292, y=10, width=104, height=36)
        self.settings_button = tk.Label(
            main.inner,
            image=self.icon_sized("settings", 29),
            bg=PANEL,
            cursor="hand2",
        )
        self.settings_button.place(x=408, y=12, width=32, height=32)
        self.settings_button.bind("<Enter>", lambda _event: self.settings_button.configure(bg=ACCENT))
        self.settings_button.bind("<Leave>", lambda _event: self.settings_button.configure(bg=PANEL))
        self.settings_button.bind("<Button-1>", lambda _event: self.toggle_settings())

        self.region_button = RoundedButton(
            main.inner,
            "Set\nRegion",
            self.configure_region,
            fill=CTA_CONFIG,
            radius=24,
            font_size=11,
            icon=self.icon_sized("crosshair", 34),
            icon_position="left",
            icon_x_offset=6,
            text_line_spacing=-5,
        )
        self.region_button.place(x=144, y=50, width=142, height=58)
        self.toggle_button = RoundedButton(
            main.inner,
            "Start",
            self.toggle_watching,
            fill=CTA_START,
            radius=24,
            font_size=13,
            icon=self.icon_sized("play", 34),
            icon_position="left",
            icon_x_offset=8,
        )
        self.toggle_button.place(x=294, y=50, width=142, height=58)
        DetectionBar(main.inner, self.detection_text).place(x=144, y=114, width=292, height=40)

    def _build_titlebar(self) -> None:
        bar = tk.Frame(self.root, bg=TITLE_BG, height=32)
        bar.pack(fill="x", side="top")
        bar.pack_propagate(False)
        bar.bind("<ButtonPress-1>", self._start_drag)
        bar.bind("<B1-Motion>", self._drag_window)
        bar.bind("<ButtonRelease-1>", self._save_window_position)

        if self.icon("app-icon") is not None:
            app_icon = tk.Label(bar, image=self.icon("app-icon"), bg=TITLE_BG)
            app_icon.pack(side="left", padx=(12, 6))
            app_icon.bind("<ButtonPress-1>", self._start_drag)
            app_icon.bind("<B1-Motion>", self._drag_window)
            app_icon.bind("<ButtonRelease-1>", self._save_window_position)

        title = tk.Label(bar, text=APP_NAME, bg=TITLE_BG, fg=TEXT, font=("Segoe UI", 10, "bold"))
        title.pack(side="left")
        title.bind("<ButtonPress-1>", self._start_drag)
        title.bind("<B1-Motion>", self._drag_window)
        title.bind("<ButtonRelease-1>", self._save_window_position)

        close = tk.Label(bar, image=self.icon("close"), bg=TITLE_BG, fg=TEXT, width=40, cursor="hand2")
        close.pack(side="right", fill="y")
        close.bind("<Enter>", lambda _event: close.configure(bg="#35131d"))
        close.bind("<Leave>", lambda _event: close.configure(bg=TITLE_BG))
        close.bind("<Button-1>", lambda _event: self.close())

        minimize = tk.Label(bar, image=self.icon("minimize"), bg=TITLE_BG, fg=MUTED, width=40, cursor="hand2")
        minimize.pack(side="right", fill="y")
        minimize.bind("<Enter>", lambda _event: minimize.configure(bg="#17131f"))
        minimize.bind("<Leave>", lambda _event: minimize.configure(bg=TITLE_BG))
        minimize.bind("<Button-1>", lambda _event: self.minimize())

    def _start_drag(self, event: tk.Event) -> None:
        self.drag_offset = (int(event.x_root) - self.root.winfo_x(), int(event.y_root) - self.root.winfo_y())

    def _drag_window(self, event: tk.Event) -> None:
        x = int(event.x_root) - self.drag_offset[0]
        y = int(event.y_root) - self.drag_offset[1]
        self.root.geometry(f"+{x}+{y}")

    def _save_window_position(self, _event: tk.Event | None = None) -> None:
        if self.shutdown.is_set():
            return
        try:
            self.root.update_idletasks()
            self.config["window_position"] = {
                "left": int(self.root.winfo_x()),
                "top": int(self.root.winfo_y()),
            }
            save_config(self.config)
        except Exception:
            logging.exception("Could not save window position")

    def _handle_escape(self, _event: tk.Event) -> None:
        if self.personalization_open:
            self.close_personalization()

    def minimize(self) -> None:
        self.root.overrideredirect(False)
        self.root.iconify()
        self.root.after(200, self._restore_borderless)

    def _restore_borderless(self) -> None:
        if self.root.state() == "normal":
            self.root.overrideredirect(True)
            self.shell_configured = False
            self.root.after(50, lambda: self.configure_window_shell(0))
        else:
            self.root.after(200, self._restore_borderless)

    def configure_window_shell(self, attempt: int = 0) -> None:
        try:
            self.root.update_idletasks()
            hwnd = get_toplevel_hwnd(self.root)
            make_appwindow(hwnd)
            apply_rounded_window(hwnd, self.root.winfo_width(), self.root.winfo_height(), 24)
            self.refresh_shell_visibility(hwnd)
            if attempt == 0 and not self.shell_refresh_done:
                self.shell_refresh_done = True
                self.root.after(20, self.refresh_taskbar_registration)
            self.shell_configured = True
        except Exception:
            logging.exception("Could not configure shell window")
        finally:
            if attempt < 6 and not self.shutdown.is_set():
                self.root.after(250, lambda: self.configure_window_shell(attempt + 1))

    def refresh_shell_visibility(self, hwnd: int) -> None:
        if not hwnd:
            return
        user32 = ctypes.windll.user32
        swp_nomove = 0x0002
        swp_nosize = 0x0001
        swp_nozorder = 0x0004
        swp_framechanged = 0x0020
        user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, swp_nomove | swp_nosize | swp_nozorder | swp_framechanged)

    def refresh_taskbar_registration(self) -> None:
        try:
            self.root.withdraw()
            self.root.after(35, self.restore_after_taskbar_refresh)
        except tk.TclError:
            pass

    def restore_after_taskbar_refresh(self) -> None:
        try:
            self.root.deiconify()
            self.root.overrideredirect(True)
            self.root.update_idletasks()
            hwnd = get_toplevel_hwnd(self.root)
            make_appwindow(hwnd)
            apply_rounded_window(hwnd, self.root.winfo_width(), self.root.winfo_height(), 24)
            self.refresh_shell_visibility(hwnd)
        except Exception:
            logging.exception("Could not refresh taskbar registration")

    def add_button(
        self,
        parent: tk.Widget,
        text: str,
        command: Callable[[], None],
        x: int,
        y: int,
        *,
        fill: str = PANEL_SOFT,
        active: str = ACCENT,
        font_size: int = 11,
    ) -> None:
        button = RoundedButton(parent, text, command, fill=fill, active=active, font_size=font_size)
        button.place(x=x, y=y, width=96, height=66)

    def notify(self, message: str) -> None:
        logging.info(message)

    def toggle_settings(self) -> None:
        if self.settings_open:
            self.hide_settings()
            return
        self.show_settings()

    def show_settings(self) -> None:
        if self.settings_panel is None:
            self.settings_panel = RoundedPanel(
                self.left_column,
                bg=PANEL,
                radius=20,
                border=BORDER,
                border_width=5,
                padding=10,
                width=APP_WIDTH - 12,
            )
            self.settings_panel.configure(height=390)
            self.settings_inner = self.settings_panel.inner
            self.build_settings_contents(self.settings_inner)
        self.settings_open = True
        self.settings_panel.pack(fill="x", pady=(6, 0))
        self.apply_window_layout("settings")

    def hide_settings(self) -> None:
        self.close_personalization(animate=False)
        self.settings_open = False
        if self.settings_panel is not None:
            self.settings_panel.pack_forget()
        if not self.shutdown.is_set():
            self.apply_window_layout("compact")

    def current_window_mode(self) -> str:
        if self.personalization_open:
            return "settings_personalization"
        if self.settings_open:
            return "settings"
        return "compact"

    def desired_window_size(self, mode: str) -> tuple[int, int]:
        if mode == "settings_personalization":
            return APP_PERSONALIZATION_WIDTH, APP_EXPANDED_HEIGHT
        if mode == "settings":
            return APP_WIDTH, APP_EXPANDED_HEIGHT
        return APP_WIDTH, APP_HEIGHT

    def apply_window_layout(self, mode: str | None = None, *, animate: bool = True) -> None:
        mode = mode or self.current_window_mode()
        width, height = self.desired_window_size(mode)
        left = int(self.root.winfo_x())
        top = int(self.root.winfo_y())
        if animate:
            self.animate_window_layout(width, height, left, top)
        else:
            self.root.geometry(f"{width}x{height}{left:+d}{top:+d}")
            self.configure_window_shell(6)

    def animate_window_layout(self, end_width: int, end_height: int, end_x: int, end_y: int, steps: int = 8) -> None:
        self.root.update_idletasks()
        start_width = int(self.root.winfo_width())
        start_height = int(self.root.winfo_height())
        start_x = int(self.root.winfo_x())
        start_y = int(self.root.winfo_y())
        width_delta = (end_width - start_width) / max(1, steps)
        height_delta = (end_height - start_height) / max(1, steps)
        x_delta = (end_x - start_x) / max(1, steps)
        y_delta = (end_y - start_y) / max(1, steps)

        def step(index: int) -> None:
            width = int(start_width + width_delta * index)
            height = int(start_height + height_delta * index)
            x = int(start_x + x_delta * index)
            y = int(start_y + y_delta * index)
            if index >= steps:
                width, height, x, y = end_width, end_height, end_x, end_y
            self.root.geometry(f"{width}x{height}{x:+d}{y:+d}")
            if index < steps:
                self.root.after(12, lambda: step(index + 1))
            else:
                self.configure_window_shell(6)

        step(1)

    def build_settings_contents(self, parent: tk.Widget) -> None:
        tk.Label(parent, text="Settings", bg=PANEL, fg=TEXT, font=("Segoe UI", 15, "bold")).place(x=12, y=0)
        self.info_button = tk.Label(
            parent,
            image=self.icon_sized("info", 26),
            bg=PANEL,
            cursor="hand2",
        )
        self.info_button.place(x=414, y=0, width=28, height=28)
        self.info_button.bind("<Enter>", lambda _event: self.info_button.configure(bg=ACCENT))
        self.info_button.bind("<Leave>", lambda _event: self.info_button.configure(bg=PANEL))
        self.info_button.bind("<Button-1>", lambda _event: self.open_readme())
        tk.Label(
            parent,
            text="Capture local samples so Turnlight can recognize busy, ready, and ignored states in your AI tools. Use multiple themes, windows, and hover states for better detection.",
            bg=PANEL,
            fg=MUTED,
            font=("Segoe UI", 9, "bold"),
            wraplength=420,
            justify="left",
        ).place(x=12, y=30)

        self._settings_button(parent, "Capture\nBusy", "busy-stop", lambda: self.capture_sample("busy_stop"), 12, 92, width=132, height=92, icon_size=40, icon_position="top", font_size=10)
        self._settings_button(parent, "Capture\nReady", "ready-arrow", lambda: self.capture_sample("typing_arrow"), 156, 92, width=132, height=92, icon_size=40, icon_position="top", font_size=10)
        self._settings_button(parent, "Capture\nIgnored", "ignored", lambda: self.capture_sample("ignored"), 300, 92, width=132, height=92, icon_size=40, icon_position="top", font_size=10)

        self._settings_button(parent, "Test Alert", "bell", self.launch_alert, 12, 200, width=204, height=46, icon_size=24, font_size=11)
        self._settings_button(parent, "Personalization", "palette", self.toggle_personalization, 228, 200, width=204, height=46, icon_size=24, font_size=11)
        self.sound_button = self._settings_button(
            parent,
            "Sound On" if bool(self.config.get("sound_enabled", True)) else "Sound Off",
            "volume-on" if bool(self.config.get("sound_enabled", True)) else "volume-off",
            self.toggle_sound,
            12,
            256,
            width=204,
            height=46,
            icon_size=24,
            font_size=11,
        )
        self._settings_button(parent, "Open Samples", "folder", self.open_samples_folder, 228, 256, width=204, height=46, icon_size=24, font_size=11)

        mode_label, mode_icon = self.alert_screen_mode_label()
        self.screen_mode_button = self._settings_button(
            parent,
            mode_label,
            mode_icon,
            self.toggle_alert_screen_mode,
            12,
            312,
            width=204,
            height=46,
            icon_size=24,
            font_size=11,
        )
        self._settings_button(parent, "Reset Samples", "folder", self.reset_samples, 228, 312, width=204, height=46, icon_size=24, font_size=11)

    def _settings_button(
        self,
        parent: tk.Widget,
        text: str,
        icon_name: str,
        command: Callable[[], None],
        x: int,
        y: int,
        *,
        width: int = 204,
        height: int = 36,
        icon_size: int = 21,
        icon_position: str = "left",
        font_size: int = 9,
    ) -> RoundedButton:
        button = RoundedButton(
            parent,
            text,
            command,
            fill=CTA_CONFIG,
            active=ACCENT,
            radius=22,
            font_size=font_size,
            icon=self.icon_sized(icon_name, icon_size),
            icon_position=icon_position,
            canvas_bg=PANEL,
        )
        button.place(x=x, y=y, width=width, height=height)
        return button

    def capture_sample(self, state: str) -> None:
        if state not in {"busy_stop", "typing_arrow", "ignored"}:
            self.notify(f"Invalid sample state: {state}")
            return
        if not self.config.get("region"):
            self.notify("Set a region before capturing samples.")
            return
        try:
            image = self.capture_region()
            target_dir = SAMPLES_DIR / state
            target_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            path = target_dir / f"{state}-{timestamp}.png"
            image.save(path)
            self.classifier.reload()
            with self.lock:
                self.last_current = image
                self.last_classification = self.classifier.classify(image)
                self.last_error = None
            self.render_preview(image)
            self.write_status()
            self.notify(f"Sample saved: {path}")
        except Exception as exc:
            with self.lock:
                self.last_error = str(exc)
            logging.exception("Could not capture sample")
            self.notify("Could not capture sample. Check turnlight.log.")

    def choose_alert_color(self) -> None:
        color = colorchooser.askcolor(
            color=alert_color(self.config),
            title="Choose alert overlay color",
            parent=self.root,
        )
        if color and color[1]:
            self.config["alert_color"] = color[1]
            save_config(self.config)
            self.notify(f"Alert color set to {color[1]}.")

    def toggle_personalization(self) -> None:
        if self.personalization_open:
            self.close_personalization()
            return
        self.show_personalization()

    def show_personalization(self) -> None:
        if not self.settings_open:
            self.show_settings()
        if self.personalization_panel is None:
            panel = RoundedPanel(
                self.shell,
                bg=PANEL,
                radius=22,
                border=BORDER,
                border_width=5,
                padding=14,
                width=PERSONALIZATION_WIDTH,
                height=PERSONALIZATION_HEIGHT,
            )
            panel.configure(width=PERSONALIZATION_WIDTH, height=PERSONALIZATION_HEIGHT)
            self.personalization_panel = panel
            self.build_personalization_contents(panel)
        self.personalization_open = True
        self.personalization_panel.pack(
            side="left",
            anchor="nw",
            padx=(PERSONALIZATION_GAP, 0),
            pady=(0, 0),
        )
        self.apply_window_layout("settings_personalization")

    def build_personalization_contents(self, panel: RoundedPanel) -> None:
        tk.Label(panel.inner, text="Personalization", bg=PANEL, fg=TEXT, font=("Segoe UI", 19, "bold")).place(x=8, y=-3)
        close = tk.Label(panel.inner, image=self.icon_sized("close", 18), bg=PANEL, cursor="hand2")
        close.place(x=360, y=4, width=24, height=24)
        close.bind("<Enter>", lambda _event: close.configure(bg="#35131d"))
        close.bind("<Leave>", lambda _event: close.configure(bg=PANEL))
        close.bind("<Button-1>", lambda _event: self.close_personalization())

        color_box = RoundedPanel(panel.inner, bg=PANEL_SOFT, radius=22, border=BORDER, border_width=5, padding=10, width=376, height=162)
        color_box.place(x=6, y=42, width=376, height=162)
        tk.Label(color_box.inner, text="Alert Color", bg=PANEL_SOFT, fg=TEXT, font=("Segoe UI", 12, "bold")).place(x=6, y=0)
        self._personalization_button(color_box.inner, "Dark", "dark-mode", lambda: self.set_alert_color("#000000"), 6, 34)
        self._personalization_button(color_box.inner, "Bright", "bright-mode", lambda: self.set_alert_color("#ffffff"), 124, 34)
        self._personalization_button(color_box.inner, "Custom", "palette", self.choose_alert_color, 242, 34)

        text_box = RoundedPanel(panel.inner, bg=PANEL_SOFT, radius=22, border=BORDER, border_width=5, padding=10, width=376, height=162)
        text_box.place(x=6, y=220, width=376, height=162)
        tk.Label(text_box.inner, text="Customize Alert Text", bg=PANEL_SOFT, fg=TEXT, font=("Segoe UI", 12, "bold")).place(x=6, y=0)
        self.alert_title_text = tk.StringVar(value=alert_title(self.config))
        self.alert_subtitle_text = tk.StringVar(value=alert_subtitle(self.config))
        self.alert_title_text.trace_add("write", lambda *_args: self.save_alert_text_from_inputs())
        self.alert_subtitle_text.trace_add("write", lambda *_args: self.save_alert_text_from_inputs())
        self._alert_text_input(text_box.inner, "Title", self.alert_title_text, ALERT_TITLE_MAX_CHARS, 6, 30, 352)
        self._alert_text_input(text_box.inner, "Subtitle", self.alert_subtitle_text, ALERT_SUBTITLE_MAX_CHARS, 6, 76, 352)
        reset_text = tk.Label(
            text_box.inner,
            text="To reset to default alert text click here.",
            bg=PANEL_SOFT,
            fg=TEXT,
            font=("Segoe UI", 8, "bold underline"),
            cursor="hand2",
        )
        reset_text.place(x=6, y=124)
        reset_text.bind("<Enter>", lambda _event: reset_text.configure(fg=HOVER_BORDER))
        reset_text.bind("<Leave>", lambda _event: reset_text.configure(fg=MUTED))
        reset_text.bind("<Button-1>", lambda _event: self.reset_alert_text())

        sound_box = RoundedPanel(panel.inner, bg=PANEL_SOFT, radius=22, border=BORDER, border_width=5, padding=10, width=376, height=140)
        sound_box.place(x=6, y=398, width=376, height=140)
        tk.Label(sound_box.inner, text="Customize sound", bg=PANEL_SOFT, fg=TEXT, font=("Segoe UI", 12, "bold")).place(x=6, y=8)
        browse = RoundedButton(
            sound_box.inner,
            "Browse",
            self.choose_custom_sound,
            fill=CTA_CONFIG,
            active=ACCENT,
            radius=20,
            font_size=11,
            icon=self.icon_sized("folder", 28),
            icon_position="left",
            canvas_bg=PANEL_SOFT,
        )
        browse.place(x=216, y=4, width=136, height=42)
        self.custom_sound_text = tk.StringVar(value=self.custom_sound_label())
        tk.Label(
            sound_box.inner,
            textvariable=self.custom_sound_text,
            bg=PANEL_SOFT,
            fg=MUTED,
            font=("Segoe UI", 8, "bold"),
            wraplength=198,
            justify="left",
        ).place(x=6, y=30)
        tk.Label(
            sound_box.inner,
            text="Browse opens C:\\Windows\\Media when available. Any local WAV can be used and looped.",
            bg=PANEL_SOFT,
            fg=MUTED,
            font=("Segoe UI", 8, "bold"),
            wraplength=338,
            justify="left",
        ).place(x=6, y=62)
        reset_link = tk.Label(
            sound_box.inner,
            text="To reset to default sound click here.",
            bg=PANEL_SOFT,
            fg=TEXT,
            font=("Segoe UI", 8, "bold underline"),
            cursor="hand2",
        )
        reset_link.place(x=6, y=98)
        reset_link.bind("<Enter>", lambda _event: reset_link.configure(fg=HOVER_BORDER))
        reset_link.bind("<Leave>", lambda _event: reset_link.configure(fg=MUTED))
        reset_link.bind("<Button-1>", lambda _event: self.reset_custom_sound())

    def _alert_text_input(
        self,
        parent: tk.Widget,
        label: str,
        variable: tk.StringVar,
        max_chars: int,
        x: int,
        y: int,
        width: int,
    ) -> tk.Entry:
        tk.Label(
            parent,
            text=f"{label} ({max_chars} max)",
            bg=PANEL_SOFT,
            fg=MUTED,
            font=("Segoe UI", 8, "bold"),
        ).place(x=x, y=y)
        field = RoundedPanel(
            parent,
            bg=CTA_CONFIG,
            radius=18,
            border=BORDER,
            border_width=3,
            padding=5,
            canvas_bg=PANEL_SOFT,
            width=width,
            height=34,
        )
        field.place(x=x + 90, y=y - 6, width=width - 90, height=34)
        validate = self.root.register(lambda proposed, limit=max_chars: self.validate_alert_text(proposed, limit))
        entry = tk.Entry(
            field.inner,
            textvariable=variable,
            bg=CTA_CONFIG,
            fg=TEXT,
            insertbackground=TEXT,
            selectbackground=HOVER_BORDER,
            selectforeground=BG,
            relief="flat",
            bd=0,
            highlightthickness=0,
            font=("Segoe UI", 10, "bold"),
            validate="key",
            validatecommand=(validate, "%P"),
        )
        entry.pack(fill="both", expand=True)
        entry.bind("<FocusIn>", lambda event: self.select_alert_text_entry(event.widget))
        entry.bind("<FocusOut>", lambda _event: self.normalize_alert_text_inputs())
        entry.bind("<Button-1>", lambda event: self.select_alert_text_entry_on_click(event))
        return entry

    def _personalization_button(
        self,
        parent: tk.Widget,
        text: str,
        icon_name: str,
        command: Callable[[], None],
        x: int,
        y: int,
    ) -> RoundedButton:
        button = RoundedButton(
            parent,
            text,
            command,
            fill=CTA_CONFIG,
            active=ACCENT,
            radius=22,
            font_size=11,
            icon=self.icon_sized(icon_name, 44 if icon_name == "dark-mode" else 48),
            icon_position="top",
            icon_y_offset=8,
            text_y_offset=8,
            canvas_bg=PANEL_SOFT,
        )
        button.place(x=x, y=y, width=108, height=94)
        return button

    def close_personalization(self, *, animate: bool = True) -> None:
        if not self.personalization_open and self.personalization_panel is None:
            return
        self.personalization_open = False
        if self.personalization_panel is not None:
            self.personalization_panel.pack_forget()
        if animate and not self.shutdown.is_set():
            self.apply_window_layout("settings" if self.settings_open else "compact")

    def validate_alert_text(self, proposed: str, max_chars: int) -> bool:
        return len(proposed) <= max_chars and "\r" not in proposed and "\n" not in proposed

    def select_alert_text_entry(self, widget: tk.Widget) -> None:
        if not isinstance(widget, tk.Entry):
            return
        widget.after_idle(lambda: (widget.select_range(0, tk.END), widget.icursor(tk.END)))

    def select_alert_text_entry_on_click(self, event: tk.Event) -> None:
        widget = event.widget
        if isinstance(widget, tk.Entry) and widget.focus_get() != widget:
            self.select_alert_text_entry(widget)

    def save_alert_text_from_inputs(self) -> None:
        if self.updating_alert_text:
            return
        title = self.alert_title_text.get() if self.alert_title_text is not None else DEFAULT_ALERT_TITLE
        subtitle = self.alert_subtitle_text.get() if self.alert_subtitle_text is not None else DEFAULT_ALERT_SUBTITLE
        self.config["alert_title"] = clean_alert_text(title, ALERT_TITLE_MAX_CHARS)
        self.config["alert_subtitle"] = clean_alert_text(subtitle, ALERT_SUBTITLE_MAX_CHARS)
        save_config(self.config)

    def normalize_alert_text_inputs(self) -> None:
        if self.alert_title_text is None or self.alert_subtitle_text is None:
            return
        title = alert_text_value(
            {"alert_title": self.alert_title_text.get()},
            "alert_title",
            DEFAULT_ALERT_TITLE,
            ALERT_TITLE_MAX_CHARS,
        )
        subtitle = alert_text_value(
            {"alert_subtitle": self.alert_subtitle_text.get()},
            "alert_subtitle",
            DEFAULT_ALERT_SUBTITLE,
            ALERT_SUBTITLE_MAX_CHARS,
            allow_empty=True,
        )
        self.updating_alert_text = True
        try:
            self.alert_title_text.set(title)
            self.alert_subtitle_text.set(subtitle)
        finally:
            self.updating_alert_text = False
        self.config["alert_title"] = title
        self.config["alert_subtitle"] = subtitle
        save_config(self.config)

    def reset_alert_text(self) -> None:
        self.config["alert_title"] = DEFAULT_ALERT_TITLE
        self.config["alert_subtitle"] = DEFAULT_ALERT_SUBTITLE
        save_config(self.config)
        self.updating_alert_text = True
        try:
            if self.alert_title_text is not None:
                self.alert_title_text.set(DEFAULT_ALERT_TITLE)
            if self.alert_subtitle_text is not None:
                self.alert_subtitle_text.set(DEFAULT_ALERT_SUBTITLE)
        finally:
            self.updating_alert_text = False
        self.notify("Custom alert text reset to default.")

    def set_alert_color(self, color: str) -> None:
        self.config["alert_color"] = color
        save_config(self.config)
        self.notify(f"Alert color set to {color}.")

    def choose_custom_sound(self) -> None:
        initial_dir = Path(r"C:\Windows\Media")
        path = filedialog.askopenfilename(
            parent=self.root,
            title="Choose alert sound",
            initialdir=str(initial_dir if initial_dir.exists() else Path.home()),
            filetypes=[
                ("Wave audio", "*.wav"),
            ],
        )
        if not path:
            return
        sound_path = Path(path)
        if sound_path.suffix.lower() != ".wav":
            self.notify("Only .wav files are supported for native custom alert sounds.")
            return
        if not sound_path.exists() or not sound_path.is_file():
            self.notify("Selected sound file was not found.")
            return
        self.config["custom_sound_path"] = str(sound_path)
        save_config(self.config)
        if self.custom_sound_text is not None:
            self.custom_sound_text.set(self.custom_sound_label())
        self.notify(f"Custom alert sound set: {sound_path.name}")

    def reset_custom_sound(self) -> None:
        self.config["custom_sound_path"] = None
        save_config(self.config)
        if self.custom_sound_text is not None:
            self.custom_sound_text.set(self.custom_sound_label())
        self.notify("Custom alert sound reset to default.")

    def custom_sound_label(self) -> str:
        path = self.config.get("custom_sound_path")
        if isinstance(path, str) and path:
            sound_path = Path(path)
            if sound_path.exists() and sound_path.suffix.lower() == ".wav":
                return f"Using WAV: {sound_path.name}"
            return "Saved sound is missing. Default system sound will be used."
        return "Using default system sound."

    def toggle_sound(self) -> None:
        enabled = not bool(self.config.get("sound_enabled", True))
        self.config["sound_enabled"] = enabled
        save_config(self.config)
        if hasattr(self, "sound_button"):
            self.sound_button.text = "Sound On" if enabled else "Sound Off"
            self.sound_button.set_icon(self.icon_sized("volume-on" if enabled else "volume-off", 24))
        self.notify(f"System sound {'enabled' if enabled else 'disabled'}.")

    def alert_screen_mode_label(self) -> tuple[str, str]:
        if str(self.config.get("alert_screen_mode", "multi")) == "primary":
            return "Principal Screen", "single-monitor"
        return "Multi-Screen", "monitor"

    def toggle_alert_screen_mode(self) -> None:
        current = str(self.config.get("alert_screen_mode", "multi"))
        self.config["alert_screen_mode"] = "primary" if current == "multi" else "multi"
        save_config(self.config)
        label, icon_name = self.alert_screen_mode_label()
        if hasattr(self, "screen_mode_button"):
            self.screen_mode_button.text = label
            self.screen_mode_button.set_icon(self.icon_sized(icon_name, 24))
            self.screen_mode_button._draw()
        self.notify(f"Alert screen mode: {label}.")

    def open_readme(self) -> None:
        readme_path = APP_DIR / "README.md"
        if not readme_path.exists():
            self.notify("README.md was not found.")
            return
        try:
            os.startfile(str(readme_path))
            self.notify("README opened.")
        except Exception:
            logging.exception("Could not open README")
            self.notify("Could not open README.md.")

    def open_samples_folder(self) -> None:
        SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(SAMPLES_DIR))
        except Exception:
            logging.exception("Could not open samples folder")
            self.notify("Could not open samples folder.")

    def reset_samples(self) -> None:
        removed = 0
        try:
            for state in ("busy_stop", "typing_arrow", "ignored"):
                folder = SAMPLES_DIR / state
                folder.mkdir(parents=True, exist_ok=True)
                for path in folder.iterdir():
                    if path.name == ".gitkeep":
                        continue
                    if path.is_file():
                        path.unlink()
                        removed += 1
            self.classifier.reload()
            self.write_status()
            self.notify(f"Samples reset. Removed {removed} files.")
        except Exception:
            logging.exception("Could not reset samples")
            self.notify("Could not reset samples.")

    def reload_samples(self) -> None:
        self.classifier.reload()
        self.notify("Samples reloaded.")

    def _ui_tick(self) -> None:
        with self.lock:
            running = self.running.is_set()
            error = self.last_error
            classification = self.last_classification

        valid_detection = classification is not None and classification.state in {"typing_arrow", "busy_stop"}
        if running:
            self.action_text.set("Watching")
            self.toggle_text.set("Pause")
        else:
            self.action_text.set("Paused")
            self.toggle_text.set("Start")

        if hasattr(self, "toggle_button") and self.toggle_button.text != self.toggle_text.get():
            self.toggle_button.text = self.toggle_text.get()
            self.toggle_button.set_icon(self.icon_sized("pause" if running else "play", 34))
            self.toggle_button._draw()

        if hasattr(self, "toggle_button"):
            self.toggle_button.set_enabled(running or valid_detection)

        if classification and classification.state == "typing_arrow":
            self.detection_text.set("Ready arrow detected")
        elif classification and classification.state == "busy_stop":
            self.detection_text.set("Busy detected")
        else:
            self.detection_text.set("No sample")

        if error:
            self.action_text.set("Error")

        show_alert = False
        with self.lock:
            if self.alert_pending and not self.alert_active:
                self.alert_pending = False
                self.alert_active = True
                show_alert = True
            elif self.alert_pending and self.alert_active:
                self.alert_pending = False

        if show_alert:
            self.show_alert_overlay()

        self.root.after(500, self._ui_tick)

    def _preview_tick(self) -> None:
        try:
            if self.config.get("region"):
                current = self.capture_region()
                classification = self.classifier.classify(current)
                with self.lock:
                    self.last_current = current
                    self.last_classification = classification
                    self.last_sample_at = time.time()
                    self.last_error = None
                self.render_preview(current)
                if not self.auto_start_attempted and classification.state in {"typing_arrow", "busy_stop"}:
                    self.auto_start_attempted = True
                    self.root.after(50, self.start_watching)
        except Exception as exc:
            with self.lock:
                self.last_error = str(exc)
        self.root.after(max(350, int(self.config["interval_ms"])), self._preview_tick)

    def render_preview(self, image: Image.Image) -> None:
        canvas_w = max(1, self.preview_canvas.winfo_width() - 2)
        canvas_h = max(1, self.preview_canvas.winfo_height() - 2)
        scale = min(canvas_w / max(1, image.width), canvas_h / max(1, image.height))
        new_size = (max(1, int(image.width * scale)), max(1, int(image.height * scale)))
        preview = image.resize(new_size, Image.Resampling.LANCZOS)
        self.preview_photo = ImageTk.PhotoImage(preview)

        self.preview_canvas.delete("all")
        x = self.preview_canvas.winfo_width() // 2
        y = self.preview_canvas.winfo_height() // 2
        self.preview_canvas.create_image(x, y, image=self.preview_photo)

        self.preview_canvas.configure(highlightbackground=BORDER)

    def write_status(self) -> None:
        with self.lock:
            now = time.time()
            status = {
                "running": self.running.is_set(),
                "region": self.config.get("region"),
                "last_classification": None
                if self.last_classification is None
                else {
                    "state": self.last_classification.state,
                    "confidence": self.last_classification.confidence,
                    "reason": self.last_classification.reason,
                },
                "stable_count": self.stable_count,
                "busy_streak": self.busy_streak,
                "arrow_streak": self.arrow_streak,
                "armed_after_busy": self.armed_after_busy,
                "last_watcher_state": self.last_watcher_state,
                "stable_samples": self.config["stable_samples"],
                "busy_stable_samples": self.config["busy_stable_samples"],
                "arrow_transition_samples": self.config["arrow_transition_samples"],
                "last_sample_at": self.last_sample_at,
                "last_alert_at": self.last_alert_at,
                "alert_suppressed": now < self.alert_suppressed_until,
                "alert_suppressed_until": self.alert_suppressed_until,
                "alert_suppression_reason": self.alert_suppression_reason,
                "last_visual_delta": self.last_visual_delta,
                "last_error": self.last_error,
            }
        try:
            STATUS_PATH.write_text(json.dumps(status, indent=2), encoding="utf-8")
        except Exception:
            logging.exception("Could not write status.json")

    def configure_region(self) -> None:
        self.pause_watching()
        self.auto_start_attempted = False
        monitors = all_display_monitors()
        if not monitors:
            self.notify("No monitors detected for region selection.")
            return

        padding = int(self.config.get("selection_padding", 0))
        overlays: list[dict[str, Any]] = []
        state: dict[str, Any] = {
            "start": None,
            "monitor": None,
            "canvas": None,
            "rect": None,
        }

        def destroy_overlays() -> None:
            for item in list(overlays):
                overlay = item["overlay"]
                try:
                    if overlay.winfo_exists():
                        overlay.destroy()
                except tk.TclError:
                    pass
            overlays.clear()

        def canvas_for_monitor(monitor: dict[str, Any]) -> tk.Canvas | None:
            for item in overlays:
                if item["monitor"] is monitor:
                    return item["canvas"]
            return None

        def on_press(_event: tk.Event) -> None:
            gx, gy = cursor_position()
            monitor = monitor_at_point(gx, gy, monitors)
            if monitor is None:
                return
            canvas = canvas_for_monitor(monitor)
            if canvas is None:
                return

            state["start"] = (gx, gy)
            state["monitor"] = monitor
            state["canvas"] = canvas
            lx, ly = global_to_local(gx, gy, monitor)
            if state["rect"] is not None:
                try:
                    state["canvas"].delete(state["rect"])
                except (AttributeError, tk.TclError):
                    pass
            state["rect"] = canvas.create_rectangle(lx, ly, lx, ly, outline=READY, width=3)

        def on_drag(_event: tk.Event) -> None:
            if state["start"] is None or state["rect"] is None or state["monitor"] is None or state["canvas"] is None:
                return
            gx, gy = cursor_position()
            x0, y0 = global_to_local(state["start"][0], state["start"][1], state["monitor"])
            x1, y1 = global_to_local(gx, gy, state["monitor"])
            state["canvas"].coords(state["rect"], x0, y0, x1, y1)

        def on_release(_event: tk.Event) -> None:
            if state["start"] is None or state["monitor"] is None:
                return

            end = cursor_position()
            region = region_from_points(state["start"], end, state["monitor"], padding)

            destroy_overlays()
            if region["width"] < 8 or region["height"] < 8:
                self.notify("Selection too small.")
                return

            self.config["region"] = region
            save_config(self.config)
            with self.lock:
                self.last_classification = None
                self.reset_transition_state()
                self.last_error = None
            self.write_status()
            self.notify(
                f"Region saved: {region['left']},{region['top']} {region['width']}x{region['height']}. "
                "Check the preview before starting."
            )

        for index, monitor in enumerate(monitors):
            overlay = tk.Toplevel(self.root)
            overlay.overrideredirect(True)
            overlay.attributes("-topmost", True)
            overlay.attributes("-alpha", 0.30)
            overlay.configure(bg="black")

            canvas = tk.Canvas(
                overlay,
                width=int(monitor["width"]),
                height=int(monitor["height"]),
                bg="black",
                highlightthickness=0,
                cursor="crosshair",
            )
            canvas.pack(fill="both", expand=True)
            canvas.create_text(
                28,
                28,
                text=f"Drag over the busy/stop button. Padding {padding}px. Esc cancels.",
                fill="white",
                anchor="nw",
                font=("Segoe UI", 20, "bold"),
            )

            overlay.bind("<Escape>", lambda _event: destroy_overlays())
            overlay.bind("<ButtonPress-1>", on_press)
            overlay.bind("<B1-Motion>", on_drag)
            overlay.bind("<ButtonRelease-1>", on_release)
            canvas.bind("<ButtonPress-1>", on_press)
            canvas.bind("<B1-Motion>", on_drag)
            canvas.bind("<ButtonRelease-1>", on_release)

            overlay.update_idletasks()
            hwnd = get_toplevel_hwnd(overlay)
            actual = set_window_rect(hwnd, monitor, topmost=True)
            logging.info("Selection overlay monitor=%s actual_window=%s", monitor, actual)
            overlays.append({"overlay": overlay, "canvas": canvas, "monitor": monitor})
            if index == 0:
                overlay.focus_force()

    def start_watching(self) -> None:
        if not self.config.get("region"):
            self.notify("Set a region first.")
            return

        with self.lock:
            classification = self.last_classification
        if classification is None or classification.state not in {"typing_arrow", "busy_stop"}:
            self.notify("Not started: no valid sample detected.")
            return

        try:
            current = self.capture_region()
            self.render_preview(current)
        except Exception as exc:
            logging.exception("Could not capture initial region")
            with self.lock:
                self.last_error = str(exc)
            self.notify("Could not capture region. Set the region again.")
            return

        with self.lock:
            self.reset_transition_state()
            self.last_classification = None
            self.last_error = None
        self.classifier.reload()
        self.running.set()
        self.write_status()
        self.notify("Watching. Classifying button state.")

    def toggle_watching(self) -> None:
        if self.running.is_set():
            self.pause_watching()
        else:
            self.start_watching()

    def pause_watching(self) -> None:
        self.running.clear()
        with self.lock:
            self.reset_transition_state()
        self.write_status()
        self.notify("Paused.")

    def close(self) -> None:
        self._save_window_position()
        self.shutdown.set()
        self.running.clear()
        if self.settings_open:
            self.hide_settings()
        self.close_personalization(animate=False)
        self.close_alert_overlay()
        self.write_status()
        self.root.destroy()

    def capture_region(self) -> Image.Image:
        region = self.config.get("region")
        if not isinstance(region, dict):
            raise RuntimeError("Region not configured")
        box = {
            "left": int(region["left"]),
            "top": int(region["top"]),
            "width": int(region["width"]),
            "height": int(region["height"]),
        }
        with mss.mss() as sct:
            shot = sct.grab(box)
            return Image.frombytes("RGB", shot.size, shot.rgb)

    def save_debug_capture(self) -> None:
        try:
            current = self.capture_region()
            current.save(DATA_DIR / "debug-current.png")
            classification = self.classifier.classify(current)
            self.classifier.save_debug(current, classification)
            with self.lock:
                self.last_classification = classification
                self.last_error = None
            self.notify(f"Debug saved. State: {classification.state} ({classification.confidence:.2f}).")
        except Exception as exc:
            with self.lock:
                self.last_error = str(exc)
            logging.exception("Could not save debug capture")
            self.notify("Could not save debug. Check turnlight.log.")
        finally:
            self.write_status()

    def reset_transition_state(self) -> None:
        self.stable_count = 0
        self.busy_streak = 0
        self.arrow_streak = 0
        self.armed_after_busy = False
        self.last_watcher_state = "unknown"

    def transition_snapshot(self) -> dict[str, Any]:
        return {
            "watcher_state": self.last_watcher_state,
            "armed_after_busy": self.armed_after_busy,
            "busy_streak": self.busy_streak,
            "arrow_streak": self.arrow_streak,
            "stable_count": self.stable_count,
        }

    def suppress_alerts_for(self, seconds: float, reason: str) -> None:
        until = time.time() + max(0.0, seconds)
        if until <= self.alert_suppressed_until and self.alert_suppression_reason == reason:
            return
        self.alert_suppressed_until = until
        self.alert_suppression_reason = reason
        self.reset_transition_state()
        logging.info("Suppressing alerts for %.1fs: %s", seconds, reason)

    def alert_is_suppressed(self) -> bool:
        if time.time() < self.alert_suppressed_until:
            return True
        if self.alert_suppression_reason is not None:
            self.alert_suppression_reason = None
        return False

    def system_view_reason(self) -> str | None:
        if task_view_hotkey_is_down():
            return "task_view_hotkey"
        return task_view_foreground_reason()

    def visual_interruption_reason(self, current: Image.Image, classification: Classification) -> str | None:
        if not self.armed_after_busy or self.last_current is None or classification.state != "typing_arrow":
            return None
        try:
            delta = image_delta(self.last_current, current)
        except Exception:
            logging.exception("Could not calculate visual delta")
            return None
        self.last_visual_delta = delta
        threshold = float(self.config.get("visual_interruption_threshold", 0.42))
        if delta >= threshold:
            return f"visual_interruption delta={delta:.3f}"
        return None

    def process_watcher_state(self, state: str) -> tuple[bool, dict[str, Any]]:
        should_alert = False
        if state == "busy_stop":
            self.busy_streak += 1
            self.arrow_streak = 0
            self.stable_count = self.busy_streak
            self.last_watcher_state = "busy_stop"
            if self.busy_streak >= int(self.config["busy_stable_samples"]):
                self.armed_after_busy = True
        elif state == "typing_arrow":
            self.busy_streak = 0
            if self.armed_after_busy:
                self.arrow_streak += 1
                self.stable_count = self.arrow_streak
                should_alert = self.arrow_streak >= int(self.config["arrow_transition_samples"])
            else:
                self.arrow_streak = 0
                self.stable_count = 0
            self.last_watcher_state = "typing_arrow"
        else:
            self.busy_streak = 0
            self.arrow_streak = 0
            self.stable_count = 0
            self.last_watcher_state = state

        return should_alert, self.transition_snapshot()

    def _watch_loop(self) -> None:
        while not self.shutdown.is_set():
            if not self.running.is_set():
                time.sleep(0.15)
                continue

            try:
                system_reason = self.system_view_reason()
                if system_reason is not None:
                    with self.lock:
                        self.suppress_alerts_for(float(self.config.get("system_view_suppression_seconds", 5)), system_reason)
                    self.write_status()
                    time.sleep(max(0.1, int(self.config["interval_ms"]) / 1000.0))
                    continue

                current = self.capture_region()
                classification = self.classifier.classify(current)
                should_alert = False

                with self.lock:
                    visual_reason = self.visual_interruption_reason(current, classification)
                    self.last_current = current
                    self.last_classification = classification
                    self.last_sample_at = time.time()
                    self.last_error = None
                    if visual_reason is not None:
                        self.suppress_alerts_for(
                            float(self.config.get("system_view_suppression_seconds", 5)),
                            visual_reason,
                        )
                        transition = self.transition_snapshot()
                    else:
                        should_alert, transition = self.process_watcher_state(classification.state)

                logging.info(
                    "Classified state: %s %.3f %s watcher=%s armed=%s busy=%s/%s arrow=%s/%s suppressed=%s reason=%s delta=%.3f",
                    classification.state,
                    classification.confidence,
                    classification.reason,
                    transition["watcher_state"],
                    transition["armed_after_busy"],
                    transition["busy_streak"],
                    self.config["busy_stable_samples"],
                    transition["arrow_streak"],
                    self.config["arrow_transition_samples"],
                    time.time() < self.alert_suppressed_until,
                    self.alert_suppression_reason,
                    self.last_visual_delta,
                )

                self.write_status()

                if should_alert:
                    now = time.time()
                    with self.lock:
                        suppressed = self.alert_is_suppressed()
                        if suppressed:
                            self.reset_transition_state()
                            logging.info("Alert suppressed before launch: %s", self.alert_suppression_reason)
                    if suppressed:
                        self.write_status()
                    elif now - self.last_alert_at >= float(self.config["cooldown_seconds"]):
                        self.last_alert_at = now
                        with self.lock:
                            self.reset_transition_state()
                            self.last_watcher_state = "typing_arrow"
                        self.launch_alert()
                        if bool(self.config["pause_after_alert"]):
                            self.running.clear()
                            self.notify("busy_stop -> arrow transition detected. Alert launched and watching paused.")
                        else:
                            self.notify("busy_stop -> arrow transition detected. Alert launched.")

            except Exception as exc:
                logging.exception("Watcher error")
                self.running.clear()
                with self.lock:
                    self.last_error = str(exc)
                    self.reset_transition_state()
                self.write_status()
                self.notify("Watching error. Check turnlight.log.")

            time.sleep(max(0.1, int(self.config["interval_ms"]) / 1000.0))

    def launch_alert(self) -> None:
        with self.lock:
            if self.alert_active or self.alert_pending:
                logging.info("Alert ignored because one is already active or pending.")
                return
            self.alert_pending = True
        self.notify("Alert scheduled.")

    def show_alert_overlay(self) -> None:
        try:
            monitors = monitors_for_alert(str(self.config.get("alert_screen_mode", "multi")))
            self.alert_windows = []
            overlay_color = alert_color(self.config)

            for monitor in monitors:
                overlay = tk.Toplevel(self.root)
                overlay.overrideredirect(True)
                overlay.configure(bg=overlay_color)
                overlay.attributes("-topmost", True)
                overlay.attributes("-alpha", 0.70)
                overlay.geometry(
                    f"{monitor['width']}x{monitor['height']}{monitor['left']:+d}{monitor['top']:+d}"
                )
                overlay.bind("<Escape>", lambda _event: self.close_alert_overlay())
                overlay.update_idletasks()
                hwnd = get_toplevel_hwnd(overlay)
                actual = set_window_rect(hwnd, monitor, topmost=True)
                logging.info("Alert overlay monitor=%s actual_window=%s", monitor, actual)
                overlay.lift()
                self.alert_windows.append(overlay)

            self._build_alert_dialog()
            if bool(self.config.get("sound_enabled", True)):
                self.start_alert_sound_loop()
            self.notify("Alert overlay launched.")
        except Exception:
            logging.exception("Could not launch alert overlay")
            self.close_alert_overlay()
            self.notify("Could not open alert overlay.")

    def _build_alert_dialog(self) -> None:
        screen = primary_monitor()
        width = 520
        height = 324
        left = int(screen["left"] + (screen["width"] - width) / 2)
        top = int(screen["top"] + (screen["height"] - height) / 2)

        dialog = tk.Toplevel(self.root)
        dialog.overrideredirect(True)
        dialog.configure(bg=BG)
        dialog.attributes("-topmost", True)
        dialog.geometry(f"{width}x{height}{left:+d}{top:+d}")
        dialog.bind("<Escape>", lambda _event: self.close_alert_overlay())
        dialog.bind("<Return>", lambda _event: self.close_alert_overlay())

        panel = RoundedPanel(dialog, bg=ALERT_CARD, radius=30, border=BORDER, border_width=6)
        panel.pack(fill="both", expand=True, padx=8, pady=8)

        big_icon = self.icon_cropped_sized("app-icon", 80)
        if big_icon is not None:
            tk.Label(panel.inner, image=big_icon, bg=ALERT_CARD).place(relx=0.5, y=12, anchor="n")
        title_text = alert_title(self.config)
        subtitle_text = alert_subtitle(self.config)
        title_font_size = 31
        if len(title_text) > 28:
            title_font_size = 25
        elif len(title_text) > 20:
            title_font_size = 28
        tk.Label(
            panel.inner,
            text=title_text,
            bg=ALERT_CARD,
            fg=TEXT,
            font=("Segoe UI", title_font_size, "bold"),
            wraplength=450,
            justify="center",
        ).place(relx=0.5, y=108, anchor="n")
        tk.Label(
            panel.inner,
            text=subtitle_text,
            bg=ALERT_CARD,
            fg=MUTED,
            font=("Segoe UI", 13, "bold"),
            wraplength=430,
            justify="center",
        ).place(relx=0.5, y=164, anchor="n")

        button = RoundedButton(
            panel.inner,
            "Done",
            self.close_alert_overlay,
            fill=ALERT_BUTTON,
            active=ALERT_BUTTON_HOVER,
            radius=20,
            font_size=21,
            canvas_bg=ALERT_CARD,
        )
        button.place(relx=0.5, y=238, width=314, height=74, anchor="center")

        self.alert_windows.append(dialog)
        dialog.update_idletasks()
        hwnd = get_toplevel_hwnd(dialog)
        set_window_rect(hwnd, {"left": left, "top": top, "width": width, "height": height}, topmost=True)
        apply_rounded_window(hwnd, width, height, 32)
        dialog.lift()
        dialog.focus_force()

    def close_alert_overlay(self) -> None:
        self.stop_alert_sound_loop()
        for window in list(self.alert_windows):
            try:
                if window.winfo_exists():
                    window.destroy()
            except tk.TclError:
                pass
        self.alert_windows = []
        with self.lock:
            self.alert_active = False
            self.alert_pending = False
        self.notify("Alert closed.")

    def start_alert_sound_loop(self) -> None:
        self.stop_alert_sound_loop()
        stop_event = threading.Event()
        self.alert_sound_stop = stop_event
        self.alert_sound_thread = threading.Thread(
            target=self._alert_sound_loop,
            args=(stop_event,),
            daemon=True,
        )
        self.alert_sound_thread.start()

    def stop_alert_sound_loop(self) -> None:
        if self.alert_sound_stop is not None:
            self.alert_sound_stop.set()
        self.alert_sound_stop = None
        try:
            import winsound

            winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:
            pass

    def _alert_sound_loop(self, stop_event: threading.Event) -> None:
        while not stop_event.is_set() and not self.shutdown.is_set():
            self.play_alert_beep()
            stop_event.wait(2.0)

    def play_alert_beep(self) -> None:
        try:
            import winsound

            sound_path = self.config.get("custom_sound_path")
            if isinstance(sound_path, str) and sound_path:
                path = Path(sound_path)
                if path.exists() and path.is_file() and path.suffix.lower() == ".wav":
                    winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
                    return
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except Exception:
            try:
                ctypes.windll.user32.MessageBeep(0x00000030)
            except Exception:
                pass


def main() -> None:
    ensure_user_data_dirs()
    handler = RotatingFileHandler(LOG_PATH, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=[handler])
    set_dpi_awareness()
    set_app_user_model_id()
    app = TurnlightApp()
    app.start()


if __name__ == "__main__":
    main()
