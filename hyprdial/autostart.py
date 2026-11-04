"""Startup apps (no GTK, testable).

Two sources: XDG autostart entries (system ones in /etc/xdg/autostart, the user's in ~/.config/autostart), turned
off with a user file that says Hidden=true, as the XDG spec has it; and the user's own commands, written to the
generated file (core.on_start_call). Commands in the user's startup file (Omarchy's ~/.config/hypr/autostart.lua,
or hyprland.lua elsewhere) are read only.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from . import core, host
from .apps import parse_desktop

USER_DIR = core.HOME / ".config/autostart"
AUTOSTART_LUA = core.HOME / ".config/hypr/autostart.lua"
OVERRIDE = "[Desktop Entry]\nHidden=true\n"  # turns a system entry off for this user only


def system_dirs() -> list[Path]:
    dirs = os.environ.get("XDG_CONFIG_DIRS") or "/etc/xdg"
    return [Path(d) / "autostart" for d in reversed(dirs.split(":")) if d]


def desktops() -> set[str]:
    return {d for d in (os.environ.get("XDG_CURRENT_DESKTOP") or "Hyprland").split(":") if d}


def applies(fields: dict[str, str], current: set[str]) -> bool:
    only = {d for d in fields.get("OnlyShowIn", "").split(";") if d}
    never = {d for d in fields.get("NotShowIn", "").split(";") if d}
    return (not only or bool(only & current)) and not (never & current)


@dataclass
class Entry:
    id: str  # file name
    name: str
    comment: str
    enabled: bool
    system: bool  # there is a system file (the user's file, if any, overrides it)


def read(path: Path) -> dict[str, str] | None:
    try:
        return parse_desktop(path.read_text(errors="replace"))
    except OSError:
        return None


def entries(
    user_dir: Path = USER_DIR, sys_dirs: list[Path] | None = None, current: set[str] | None = None
) -> list[Entry]:
    current = desktops() if current is None else current
    found: dict[str, tuple[dict, bool]] = {}
    for directory in system_dirs() if sys_dirs is None else sys_dirs:
        for f in sorted(directory.glob("*.desktop")) if directory.is_dir() else []:
            fields = read(f)
            if fields is not None:
                found[f.name] = (fields, True)
    for f in sorted(user_dir.glob("*.desktop")) if user_dir.is_dir() else []:
        fields = read(f)
        if fields is not None:
            base, system = found.get(f.name, ({}, False))
            found[f.name] = ({**base, **fields}, system)  # a bare Hidden=true override keeps the system's name
    result = []
    for file, (fields, system) in found.items():
        if fields.get("Type", "Application") != "Application" or not applies(fields, current):
            continue
        enabled = fields.get("Hidden") != "true" and fields.get("X-GNOME-Autostart-enabled") != "false"
        result.append(
            Entry(file, fields.get("Name", file.removesuffix(".desktop")), fields.get("Comment", ""), enabled, system)
        )
    return sorted(result, key=lambda e: e.name.casefold())


def set_key(text: str, key: str, value: str | None) -> str:
    """Sets (or removes, with None) a key of the [Desktop Entry] group, keeping everything else."""
    lines, out, inside, done = text.splitlines(), [], False, False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("["):
            if inside and not done and value is not None:
                at = len(out)
                while at and not out[at - 1].strip():
                    at -= 1  # before the blank lines that end the group
                out.insert(at, f"{key}={value}")
                done = True
            inside = stripped == "[Desktop Entry]"
        elif inside and re.match(rf"{re.escape(key)}\s*=", stripped):
            if value is not None and not done:
                out.append(f"{key}={value}")
                done = True
            continue
        out.append(line)
    if inside and not done and value is not None:
        out.append(f"{key}={value}")
    return "\n".join(out) + "\n"


def set_enabled(entry: Entry, on: bool, user_dir: Path = USER_DIR) -> None:
    user_file = user_dir / entry.id
    text = user_file.read_text() if user_file.exists() else None
    if on:
        if text is None:
            return
        if entry.system and text.strip() == OVERRIDE.strip():
            user_file.unlink()  # only our override was there: back to the system file
        else:
            text = set_key(text, "Hidden", None)
            user_file.write_text(set_key(text, "X-GNOME-Autostart-enabled", None))
    else:
        user_dir.mkdir(parents=True, exist_ok=True)
        user_file.write_text(OVERRIDE if text is None else set_key(text, "Hidden", "true"))


# ------------------------------------------------------------------ commands
STARTUP_CALL = re.compile(r"(?<![\w.])(?:o\.(?:launch|exec)_on_start|hl\.exec_cmd)\(\s*(['\"])(.*?)\1\s*\)")


def startup_file() -> Path:
    return AUTOSTART_LUA if host.is_omarchy() else core.HYPR_MAIN


def lua_commands(path: Path | None = None) -> list[str]:
    """Uncommented o.launch_on_start / o.exec_on_start / hl.exec_cmd calls of the user's startup file."""
    path = startup_file() if path is None else path
    try:
        text = path.read_text()
    except OSError:
        return []
    found = []
    for line in text.splitlines():
        if line.strip().startswith("--"):
            continue  # commented out; "--" inside a command (foo --bar) is not a comment
        m = STARTUP_CALL.search(line)
        if m:
            found.append(m.group(2))
    return found


def render_extras(extras: dict) -> list[str]:
    commands = [c for c in extras.get("autostart", []) if isinstance(c, str) and c.strip()]
    if not commands:
        return []
    return ["", "-- Startup apps"] + [core.on_start_call(c) for c in commands]


def valid_command(text: str) -> str | None:
    text = text.strip()
    return text if text and not any(ord(c) < 32 for c in text) else None
