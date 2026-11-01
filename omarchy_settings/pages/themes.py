"""Página de temas e wallpapers (usa os scripts omarchy-theme-*)."""
from __future__ import annotations

import os
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, Gtk  # noqa: E402

from .. import core
from ..i18n import _
from ..ui import bg, button_row

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}


def _norm(name: str) -> str:
    return name.lower().replace(" ", "").replace("-", "").replace("_", "")


def list_themes() -> list[str]:
    names = [n.strip() for n in core.out(["omarchy-theme-list"]).splitlines() if n.strip()]
    if names:
        return names
    found: set[str] = set()
    for base in (core.CONF_DIR / "omarchy" / "themes", core.HOME / ".local/share/omarchy/themes"):
        if base.is_dir():
            found.update(p.name for p in base.iterdir() if p.is_dir())
    return sorted(found)


def list_wallpapers(limit: int = 12) -> list[Path]:
    roots = [core.CONF_DIR / "omarchy/current/theme/backgrounds"]
    user_root = core.CONF_DIR / "omarchy/backgrounds"
    if user_root.is_dir():
        roots += [p for p in sorted(user_root.iterdir()) if p.is_dir()]
    files: list[Path] = []
    for root in roots:
        if root.is_dir():
            files += [p for p in sorted(root.iterdir()) if p.suffix.lower() in IMAGE_EXT]
    return files[:limit]


def set_wallpaper(path: Path) -> None:
    if core.have("omarchy-theme-bg-set"):
        core.run(["omarchy-theme-bg-set", str(path)])
        return
    link = core.CONF_DIR / "omarchy/current/background"
    link.parent.mkdir(parents=True, exist_ok=True)
    tmp = link.with_name("background.tmp")
    if tmp.is_symlink() or tmp.exists():
        tmp.unlink()
    tmp.symlink_to(path)
    os.replace(tmp, link)
    core.run(["pkill", "-x", "swaybg"])
    prefix = ["uwsm-app", "--"] if core.have("uwsm-app") else []
    core.spawn(prefix + ["swaybg", "-i", str(link), "-m", "fill"])


class ThemesPage(Adw.PreferencesPage):
    def __init__(self, win):
        super().__init__()
        self.win = win

        self.theme_group = Adw.PreferencesGroup(
            title=_("Theme"), description=_("Changes the colors of the system, terminal, bar and editor at once.")
        )
        self.add(self.theme_group)
        bg(lambda: (list_themes(), core.out(["omarchy-theme-current"])), self._populate_themes)

        self.wall_group = Adw.PreferencesGroup(title=_("Wallpaper"))
        self.add(self.wall_group)
        self.wall_group.add(
            button_row(
                _("Next wallpaper"),
                _("Cycles through the current theme's backgrounds"),
                _("Change"),
                lambda: bg(
                    lambda: core.run(["omarchy-theme-bg-next"]),
                    lambda _r: win.toast(_("Wallpaper changed")),
                ),
            )
        )
        bg(list_wallpapers, self._populate_wallpapers)

    # -- temas
    def _populate_themes(self, result) -> None:
        if isinstance(result, Exception) or not result[0]:
            self.theme_group.add(
                Adw.ActionRow(title=_("No themes found"), subtitle=_("omarchy-theme-list is not available"))
            )
            return
        themes, current = result
        first: Gtk.CheckButton | None = None
        for name in themes:
            row = Adw.ActionRow(title=name)
            check = Gtk.CheckButton()
            if first is None:
                first = check
            else:
                check.set_group(first)
            check.set_active(_norm(name) == _norm(current))
            check.connect("toggled", self._on_theme_toggled, name)
            row.add_prefix(check)
            row.set_activatable_widget(check)
            self.theme_group.add(row)

    def _on_theme_toggled(self, button: Gtk.CheckButton, name: str) -> None:
        if not button.get_active():
            return
        self.win.toast(_("Applying {name}…").format(name=name))

        def done(res) -> None:
            ok = not isinstance(res, Exception) and res is not None and res.returncode == 0
            self.win.toast((_("Theme {name} applied") if ok else _("Failed to apply {name}")).format(name=name))

        bg(lambda: core.run(["omarchy-theme-set", name], timeout=120), done)

    # -- wallpapers
    def _populate_wallpapers(self, result) -> None:
        if isinstance(result, Exception) or not result:
            return
        flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.SINGLE, max_children_per_line=4, homogeneous=True)
        flow.set_row_spacing(8)
        flow.set_column_spacing(8)
        for path in result:
            pic = Gtk.Picture.new_for_file(Gio.File.new_for_path(str(path)))
            pic.set_content_fit(Gtk.ContentFit.COVER)
            pic.set_size_request(160, 90)
            pic.add_css_class("card")
            pic.set_tooltip_text(path.name)
            flow.append(pic)
        flow.connect("child-activated", self._on_wall_activated, result)
        flow.set_activate_on_single_click(True)
        self.wall_group.add(flow)

    def _on_wall_activated(self, _flow, child, paths: list[Path]) -> None:
        path = paths[child.get_index()]
        bg(lambda: set_wallpaper(path), lambda _r: self.win.toast(_("Wallpaper: {name}").format(name=path.name)))
