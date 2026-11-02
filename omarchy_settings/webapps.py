"""Web apps (no GTK, testable): the launchers made by `omarchy webapp install`, listed, added and removed."""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from pathlib import Path

from . import core
from .apps import parse_desktop
from .system import result

DESKTOP_DIR = core.HOME / ".local/share/applications"
ICON_DIR = core.HOME / ".local/share/icons/hicolor/256x256/apps"
LAUNCHERS = ("omarchy-launch-webapp", "omarchy-webapp-handler")


@dataclass
class WebApp:
    name: str  # file name without .desktop: what omarchy-webapp-remove takes
    title: str
    url: str
    icon: str  # icon name, or a file path when the icon sits in Omarchy's icon folder


def icon_for(value: str, icon_dir: Path = ICON_DIR) -> str:
    """A freshly installed icon isn't in GTK's icon cache yet: prefer the file when there is one."""
    path = icon_dir / f"{value}.png"
    return str(path) if value and "/" not in value and path.is_file() else value


def url_of(exec_line: str) -> str:
    try:
        args = shlex.split(exec_line)
    except ValueError:
        args = exec_line.split()
    return next((a for a in args if re.match(r"https?://", a)), "")


def web_apps(directory: Path = DESKTOP_DIR, icon_dir: Path = ICON_DIR) -> list[WebApp]:
    found = []
    for f in sorted(directory.glob("*.desktop")) if directory.is_dir() else []:
        try:
            fields = parse_desktop(f.read_text(errors="replace"))
        except OSError:
            continue
        exec_line = fields.get("Exec", "")
        if any(launcher in exec_line for launcher in LAUNCHERS):
            found.append(
                WebApp(
                    f.stem, fields.get("Name", f.stem), url_of(exec_line), icon_for(fields.get("Icon", ""), icon_dir)
                )
            )
    return sorted(found, key=lambda a: a.title.casefold())


def check(name: str, url: str, existing: list[WebApp]) -> str | None:
    """Problem with the form, if any (the same rules as omarchy-webapp-install, before running it)."""
    if not name:
        return "name"
    if "/" in name:
        return "slash"
    if any(a.name == name for a in existing):
        return "exists"
    if not url or re.search(r"\s", url):
        return "url"
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", url) and not re.match(r"^https?://", url, re.I):
        return "url"  # javascript:, file:, data:… are refused
    return None


def install(name: str, url: str, icon: str = "") -> tuple[bool, str]:
    """An empty icon makes Omarchy fetch the site's own icon."""
    return result(core.run(["omarchy-webapp-install", name, url, icon], timeout=60))


def remove(name: str) -> tuple[bool, str]:
    # no notification: the window already shows a message
    return result(core.run(["env", "OMARCHY_REMOVE_NOTIFY=false", "omarchy-webapp-remove", name], timeout=30))
