"""Display brightness (DDC/CI) and text size through Omarchy's commands (no GTK, testable)."""

from __future__ import annotations

import re

from . import core


def brightness(output: str) -> int | None:
    m = re.fullmatch(r"\s*(\d+)\s*", core.out(["omarchy-brightness-display", "--monitor", output], timeout=8))
    return int(m.group(1)) if m else None


def text_size() -> int | None:
    m = re.search(r"text size:\s*(\d+)", core.out(["omarchy-display-text-size"]))
    return int(m.group(1)) if m else None


def set_brightness(output: str, percent: int) -> None:
    core.run(["omarchy-brightness-display", "--no-osd", "--monitor", output, f"{percent}%"], timeout=15)


def set_text_size(size: int) -> None:
    core.run(["omarchy-display-text-size", str(size)], timeout=30)
