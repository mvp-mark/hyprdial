"""Date and time, language, default apps and system info (no GTK, testable).

Time zone, NTP and language go through timedatectl/localectl, which ask for the password through polkit (the
Omarchy shell shows the prompt). Default apps go through `omarchy default`, the same commands as Omarchy's menu.
"""
from __future__ import annotations

import os
import platform
from pathlib import Path

from . import core

# ------------------------------------------------------------------ date and time
def time_settings() -> dict:
    """{"timezone": "America/Manaus", "ntp": True, "can_ntp": True, "synced": True}"""
    fields = dict(line.split("=", 1) for line in core.out(["timedatectl", "show"]).splitlines() if "=" in line)
    return {"timezone": fields.get("Timezone", ""), "ntp": fields.get("NTP") == "yes",
            "can_ntp": fields.get("CanNTP") == "yes", "synced": fields.get("NTPSynchronized") == "yes"}


def timezones() -> list[str]:
    return [t for t in core.out(["timedatectl", "list-timezones"]).splitlines() if t]


def set_timezone(zone: str) -> tuple[bool, str]:
    return result(core.run(["timedatectl", "set-timezone", zone], timeout=120))


def set_ntp(on: bool) -> tuple[bool, str]:
    return result(core.run(["timedatectl", "set-ntp", "true" if on else "false"], timeout=120))


def refresh_clock() -> None:
    core.run(["omarchy-shell", "-q", "omarchy.clock", "refresh"])


# ------------------------------------------------------------------ language
def locale_settings() -> tuple[str, list[str]]:
    """(current LANG, locales generated on this system)."""
    current = ""
    for line in core.out(["localectl", "status"]).splitlines():
        line = line.strip()
        if "LANG=" in line:
            current = line.split("LANG=", 1)[1].split()[0]
    available = [loc for loc in core.out(["localectl", "list-locales"]).splitlines() if loc and loc != "C.UTF-8"]
    return current, available


def set_locale(lang: str) -> tuple[bool, str]:
    return result(core.run(["localectl", "set-locale", f"LANG={lang}"], timeout=120))


def result(r) -> tuple[bool, str]:
    if r is None:
        return False, ""
    return r.returncode == 0, (r.stderr or r.stdout).strip()


# ------------------------------------------------------------------ default apps
APP_DIRS = [Path("/usr/share/applications"), core.HOME / ".local/share/applications"]

# kind -> [(omarchy name, label, how to tell it's installed: "bin:<cmd>" or "app:<desktop file>")]
DEFAULT_APPS = {
    "browser": [("chromium", "Chromium", "app:chromium.desktop"), ("chrome", "Chrome", "app:google-chrome.desktop"),
                ("brave", "Brave", "app:brave-browser.desktop"), ("brave-origin", "Brave Origin", "app:brave-origin.desktop"),
                ("edge", "Edge", "app:microsoft-edge.desktop"), ("firefox", "Firefox", "app:firefox.desktop"),
                ("zen", "Zen", "app:zen.desktop")],
    "terminal": [("alacritty", "Alacritty", "bin:alacritty"), ("foot", "Foot", "bin:foot"),
                 ("ghostty", "Ghostty", "bin:ghostty"), ("kitty", "Kitty", "bin:kitty")],
    "editor": [("nvim", "Neovim", "bin:nvim"), ("code", "VSCode", "bin:code"), ("cursor", "Cursor", "bin:cursor"),
               ("zed", "Zed", "bin:zeditor"), ("sublime_text", "Sublime Text", "bin:sublime_text"),
               ("helix", "Helix", "bin:helix"), ("vim", "Vim", "bin:vim"), ("emacs", "Emacs", "bin:emacs")],
}


CURRENT_ALIASES = {"zeditor": "zed"}  # `omarchy default editor` prints the command, set takes "zed"


def installed(check: str) -> bool:
    how, name = check.split(":", 1)
    if how == "bin":
        return core.have(name)
    return any((d / name).exists() for d in APP_DIRS)


def default_apps() -> dict[str, tuple[list[tuple[str, str]], str]]:
    """kind -> (installed choices as (name, label), current name). Kinds without choices are left out."""
    apps = {}
    for kind, choices in DEFAULT_APPS.items():
        available = [(name, label) for name, label, check in choices if installed(check)]
        if available:
            current = core.out(["omarchy", "default", kind])
            apps[kind] = (available, CURRENT_ALIASES.get(current, current))
    return apps


def set_default_app(kind: str, name: str) -> tuple[bool, str]:
    return result(core.run(["omarchy", "default", kind, name], timeout=30))


# ------------------------------------------------------------------ about
def read_first(path: str, prefix: str) -> str:
    try:
        for line in Path(path).read_text().splitlines():
            if line.startswith(prefix):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return ""


def memory_gib() -> str:
    kib = read_first("/proc/meminfo", "MemTotal").split()
    return f"{int(kib[0]) / 1024 ** 2:.1f} GiB" if kib and kib[0].isdigit() else ""


def about() -> list[tuple[str, str]]:
    """(key, value) pairs; keys are translated by the page."""
    info = [("omarchy", core.out(["omarchy", "version"])), ("hostname", platform.node()),
            ("kernel", platform.release()), ("cpu", read_first("/proc/cpuinfo", "model name")),
            ("cores", str(os.cpu_count() or "")), ("memory", memory_gib())]
    return [(k, v) for k, v in info if v]


UPDATE_COMMAND = ["omarchy-launch-floating-terminal-with-presentation", "omarchy-update"]
