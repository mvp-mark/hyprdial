"""What the app runs on (no GTK, testable): Omarchy or plain Hyprland, and whether Hyprland can take its settings.

On Omarchy every page is shown and shortcuts and startup commands are written with Omarchy's Lua helpers
(o.bind, o.launch_on_start); on plain Hyprland the Omarchy-only pages are hidden and Hyprland's own API is used.
HYPRDIAL_PLATFORM=omarchy|hyprland forces one of them (for tests).
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from . import core
from .i18n import _

OMARCHY_PATH = Path(os.environ.get("OMARCHY_PATH", "/usr/share/omarchy"))
HELPERS = OMARCHY_PATH / "default" / "hypr" / "helpers.lua"  # defines o.bind and o.launch_on_start
FORCE_VAR = "HYPRDIAL_PLATFORM"
PLATFORMS = ("omarchy", "hyprland")
MIN_HYPRLAND = (0, 56)
LEGACY_CONF = core.CONF_DIR / "hypr" / "hyprland.conf"

_detected: str | None = None


def detect(env: dict | None = None, helpers: Path = HELPERS) -> str:
    env = os.environ if env is None else env
    forced = env.get(FORCE_VAR, "")
    if forced in PLATFORMS:
        return forced
    return "omarchy" if core.have("omarchy") and helpers.is_file() else "hyprland"


def platform() -> str:
    """The platform, detected once per run."""
    global _detected
    if _detected is None:
        _detected = detect()
    return _detected


def is_omarchy() -> bool:
    return platform() == "omarchy"


def reset() -> None:
    """Detects again on the next call (tests)."""
    global _detected
    _detected = None


def hyprland_version() -> tuple[int, ...] | None:
    """(0, 56, 2) from `hyprctl version -j`, or None when Hyprland isn't answering."""
    try:
        data = json.loads(core.out(["hyprctl", "version", "-j"]))
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    m = re.match(r"v?(\d+)\.(\d+)(?:\.(\d+))?", str(data.get("tag") or data.get("version") or ""))
    return tuple(int(part) for part in m.groups() if part is not None) if m else None


def config_problem(
    version: tuple[int, ...] | None, main: Path = core.HYPR_MAIN, legacy: Path = LEGACY_CONF
) -> str | None:
    """Why Hyprland settings can't be written, or None. Pages that don't write Hyprland's config still work."""
    if version is None:
        return _("Hyprland isn't running, so its settings can't be changed from here.")
    if version[:2] < MIN_HYPRLAND:
        return _("Hyprland {version} is too old; update it to {minimum} or newer to change its settings here.").format(
            version=".".join(map(str, version)), minimum=".".join(map(str, MIN_HYPRLAND))
        )
    if not main.exists() and legacy.exists():
        return _("Your Hyprland configuration is still in hyprland.conf; move it to hyprland.lua to change it here.")
    return None


# ------------------------------------------------------------------ commands that differ per platform
TERMINALS = (("xdg-terminal-exec", []), ("kitty", []), ("foot", []), ("alacritty", ["-e"]), ("xterm", ["-e"]))


def terminal() -> list[str]:
    """The terminal and the flag that makes it run a command (xterm when none is found)."""
    return next(([name, *flag] for name, flag in TERMINALS if core.have(name)), ["xterm", "-e"])


def terminal_command(script: str) -> list[str]:
    """Runs a shell script in a visible terminal that stays open until Enter (for sudo prompts)."""
    if is_omarchy():
        return ["omarchy-launch-floating-terminal-with-presentation", script]
    return [*terminal(), "bash", "-c", f'{script}; echo; read -rp "{_("Press Enter to close")}"']


def tui_command(command: str) -> str:
    """Shell command that opens a terminal app (Omarchy's shortcuts do it with { tui = ... })."""
    return " ".join([*terminal(), command])


def launch(command: str) -> str:
    """How a desktop app is started: through uwsm when the session uses it, as Omarchy does."""
    return f"uwsm-app -- {command}" if core.have("uwsm-app") else command
