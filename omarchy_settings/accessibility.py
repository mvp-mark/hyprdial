"""Cursor size (no GTK, testable). Text size lives in displays.py; animations are a Hyprland option.

The size is set three ways: GTK apps read it from gsettings (live), Hyprland's own cursor through
`hyprctl setcursor` (live), and the XCURSOR_SIZE/HYPRCURSOR_SIZE variables in the generated file, so apps started
at the next login get it too.
"""

from __future__ import annotations

from . import core

CURSOR_SIZES = (24, 32, 48, 64)
DEFAULT_CURSOR = 24  # Omarchy's XCURSOR_SIZE
SCHEMA = "org.gnome.desktop.interface"


def gsetting(key: str) -> str:
    return core.out(["gsettings", "get", SCHEMA, key]).strip("'")


def cursor_size() -> int:
    value = gsetting("cursor-size")
    return int(value) if value.isdigit() else DEFAULT_CURSOR


def set_cursor_size(size: int) -> None:
    core.run(["gsettings", "set", SCHEMA, "cursor-size", str(size)])
    core.run(["hyprctl", "setcursor", gsetting("cursor-theme") or "default", str(size)])


def render_extras(extras: dict) -> list[str]:
    size = extras.get("cursor_size")
    if not isinstance(size, int) or size == DEFAULT_CURSOR:
        return []
    return [
        "",
        "-- Cursor size",
        f'pcall(function() hl.env("XCURSOR_SIZE", "{size}") end)',
        f'pcall(function() hl.env("HYPRCURSOR_SIZE", "{size}") end)',
    ]
