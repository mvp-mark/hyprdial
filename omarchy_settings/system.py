"""Date and time, language, notifications and system info (no GTK, testable).

Time zone, NTP and language go through timedatectl/localectl, which ask for the password through polkit (the
Omarchy shell shows the prompt).
"""

from __future__ import annotations

import json
import os
import platform
import re
from pathlib import Path

from . import core, host


# ------------------------------------------------------------------ date and time
def time_settings() -> dict:
    """{"timezone": "America/Manaus", "ntp": True, "can_ntp": True, "synced": True}"""
    fields = dict(line.split("=", 1) for line in core.out(["timedatectl", "show"]).splitlines() if "=" in line)
    return {
        "timezone": fields.get("Timezone", ""),
        "ntp": fields.get("NTP") == "yes",
        "can_ntp": fields.get("CanNTP") == "yes",
        "synced": fields.get("NTPSynchronized") == "yes",
    }


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


LOCALE_GEN = Path("/etc/locale.gen")
LOCALE_ARCHIVE = Path("/usr/lib/locale/locale-archive")  # rewritten by locale-gen
LOCALE_NAME = re.compile(r"[A-Za-z0-9_.@-]+")


def _locale_key(name: str) -> str:
    """pt_BR.UTF-8 and pt_BR.utf8 are the same locale."""
    return name.lower().replace(".utf-8", "").replace(".utf8", "")


def same_locale(a: str, b: str) -> bool:
    return _locale_key(a) == _locale_key(b)


def keyboard_layout() -> str:
    """Hyprland's first keyboard layout ('br' from 'br,us'), or ''."""
    try:
        option = json.loads(core.out(["hyprctl", "getoption", "input:kb_layout", "-j"]) or "{}")
    except ValueError:
        return ""
    value = option.get("str", "") if isinstance(option, dict) else ""
    return value.split(",")[0].strip().lower()


# Layouts whose locale isn't simply xx_XX (de -> de_DE, fr -> fr_FR, ...)
LAYOUT_LOCALES = {
    "us": "en_US", "gb": "en_GB", "br": "pt_BR", "jp": "ja_JP", "kr": "ko_KR", "cn": "zh_CN", "tw": "zh_TW",
    "se": "sv_SE", "dk": "da_DK", "no": "nb_NO", "ua": "uk_UA", "cz": "cs_CZ", "gr": "el_GR", "il": "he_IL",
    "ee": "et_EE", "latam": "es_MX", "ca": "fr_CA", "ch": "de_CH", "at": "de_AT", "be": "fr_BE",
}  # fmt: skip


def suggest_locale(layout: str, names: list[str]) -> str:
    """The locale a keyboard layout points at (br -> pt_BR.UTF-8), if it is among names; else ''."""
    if not re.fullmatch(r"[a-z]+", layout):
        return ""
    base = LAYOUT_LOCALES.get(layout, f"{layout}_{layout.upper()}")
    return next((n for n in names if same_locale(n, base + ".UTF-8")), "")


def installable_locales(generated: list[str], locale_gen: Path = LOCALE_GEN) -> list[str]:
    """UTF-8 locales listed (commented out) in /etc/locale.gen that aren't generated yet."""
    try:
        text = locale_gen.read_text(errors="replace")
    except OSError:
        return []
    have = {_locale_key(g) for g in generated}
    found = []
    for line in text.splitlines():
        m = re.fullmatch(r"#\s?(\S+)\s+UTF-8\s*", line)
        if m and LOCALE_NAME.fullmatch(m.group(1)) and _locale_key(m.group(1)) not in have:
            found.append(m.group(1))
    return sorted(set(found))


def locale_description(name: str, locales_dir: Path = Path("/usr/share/i18n/locales")) -> str:
    """'Brazilian Portuguese (Brazil)' from glibc's locale sources; '' when there's none."""
    base = re.sub(r"\.utf-?8", "", name, flags=re.IGNORECASE)
    try:
        text = (locales_dir / base).read_text(errors="replace")
    except (OSError, ValueError):
        return ""
    fields = dict(re.findall(r'^(language|territory)\s+"([^"]*)"', text, re.MULTILINE))
    language, territory = fields.get("language", ""), fields.get("territory", "")
    return f"{language} ({territory})" if language and territory else language


def install_locale_command(name: str) -> list[str]:
    """Uncomments the locale in /etc/locale.gen and runs locale-gen, with sudo in a visible terminal."""
    if not LOCALE_NAME.fullmatch(name):
        raise ValueError(name)
    pattern = name.replace(".", "\\.")  # the only character in LOCALE_NAME that sed treats specially
    return host.terminal_command(f"sudo sed -i 's/^#\\s\\?\\({pattern} UTF-8\\)/\\1/' {LOCALE_GEN} && sudo locale-gen")


def result(r) -> tuple[bool, str]:
    if r is None:
        return False, ""
    return r.returncode == 0, (r.stderr or r.stdout).strip()


# ------------------------------------------------------------------ notifications
def dnd() -> bool | None:
    state = core.out(["omarchy-shell", "notifications", "isDnd"])
    return {"on": True, "off": False}.get(state)


def set_dnd(on: bool) -> bool:
    ok = core.out(["omarchy-shell", "notifications", "setDnd", "on" if on else "off"]) == ("on" if on else "off")
    core.run(["omarchy-shell", "-q", "omarchy.indicators", "refresh"])
    return ok


def show_history() -> None:
    core.run(["omarchy-shell", "notifications", "showHistory"])


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
    return f"{int(kib[0]) / 1024**2:.1f} GiB" if kib and kib[0].isdigit() else ""


def about() -> list[tuple[str, str]]:
    """(key, value) pairs; keys are translated by the page."""
    info = [
        ("omarchy", core.out(["omarchy", "version"])),
        ("hostname", platform.node()),
        ("kernel", platform.release()),
        ("cpu", read_first("/proc/cpuinfo", "model name")),
        ("cores", str(os.cpu_count() or "")),
        ("memory", memory_gib()),
    ]
    return [(k, v) for k, v in info if v]


# ------------------------------------------------------------------ this app
PACKAGE = "omarchy-settings-gui"
RELEASES_URL = "https://github.com/mvp-mark/omarchy-settings/releases"
LATEST_API = "https://api.github.com/repos/mvp-mark/omarchy-settings/releases/latest"
PACKAGE_DIR = Path("/usr/share") / PACKAGE
LOCAL_DIR = Path.home() / ".local/share/omarchy-settings"  # where install.sh puts it


HERE = Path(__file__).resolve().parent


def app_location(here: Path = HERE) -> str:
    """'package', 'local' (install.sh) or 'source' (run from a checkout)."""
    if here.parent == PACKAGE_DIR:
        return "package"
    if here.parent == LOCAL_DIR:
        return "local"
    return "source"


def other_copies(location: str) -> list[str]:
    """The other installed copies, besides the one running; the launcher opens only one of them."""
    others = []
    if location != "package" and core.out(["pacman", "-Q", PACKAGE]):
        others.append("package")
    if location != "local" and (LOCAL_DIR / "omarchy_settings").is_dir():
        others.append("local")
    return others


def latest_release() -> str:
    """Version of the newest release on GitHub ('0.6.0'), or '' offline."""
    try:
        data = json.loads(core.out(["curl", "-fsS", "--max-time", "5", LATEST_API], timeout=8) or "{}")
    except ValueError:
        return ""
    tag = data.get("tag_name", "") if isinstance(data, dict) else ""
    return tag[1:] if tag.startswith("v") else ""


def is_newer(candidate: str, current: str) -> bool:
    def parts(v: str) -> tuple[int, ...]:
        return tuple(int(x) for x in re.findall(r"\d+", v))

    return bool(candidate) and parts(candidate) > parts(current)


PRINTERS_URL = "http://localhost:631/printers/"  # CUPS web interface
UPDATE_COMMAND = ["omarchy-launch-floating-terminal-with-presentation", "omarchy-update"]
SNAPSHOT_COMMAND = ["omarchy-launch-floating-terminal-with-presentation", "omarchy-snapshot", "create"]


def update_status() -> tuple[str | None, str]:
    """("available", "omarchy 4.0.6-1 -> 4.0.7-1"), ("current", "") or (None, "") when it can't tell.

    omarchy-update-available lists the updates and exits 0, or says it's up to date and exits 1."""
    r = core.run(["omarchy-update-available"], timeout=60)
    if r is None:
        return None, ""
    if r.returncode == 0 and r.stdout.strip():
        return "available", r.stdout.strip().splitlines()[0]
    if r.returncode == 1 and "up to date" in r.stdout:
        return "current", ""
    return None, ""


def can_snapshot() -> bool:
    return core.have("snapper") and core.have("omarchy-snapshot")
