"""Página de temas e wallpapers: galeria com prévia, cores e filtro; grade de wallpapers do tema atual."""
from __future__ import annotations

from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Adw, Gdk, GdkPixbuf, GLib, Gtk  # noqa: E402

from .. import core
from .. import themes_data as td
from ..i18n import _
from ..ui import bg, button_row

THEME_THUMB = (240, 135)
WALL_THUMB = (180, 101)

CSS = b"""
.oms-card { padding: 6px; border-radius: 14px; }
.oms-card.current { box-shadow: inset 0 0 0 2px @accent_bg_color; }
.oms-thumb { border-radius: 10px; }
.oms-badge {
  background: @accent_bg_color; color: @accent_fg_color;
  border-radius: 999px; padding: 2px 8px; margin: 6px; font-size: 0.85em; font-weight: 700;
}
"""
_css_installed = False


def install_css() -> None:
    global _css_installed
    if not _css_installed:
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        _css_installed = True


def load_thumbnails(paths: list[Path], size: tuple[int, int]) -> dict[Path, GdkPixbuf.Pixbuf]:
    """Decodifica já no tamanho do cartão (roda fora da thread da interface).

    O tamanho exato importa: o FlowBox distribui os cartões pelo tamanho natural da imagem.
    """
    result = {}
    for path in paths:
        try:
            result[path] = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path), size[0], size[1], True)
        except GLib.Error:
            pass
    return result


def texture(pixbuf: GdkPixbuf.Pixbuf) -> Gdk.Texture:
    fmt = Gdk.MemoryFormat.R8G8B8A8 if pixbuf.get_has_alpha() else Gdk.MemoryFormat.R8G8B8
    return Gdk.MemoryTexture.new(pixbuf.get_width(), pixbuf.get_height(), fmt, pixbuf.read_pixel_bytes(),
                                 pixbuf.get_rowstride())


def swatch_strip(colors: list[str]) -> Gtk.DrawingArea:
    area = Gtk.DrawingArea(content_width=96, content_height=12, valign=Gtk.Align.CENTER)
    rgbas = []
    for c in colors:
        rgba = Gdk.RGBA()
        if rgba.parse(c):
            rgbas.append(rgba)

    def draw(_area, cr, w, h) -> None:
        if not rgbas:
            return
        step = w / len(rgbas)
        for i, rgba in enumerate(rgbas):
            cr.set_source_rgba(rgba.red, rgba.green, rgba.blue, 1)
            cr.rectangle(i * step, 0, step + 0.5, h)
            cr.fill()

    area.set_draw_func(draw)
    return area


def thumb_card(size: tuple[int, int], title: str | None = None, extra: Gtk.Widget | None = None):
    """Cartão com imagem (preenchida depois), selo de 'atual' e legenda opcional."""
    card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, css_classes=["oms-card"])
    overlay = Gtk.Overlay()
    picture = Gtk.Picture(content_fit=Gtk.ContentFit.COVER, css_classes=["oms-thumb", "card"])
    picture.set_size_request(*size)
    overlay.set_child(picture)
    badge = Gtk.Label(label=_("Current"), css_classes=["oms-badge"], halign=Gtk.Align.START,
                      valign=Gtk.Align.START, visible=False)
    overlay.add_overlay(badge)
    card.append(overlay)
    if title is not None:
        caption = Gtk.Box(spacing=8)
        caption.append(Gtk.Label(label=title, xalign=0, hexpand=True, ellipsize=3))
        if extra is not None:
            caption.append(extra)
        card.append(caption)
    return card, picture, badge


class ThemesPage(Adw.PreferencesPage):
    def __init__(self, win):
        super().__init__()
        install_css()
        self.win = win
        self.themes: list[td.Theme] = []
        self.cards: dict[str, tuple[Gtk.Box, Gtk.Picture, Gtk.Label]] = {}
        self.wall_cards: dict[Path, tuple[Gtk.Box, Gtk.Picture, Gtk.Label]] = {}
        self.filter_mode = "all"
        self.applying = False

        self.theme_group = Adw.PreferencesGroup(
            title=_("Theme"), description=_("Changes the colors of the system, terminal, bar and editor at once."))
        tools = Gtk.Box(spacing=8, margin_bottom=8)
        self.search = Gtk.SearchEntry(hexpand=True, placeholder_text=_("Search themes"))
        self.search.connect("search-changed", lambda _e: self.flow.invalidate_filter())
        tools.append(self.search)
        modes = Gtk.Box(css_classes=["linked"])
        first = None
        for mode, label in (("all", _("All")), ("dark", _("Dark")), ("light", _("Light"))):
            btn = Gtk.ToggleButton(label=label, active=mode == "all", group=first)
            first = first or btn
            btn.connect("toggled", lambda b, m=mode: b.get_active() and self._set_mode(m))
            modes.append(btn)
        tools.append(modes)
        self.theme_group.add(tools)

        self.flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True,
                                max_children_per_line=4, min_children_per_line=1, row_spacing=8, column_spacing=8,
                                activate_on_single_click=True)
        self.flow.set_filter_func(self._filter)
        self.flow.connect("child-activated", self._on_theme_activated)
        self.theme_group.add(self.flow)
        self.add(self.theme_group)

        self.wall_group = Adw.PreferencesGroup(title=_("Wallpaper"))
        self.wall_flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True,
                                     max_children_per_line=6, min_children_per_line=2, row_spacing=6,
                                     column_spacing=6, activate_on_single_click=True)
        self.wall_flow.connect("child-activated", self._on_wall_activated)
        self.wall_group.add(self.wall_flow)
        self.add(self.wall_group)
        # grupo à parte: num PreferencesGroup as linhas sempre vêm antes dos outros widgets, e a grade deve vir antes
        wall_actions = Adw.PreferencesGroup()
        wall_actions.add(button_row(_("Next wallpaper"), _("Cycles through the current theme's backgrounds"),
                                    _("Change"), self._next_wallpaper))
        wall_actions.add(button_row(_("Your wallpapers"),
                                    _("Images in this folder appear here for the current theme"),
                                    _("Open folder"), self._open_user_folder))
        self.add(wall_actions)

        bg(td.list_themes, self._populate_themes)
        self._load_wallpapers()

    # ------------------------------------------------------------------ temas
    def _populate_themes(self, themes) -> None:
        if isinstance(themes, Exception) or not themes:
            self.theme_group.add(Adw.ActionRow(title=_("No themes found"),
                                               subtitle=_("Omarchy's theme folder could not be read")))
            return
        self.themes = themes
        for theme in themes:
            card, picture, badge = thumb_card(THEME_THUMB, theme.name, swatch_strip(theme.swatches()))
            card.set_tooltip_text(f"{theme.name} · {_('Dark theme') if theme.dark else _('Light theme')}")
            child = Gtk.FlowBoxChild(child=card)
            child.theme = theme
            self.flow.append(child)
            self.cards[theme.slug] = (card, picture, badge)
        self._mark_current_theme(td.current_slug())
        previews = {t.preview: t.slug for t in themes if t.preview}
        bg(lambda: load_thumbnails(list(previews), THEME_THUMB),
           lambda pix: self._set_textures(pix, {p: self.cards[s][1] for p, s in previews.items()}))

    @staticmethod
    def _set_textures(pixbufs, pictures: dict) -> None:
        if isinstance(pixbufs, Exception):
            return
        for path, pixbuf in pixbufs.items():
            if path in pictures:
                pictures[path].set_paintable(texture(pixbuf))

    def _mark_current_theme(self, slug: str) -> None:
        for s, (card, _picture, badge) in self.cards.items():
            current = s == slug
            badge.set_visible(current)
            if current:
                card.add_css_class("current")
            else:
                card.remove_css_class("current")

    def _set_mode(self, mode: str) -> None:
        self.filter_mode = mode
        self.flow.invalidate_filter()

    def _filter(self, child: Gtk.FlowBoxChild) -> bool:
        theme = child.theme
        if self.filter_mode == "dark" and not theme.dark or self.filter_mode == "light" and theme.dark:
            return False
        q = self.search.get_text().strip().lower()
        return not q or q in theme.name.lower() or q in theme.slug

    def _on_theme_activated(self, _flow, child: Gtk.FlowBoxChild) -> None:
        self._apply_theme(child.theme.slug)

    def _apply_theme(self, slug: str, undoable: bool = True) -> None:
        """Aplica o tema; o toast de sucesso oferece voltar ao anterior (exceto quando já é um desfazer)."""
        previous = td.current_slug()
        if self.applying or slug == previous:
            return
        name = td.display_name(slug)
        self.applying = True
        self.win.toast(_("Applying {name}…").format(name=name))

        def done(res) -> None:
            self.applying = False
            self._mark_current_theme(td.current_slug())
            self._load_wallpapers()
            if isinstance(res, Exception) or res is None or res.returncode != 0:
                self.win.toast(_("Failed to apply {name}").format(name=name))
                return
            toast = Adw.Toast(title=_("Theme {name} applied").format(name=name), timeout=8)
            if undoable and previous:
                toast.set_button_label(_("Undo"))
                toast.connect("button-clicked", lambda _t: self._apply_theme(previous, undoable=False))
            self.win.toasts.add_toast(toast)

        bg(lambda: core.run(["omarchy-theme-set", name], timeout=120), done)

    # ------------------------------------------------------------------ wallpapers
    def _load_wallpapers(self) -> None:
        def work():
            files = td.wallpapers()
            return files, load_thumbnails(files, WALL_THUMB)

        bg(work, self._populate_wallpapers)

    def _populate_wallpapers(self, result) -> None:
        self.wall_flow.remove_all()
        self.wall_cards = {}
        if isinstance(result, Exception):
            return
        files, pixbufs = result
        current = td.current_wallpaper()
        for path in files:
            card, picture, badge = thumb_card(WALL_THUMB)
            card.set_tooltip_text(path.name)
            if path in pixbufs:
                picture.set_paintable(texture(pixbufs[path]))
            child = Gtk.FlowBoxChild(child=card)
            child.path = path
            self.wall_flow.append(child)
            self.wall_cards[path.resolve()] = (card, picture, badge)
        self._mark_current_wallpaper(current)

    def _mark_current_wallpaper(self, current: Path | None) -> None:
        for path, (card, _picture, badge) in self.wall_cards.items():
            is_current = path == current
            badge.set_visible(is_current)
            if is_current:
                card.add_css_class("current")
            else:
                card.remove_css_class("current")

    def _on_wall_activated(self, _flow, child: Gtk.FlowBoxChild) -> None:
        path = child.path
        bg(lambda: core.run(["omarchy-theme-bg-set", str(path)]),
           lambda _r: (self._mark_current_wallpaper(td.current_wallpaper()),
                       self.win.toast(_("Wallpaper: {name}").format(name=path.name))))

    def _next_wallpaper(self) -> None:
        bg(lambda: core.run(["omarchy-theme-bg-next"]),
           lambda _r: (self._mark_current_wallpaper(td.current_wallpaper()), self.win.toast(_("Wallpaper changed"))))

    def _open_user_folder(self) -> None:
        folder = td.USER_BACKGROUNDS / (td.current_slug() or "")
        folder.mkdir(parents=True, exist_ok=True)
        core.spawn(["xdg-open", str(folder)])
