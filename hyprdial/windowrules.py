"""Window rules (no GTK, testable): what happens when an app's window opens (float, size, workspace, opacity…).

The app's rules live in the state (extras["window_rules"]) and go to the generated file as hl.window_rule calls
(o.window on Omarchy, its wrapper). Rules already in the user's .lua files are read, to be shown, never changed.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from . import core, host
from .i18n import _
from .keybinds import CONFIG_DIR, find_calls

EFFECTS = ("float", "center", "size", "workspace", "silent", "opacity", "pin", "fullscreen", "maximize", "idle")


@dataclass(frozen=True)
class Window:
    app: str  # class
    title: str


def open_windows() -> list[Window]:
    """The open windows' apps, one per class, from `hyprctl clients -j`."""
    try:
        data = json.loads(core.out(["hyprctl", "clients", "-j"]))
    except (ValueError, TypeError):
        return []
    seen: dict[str, Window] = {}
    for c in data if isinstance(data, list) else []:
        app = str(c.get("class") or c.get("initialClass") or "") if isinstance(c, dict) else ""
        if app and app not in seen:
            seen[app] = Window(app, str(c.get("title") or ""))
    return sorted(seen.values(), key=lambda w: w.app.casefold())


def problem(rule: dict) -> str | None:
    """Why a rule can't be saved, or None."""
    app = str(rule.get("class", "")).strip()
    if not app or any(ord(c) < 32 for c in app):
        return _("Choose an app or type its class.")
    if not any(rule.get(k) for k in EFFECTS if k != "silent"):
        return _("Choose at least one thing to do.")
    size = rule.get("size")
    if size and not (isinstance(size, list) and len(size) == 2 and all(isinstance(v, int) and v > 0 for v in size)):
        return _("The size must be two positive numbers.")
    if rule.get("pin") and not rule.get("float"):
        return _("Only floating windows can be shown on every workspace.")
    workspace = str(rule.get("workspace") or "")
    if workspace and not re.fullmatch(r"[1-9]\d?|special(:\w+)?", workspace):
        return _("The workspace must be a number from 1 to 99.")
    opacity = rule.get("opacity")
    if opacity is not None and not (isinstance(opacity, (int, float)) and 0.1 <= opacity <= 1):
        return _("The opacity must be between 10% and 100%.")
    return None


def effects_lua(rule: dict) -> list[str]:
    fields = []
    for key in ("float", "center", "pin", "fullscreen", "maximize"):
        if rule.get(key):
            fields.append(f"{key} = true")
    if rule.get("size"):
        w, h = rule["size"]
        fields.append(f"size = {{ {w}, {h} }}")
    if rule.get("workspace"):
        suffix = " silent" if rule.get("silent") else ""
        fields.append(f"workspace = {core.lua(str(rule['workspace']) + suffix)}")
    if rule.get("opacity") is not None:
        fields.append(f"opacity = {core.lua(core.fmt(float(rule['opacity'])))}")
    if rule.get("idle"):
        fields.append('idle_inhibit = "fullscreen"')
    return fields


def match_regex(app: str) -> str:
    """The class as an exact-match regex; only regex metacharacters are escaped (org.gnome.Calculator)."""
    return "^(" + re.sub(r"([.^$*+?()\[\]{}|\\])", r"\\\1", app) + ")$"


def rule_call(rule: dict) -> str:
    match = f"{{ class = {core.lua(match_regex(rule['class']))} }}"
    effects = ", ".join(effects_lua(rule))
    if host.is_omarchy():
        return f"pcall(function() o.window({match}, {{ {effects} }}) end)"
    return f"pcall(function() hl.window_rule({{ match = {match}, {effects} }}) end)"


def render_extras(extras: dict) -> list[str]:
    rules = [r for r in extras.get("window_rules", []) if isinstance(r, dict) and problem(r) is None]
    if not rules:
        return []
    return ["", "-- Window rules"] + [rule_call(r) for r in rules]


def describe(rule: dict) -> str:
    """'Floating, 800×600, workspace 3' for the rule's row."""
    parts = []
    if rule.get("float"):
        parts.append(_("floating"))
    if rule.get("center"):
        parts.append(_("centered"))
    if rule.get("size"):
        parts.append("{}×{}".format(*rule["size"]))
    if rule.get("workspace"):
        parts.append(_("workspace {n}").format(n=rule["workspace"]))
    if rule.get("opacity") is not None:
        parts.append(_("opacity {percent}%").format(percent=round(rule["opacity"] * 100)))
    if rule.get("pin"):
        parts.append(_("on every workspace"))
    if rule.get("fullscreen"):
        parts.append(_("fullscreen"))
    if rule.get("maximize"):
        parts.append(_("maximized"))
    if rule.get("idle"):
        parts.append(_("keeps the screen on in fullscreen"))
    text = ", ".join(parts)
    return text[:1].upper() + text[1:]


# ------------------------------------------------------------------ the user's own rules (read only)
@dataclass(frozen=True)
class ConfigRule:
    file: str  # relative to ~/.config/hypr
    text: str  # the call, on one line


def config_rules(config_dir: Path | None = None) -> list[ConfigRule]:
    config_dir = CONFIG_DIR if config_dir is None else config_dir
    found = []
    for path in sorted(config_dir.rglob("*.lua")):
        if path.name == core.HYPR_MANAGED.name:
            continue
        try:
            text = path.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        for name, args in find_calls(text, ("hl.window_rule", "o.window")):
            call = re.sub(r"\s+", " ", f"{name}({', '.join(args)})")
            found.append(ConfigRule(str(path.relative_to(config_dir)), call))
    return found
