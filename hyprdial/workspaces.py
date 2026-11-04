"""Workspace rules (no GTK, testable): which display shows workspaces 1–10, the one each display starts on, and
which ones always exist. Stored in extras["workspaces"] and rendered as hl.workspace_rule calls.

    {"monitor": {"1": "DP-1", ...}, "default": {"DP-1": "1", ...}, "persistent": ["1", "2"]}
"""

from __future__ import annotations

from . import core

NUMBERS = [str(n) for n in range(1, 11)]


def empty() -> dict:
    return {"monitor": {}, "default": {}, "persistent": []}


def normalize(state: dict | None) -> dict:
    """Drops what isn't a workspace 1–10; a display's start workspace is shown on that display."""
    state = state if isinstance(state, dict) else {}
    monitor = {w: m for w, m in (state.get("monitor") or {}).items() if w in NUMBERS and isinstance(m, str) and m}
    default = {m: w for m, w in (state.get("default") or {}).items() if w in NUMBERS and isinstance(m, str) and m}
    for m, w in default.items():
        monitor[w] = m
    persistent = sorted({w for w in state.get("persistent") or [] if w in NUMBERS}, key=int)
    return {"monitor": monitor, "default": default, "persistent": persistent}


def is_empty(state: dict) -> bool:
    s = normalize(state)
    return not (s["monitor"] or s["default"] or s["persistent"])


def render_extras(extras: dict) -> list[str]:
    s = normalize(extras.get("workspaces"))
    starts = {w: m for m, w in s["default"].items()}
    lines = []
    for w in NUMBERS:
        fields = [f"workspace = {core.lua(w)}"]
        if w in s["monitor"]:
            fields.append(f"monitor = {core.lua(s['monitor'][w])}")
        if w in starts:
            fields.append("default = true")
        if w in s["persistent"]:
            fields.append("persistent = true")
        if len(fields) > 1:
            lines.append(f"pcall(function() hl.workspace_rule({{ {', '.join(fields)} }}) end)")
    return ["", "-- Workspaces"] + lines if lines else []
