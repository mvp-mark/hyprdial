"""Janela principal e ponto de entrada."""
from __future__ import annotations

import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GObject  # noqa: E402

from . import __version__
from .core import HyprStore
from .pages.bar import BarPage
from .pages.connectivity import ConnectivityPage
from .pages.hyprland import HyprlandPage
from .pages.monitors import MonitorsPage
from .pages.shortcuts import ShortcutsPage
from .pages.themes import ThemesPage

APP_ID = "org.omarchy.Settings"


class Window(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application):
        super().__init__(application=app, title="Omarchy Settings", default_width=900, default_height=720)
        self.store = HyprStore()

        self.stack = Adw.ViewStack()
        pages = [
            (ThemesPage(self), "themes", "Temas", "preferences-desktop-theme-symbolic"),
            (HyprlandPage(self), "hyprland", "Hyprland", "preferences-system-symbolic"),
            (MonitorsPage(self), "monitors", "Monitores", "preferences-desktop-display-symbolic"),
            (ShortcutsPage(self), "shortcuts", "Atalhos", "preferences-desktop-keyboard-shortcuts-symbolic"),
            (BarPage(self), "bar", "Barra e fontes", "preferences-desktop-font-symbolic"),
            (ConnectivityPage(self), "connectivity", "Conectividade", "network-wireless-symbolic"),
        ]
        for page, name, title, icon in pages:
            self.stack.add_titled_with_icon(page, name, title, icon)

        title = Adw.ViewSwitcherTitle(stack=self.stack, title="Omarchy Settings")
        header = Adw.HeaderBar()
        header.set_title_widget(title)
        bottom = Adw.ViewSwitcherBar(stack=self.stack)
        title.bind_property("title-visible", bottom, "reveal", GObject.BindingFlags.SYNC_CREATE)

        view = Adw.ToolbarView()
        view.add_top_bar(header)
        view.set_content(self.stack)
        view.add_bottom_bar(bottom)

        self.toasts = Adw.ToastOverlay()
        self.toasts.set_child(view)
        self.set_content(self.toasts)
        self.connect("close-request", self._on_close)

    def toast(self, message: str) -> None:
        self.toasts.add_toast(Adw.Toast(title=message, timeout=2))

    def _on_close(self, _win) -> bool:
        self.store.flush()  # garante que ajustes pendentes foram gravados
        return False


class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)

    def do_activate(self) -> None:
        win = self.props.active_window or Window(self)
        win.present()


def main() -> int:
    if "--version" in sys.argv:
        print(f"omarchy-settings {__version__}")
        return 0
    return App().run(sys.argv)
