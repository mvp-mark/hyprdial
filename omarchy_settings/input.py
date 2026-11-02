"""Touchpad and touchscreen on/off through Omarchy's toggles (no GTK, testable).

omarchy-hw-<kind> prints the device name (nothing when there is none); omarchy-toggle-input-device turns it on or
off and remembers a disabled device in ~/.local/state/omarchy/toggles/hypr/<kind>-disabled-name.
"""

from __future__ import annotations

from pathlib import Path

from . import core

KINDS = ("touchpad", "touchscreen")
TOGGLES = core.HOME / ".local/state/omarchy/toggles/hypr"


def device(kind: str) -> str:
    return core.out([f"omarchy-hw-{kind}"]) if core.have(f"omarchy-hw-{kind}") else ""


def enabled(kind: str, toggles: Path = TOGGLES) -> bool:
    return not (toggles / f"{kind}-disabled-name").exists()


def devices(toggles: Path = TOGGLES) -> dict[str, bool]:
    """kind -> enabled, for the kinds this computer has."""
    return {kind: enabled(kind, toggles) for kind in KINDS if device(kind)}


def set_enabled(kind: str, on: bool) -> bool:
    r = core.run(["omarchy-toggle-input-device", kind, "on" if on else "off"])
    return bool(r and r.returncode == 0)
