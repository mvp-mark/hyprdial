"""Omarchy shell (Quickshell) configuration and commands (no GTK, testable).

The bar belongs to omarchy-shell. Position, transparency and widgets are changed through the `omarchy-bar` and
`omarchy-plugin-*` commands, which talk to the running shell; only the idle settings are written straight to
~/.config/omarchy/shell.json, the same way Omarchy's commands do it.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from . import core
from .i18n import _

OMARCHY_PATH = os.environ.get("OMARCHY_PATH", "/usr/share/omarchy")
SHELL_CONFIG = core.CONF_DIR / "omarchy" / "shell.json"
SHELL_DEFAULTS = Path(OMARCHY_PATH) / "config" / "omarchy" / "shell.json"
BAR_OFF_FLAG = core.HOME / ".local/state/omarchy/toggles/bar-off"
STAY_AWAKE_FLAG = core.HOME / ".local/state/omarchy/indicators/stay-awake"

SECTIONS = ["left", "center", "right"]
IDLE_TIMES = [60, 120, 150, 300, 600, 900, 1800, 3600, 0]


def read_shell() -> dict:
    """Same rule as omarchy-shell-config: the user's file, or the defaults if it is empty."""
    for path in (SHELL_CONFIG, SHELL_DEFAULTS):
        try:
            if path.stat().st_size:
                data = json.loads(path.read_text())
                if isinstance(data, dict):
                    return data
        except (OSError, ValueError):
            continue
    return {}


def bar_layout(config: dict) -> dict[str, list[dict]]:
    layout = (config.get("bar") or {}).get("layout") or {}
    result = {}
    for section in SECTIONS:
        items = layout.get(section) if isinstance(layout.get(section), list) else []
        result[section] = [i if isinstance(i, dict) else {"id": str(i)} for i in items]
    return result


def write_config(config: dict) -> bool:
    """Writes shell.json atomically and asks the running shell to read it again."""
    config.setdefault("version", 1)
    try:
        SHELL_CONFIG.parent.mkdir(parents=True, exist_ok=True)
        tmp = SHELL_CONFIG.with_suffix(".tmp")
        tmp.write_text(json.dumps(config, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
        os.replace(tmp, SHELL_CONFIG)
    except OSError:
        return False
    core.run(["omarchy-shell", "shell", "reloadConfig"])
    return True


def write_idle(key: str, seconds: int) -> bool:
    config = read_shell()
    idle = config.get("idle") if isinstance(config.get("idle"), dict) else {}
    idle[key] = seconds
    config["idle"] = idle
    return write_config(config)


# ------------------------------------------------------------------ widgets that can repeat
REPEATABLE = {"omarchy.spacer"}  # omarchy-bar keeps one of each widget; spacers make sense several times


def remove_widget_at(section: str, index: int, widget_id: str) -> bool:
    """Removes one widget from the layout, leaving the others with the same id (omarchy-plugin-disable removes them
    all). Checks the id first, so a layout changed meanwhile is never cut in the wrong place."""
    config = read_shell()
    items = (config.get("bar") or {}).get("layout", {}).get(section)
    if not isinstance(items, list) or not 0 <= index < len(items):
        return False
    item = items[index]
    if (item.get("id") if isinstance(item, dict) else str(item)) != widget_id:
        return False
    del items[index]
    return write_config(config)


def add_widget_copy(widget_id: str, section: str) -> bool:
    """Adds another copy of a repeatable widget at the end of a section."""
    config = read_shell()
    layout = config.setdefault("bar", {}).setdefault("layout", {})
    items = layout.get(section) if isinstance(layout.get(section), list) else []
    layout[section] = [*items, {"id": widget_id}]
    return write_config(config)


def widget_catalog() -> dict[str, tuple[str, str]]:
    """id -> (name, description) of every bar widget the shell knows about, as the catalog writes them."""
    try:
        catalog = json.loads(core.out(["omarchy-plugin-catalog"], timeout=15))
    except (ValueError, TypeError):
        catalog = []
    result = {}
    for item in catalog if isinstance(catalog, list) else []:
        if isinstance(item, dict) and item.get("barWidget"):
            result[item["id"]] = (item.get("name") or item["id"], item.get("description") or "")
    return result


def command(args: list[str]) -> tuple[bool, str]:
    r = core.run(args, timeout=20)
    if r is None:
        return False, _("command not found")
    return r.returncode == 0, (r.stderr or r.stdout).strip()


def bar(args: list[str]) -> tuple[bool, str]:
    return command(["omarchy-bar", *args])


def show_bar(on: bool) -> tuple[bool, str]:
    # omarchy-toggle-bar controls the "bar-off" flag: 'off' shows the bar, 'on' hides it
    return command(["omarchy-toggle-bar", "off" if on else "on"])


def restart() -> tuple[bool, str]:
    return command(["omarchy-restart-shell"])


def enable_widget(widget_id: str) -> tuple[bool, str]:
    return command(["omarchy-plugin-enable", widget_id])


def disable_widget(widget_id: str) -> tuple[bool, str]:
    return command(["omarchy-plugin-disable", widget_id])


def stay_awake(on: bool) -> tuple[bool, str]:
    return command(["omarchy-toggle-idle", "stay-awake" if on else "allow-idle"])


# ------------------------------------------------------------------ font
def fonts() -> tuple[list[str], str]:
    """(monospace fonts Omarchy offers, the current one)."""
    available = [f.strip() for f in core.out(["omarchy-font-list"]).splitlines() if f.strip()]
    return available, core.out(["omarchy-font-current"])


def set_font(name: str):
    return core.run(["omarchy-font-set", name], timeout=60)
