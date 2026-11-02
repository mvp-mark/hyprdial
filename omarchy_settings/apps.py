"""Default apps (no GTK, testable).

Browser, terminal and editor go through `omarchy default`, the same commands as Omarchy's menu. File manager, PDF
and image apps go through xdg-mime, choosing among the installed apps that declare they open that type.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from . import core
from .system import result

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


# ------------------------------------------------------------------ apps by file type
# kind -> MIME types set together; the first one picks the candidates and the current app
MIME_KINDS = {"files": ["inode/directory"], "pdf": ["application/pdf"],
              "images": ["image/png", "image/jpeg", "image/webp", "image/gif"]}


@dataclass
class DesktopApp:
    id: str  # desktop file name, e.g. org.gnome.Evince.desktop
    name: str
    mime: list[str]
    hidden: bool  # NoDisplay or Hidden: helpers that aren't offered unless already in use


def data_dirs() -> list[Path]:
    """applications/ folders by priority, lowest first, so later ones override earlier ones."""
    system = os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    dirs = [Path(d) / "applications" for d in reversed(system.split(":")) if d]
    return dirs + [core.HOME / ".local/share/applications"]


def parse_desktop(text: str) -> dict[str, str]:
    """Keys of the [Desktop Entry] group, untranslated."""
    fields, inside = {}, False
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("["):
            inside = line == "[Desktop Entry]"
        elif inside and "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            fields.setdefault(key.strip(), value.strip())
    return fields


def desktop_apps(dirs: list[Path] | None = None) -> dict[str, DesktopApp]:
    apps = {}
    for directory in dirs if dirs is not None else data_dirs():
        try:
            files = sorted(directory.glob("*.desktop"))
        except OSError:
            continue
        for f in files:
            try:
                fields = parse_desktop(f.read_text(errors="replace"))
            except OSError:
                continue
            hidden = fields.get("NoDisplay") == "true" or fields.get("Hidden") == "true"
            apps[f.name] = DesktopApp(f.name, fields.get("Name", f.stem),
                                      [m for m in fields.get("MimeType", "").split(";") if m], hidden)
    return apps


def mime_choices(kind: str, apps: dict[str, DesktopApp] | None = None) -> tuple[list[tuple[str, str]], str]:
    """(choices as (desktop id, label), current desktop id) for a kind of file."""
    apps = desktop_apps() if apps is None else apps
    primary = MIME_KINDS[kind][0]
    current = core.out(["xdg-mime", "query", "default", primary])
    found = [a for a in apps.values() if primary in a.mime and (not a.hidden or a.id == current)]
    found.sort(key=lambda a: a.name.casefold())
    names = [a.name for a in found]
    # two apps called "Document Viewer": tell them apart by their file name (org.gnome.Evince -> Evince)
    choices = [(a.id, a.name if names.count(a.name) == 1 else f"{a.name} ({a.id.removesuffix('.desktop').split('.')[-1]})")
               for a in found]
    return choices, current


def set_mime_default(kind: str, desktop_id: str) -> tuple[bool, str]:
    return result(core.run(["xdg-mime", "default", desktop_id, *MIME_KINDS[kind]]))
