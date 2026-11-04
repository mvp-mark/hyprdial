"""Omarchy themes and wallpapers (no GTK, testable).

A theme is a folder in $OMARCHY_PATH/themes/<slug>; ~/.config/omarchy/themes/<slug> can be a whole user theme
or just overlay files of the official one, as omarchy-theme-set does. The current theme lives in
~/.local/state/omarchy/current.
"""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from . import core

OMARCHY_THEMES = Path(os.environ.get("OMARCHY_PATH", "/usr/share/omarchy")) / "themes"
USER_THEMES = core.CONF_DIR / "omarchy" / "themes"
STATE = core.HOME / ".local/state/omarchy/current"
USER_BACKGROUNDS = core.CONF_DIR / "omarchy" / "backgrounds"
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
SWATCH_KEYS = ("background", "foreground", "accent", "red", "yellow", "green", "blue", "magenta")


@dataclass
class Theme:
    slug: str
    name: str
    preview: Path | None
    colors: dict = field(default_factory=dict)
    user: bool = False  # exists in ~/.config/omarchy/themes

    @property
    def dark(self) -> bool:
        return self.colors.get("mode", "dark") != "light"

    def swatches(self) -> list[str]:
        return [self.colors[k] for k in SWATCH_KEYS if isinstance(self.colors.get(k), str)]


def display_name(slug: str) -> str:
    """Same format as omarchy-theme-list: 'catppuccin-latte' -> 'Catppuccin Latte'."""
    return re.sub(r"(^|-)([a-z])", lambda m: m.group(1) + m.group(2).upper(), slug).replace("-", " ")


def _first(slug: str, filename: str, roots: tuple[Path, ...]) -> Path | None:
    for root in roots:
        path = root / slug / filename
        if path.is_file():
            return path
    return None


def read_colors(path: Path | None) -> dict:
    try:
        return tomllib.loads(path.read_text()) if path else {}
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def list_themes(user_dir: Path = USER_THEMES, omarchy_dir: Path = OMARCHY_THEMES) -> list[Theme]:
    roots = (user_dir, omarchy_dir)  # the user's comes first: it overlays the official one
    slugs: set[str] = set()
    for root in roots:
        if root.is_dir():
            slugs.update(p.name for p in root.iterdir() if p.is_dir() and not p.name.startswith("."))
    themes = []
    for slug in sorted(slugs):
        themes.append(
            Theme(
                slug,
                display_name(slug),
                _first(slug, "preview.png", roots),
                read_colors(_first(slug, "colors.toml", roots)),
                (user_dir / slug).is_dir(),
            )
        )
    return themes


def current_slug(state: Path = STATE) -> str:
    try:
        return (state / "theme.name").read_text().strip()
    except OSError:
        return ""


def wallpapers(state: Path = STATE, user_backgrounds: Path = USER_BACKGROUNDS) -> list[Path]:
    """Wallpapers of the current theme: the user's and the theme's, in omarchy-theme-bg-next order."""
    slug = current_slug(state)
    files: list[Path] = []
    for root in (user_backgrounds / slug, state / "theme" / "backgrounds"):
        if slug and root.is_dir():
            files += sorted(p for p in root.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXT)
    return files


def current_wallpaper(state: Path = STATE) -> Path | None:
    link = state / "background"
    try:
        return link.resolve(strict=True)
    except (OSError, RuntimeError):
        return None


def set_theme(name: str):
    return core.run(["omarchy-theme-set", name], timeout=120)


def set_wallpaper(path: Path):
    return core.run(["omarchy-theme-bg-set", str(path)])


def next_wallpaper():
    return core.run(["omarchy-theme-bg-next"])


# ------------------------------------------------------------------ accent color
HEX = re.compile(r"#[0-9a-fA-F]{6}")


def readable_on(color: str) -> str:
    """Black or white, whichever reads better on the color (WCAG relative luminance)."""

    def channel(c: str) -> float:
        v = int(c, 16) / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(color[i : i + 2]) for i in (1, 3, 5))
    luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return "#000000" if luminance > 0.179 else "#ffffff"


def accent(state: Path = STATE) -> tuple[str, str] | None:
    """(accent color, text color on it) of the current theme, or None when it has none."""
    color = read_colors(state / "theme" / "colors.toml").get("accent")
    if not isinstance(color, str) or not HEX.fullmatch(color.strip()):
        return None
    color = color.strip().lower()
    return color, readable_on(color)


def accent_css(colors: tuple[str, str]) -> str:
    """libadwaita's accent colors, both as CSS variables (1.6+) and as named colors (older)."""
    bg, fg = colors
    return (
        f":root {{ --accent-bg-color: {bg}; --accent-color: {bg}; --accent-fg-color: {fg}; }}\n"
        f"@define-color accent_bg_color {bg};\n@define-color accent_color {bg};\n@define-color accent_fg_color {fg};\n"
    )
