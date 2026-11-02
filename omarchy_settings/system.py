"""Date and time, language, notifications and system info (no GTK, testable).

Time zone, NTP and language go through timedatectl/localectl, which ask for the password through polkit (the
Omarchy shell shows the prompt).
"""

from __future__ import annotations

import os
import platform
import re
from pathlib import Path

from . import core


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
TERMINAL = "omarchy-launch-floating-terminal-with-presentation"
LOCALE_NAME = re.compile(r"[A-Za-z0-9_.@-]+")


def _locale_key(name: str) -> str:
    """pt_BR.UTF-8 and pt_BR.utf8 are the same locale."""
    return name.lower().replace(".utf-8", "").replace(".utf8", "")


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
    return [TERMINAL, f"sudo sed -i 's/^#\\s\\?\\({pattern} UTF-8\\)/\\1/' {LOCALE_GEN} && sudo locale-gen"]


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
