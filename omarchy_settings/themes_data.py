"""Temas e wallpapers do Omarchy (sem GTK, testável).

Um tema é uma pasta em $OMARCHY_PATH/themes/<slug>; ~/.config/omarchy/themes/<slug> pode ser um tema
inteiro do usuário ou só sobrepor arquivos do oficial, como o omarchy-theme-set faz. O tema atual fica em
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
    user: bool = False  # existe em ~/.config/omarchy/themes

    @property
    def dark(self) -> bool:
        return self.colors.get("mode", "dark") != "light"

    def swatches(self) -> list[str]:
        return [self.colors[k] for k in SWATCH_KEYS if isinstance(self.colors.get(k), str)]


def display_name(slug: str) -> str:
    """Mesmo formato do omarchy-theme-list: 'catppuccin-latte' -> 'Catppuccin Latte'."""
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
    roots = (user_dir, omarchy_dir)  # o do usuário vem primeiro: sobrepõe o oficial
    slugs: set[str] = set()
    for root in roots:
        if root.is_dir():
            slugs.update(p.name for p in root.iterdir() if p.is_dir() and not p.name.startswith("."))
    themes = []
    for slug in sorted(slugs):
        themes.append(Theme(slug, display_name(slug), _first(slug, "preview.png", roots),
                            read_colors(_first(slug, "colors.toml", roots)), (user_dir / slug).is_dir()))
    return themes


def current_slug(state: Path = STATE) -> str:
    try:
        return (state / "theme.name").read_text().strip()
    except OSError:
        return ""


def wallpapers(state: Path = STATE, user_backgrounds: Path = USER_BACKGROUNDS) -> list[Path]:
    """Wallpapers do tema atual: os do usuário e os do tema, na ordem do omarchy-theme-bg-next."""
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
