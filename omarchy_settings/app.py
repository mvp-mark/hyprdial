"""Main window and entry point."""
from __future__ import annotations

import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GObject, Gtk  # noqa: E402

from . import __version__
from .core import HyprStore
from .pages.apps import AppsPage
from .i18n import _
from .pages.bar import BarPage
from .pages.connectivity import ConnectivityPage
from .pages.dependencies import DependenciesDialog
from .pages.hyprland import HyprlandPage
from .pages.monitors import MonitorsPage
from .pages.power import PowerPage
from .pages.search import SearchDialog
from .pages.shortcuts import ShortcutsPage
from .pages.sound import SoundPage
from .pages.system import SystemPage
from .pages.themes import ThemesPage
from .ui import bg

APP_ID = "org.omarchy.Settings"


class Window(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application):
        super().__init__(application=app, title=_("Omarchy Settings"), default_width=900, default_height=720)
        self.store = HyprStore()

        self.stack = Adw.ViewStack()
        self._add_pages()

        title = Adw.ViewSwitcherTitle(stack=self.stack, title=_("Omarchy Settings"))
        header = Adw.HeaderBar()
        header.set_title_widget(title)
        menu = Gio.Menu()
        menu.append(_("Dependencies…"), "win.dependencies")
        menu.append(_("Restore app defaults…"), "win.restore-defaults")
        header.pack_end(Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu, tooltip_text=_("Main menu")))
        find = Gtk.Button(icon_name="system-search-symbolic", tooltip_text=_("Search settings (Ctrl+F)"),
                          action_name="win.search")
        header.pack_start(find)
        action = Gio.SimpleAction(name="search")
        action.connect("activate", lambda *_args: self.show_search())
        self.add_action(action)
        # bubble phase: the shortcut recorder, which captures keys, gets Ctrl+F first
        keys = Gtk.ShortcutController(propagation_phase=Gtk.PropagationPhase.BUBBLE)
        keys.add_shortcut(Gtk.Shortcut(trigger=Gtk.ShortcutTrigger.parse_string("<Control>f"),
                                       action=Gtk.NamedAction.new("win.search")))
        self.add_controller(keys)
        action = Gio.SimpleAction(name="dependencies")
        action.connect("activate", lambda *_args: self.show_dependencies())
        self.add_action(action)
        action = Gio.SimpleAction(name="restore-defaults")
        action.connect("activate", lambda *_args: self.confirm_restore_defaults())
        self.add_action(action)
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

    def _add_pages(self) -> None:
        pages = [
            (ThemesPage(self), "themes", _("Themes"), "preferences-desktop-theme-symbolic"),
            (HyprlandPage(self), "hyprland", "Hyprland", "preferences-system-symbolic"),
            (MonitorsPage(self), "monitors", _("Displays"), "preferences-desktop-display-symbolic"),
            (SoundPage(self), "sound", _("Sound"), "audio-volume-high-symbolic"),
            (PowerPage(self), "power", _("Power"), "system-shutdown-symbolic"),
            (ShortcutsPage(self), "shortcuts", _("Shortcuts"), "preferences-desktop-keyboard-shortcuts-symbolic"),
            (AppsPage(self), "apps", _("Apps"), "view-app-grid-symbolic"),
            (BarPage(self), "bar", _("Bar and fonts"), "preferences-desktop-font-symbolic"),
            (ConnectivityPage(self), "connectivity", _("Connectivity"), "network-wireless-symbolic"),
            (SystemPage(self), "system", _("System"), "computer-symbolic"),
        ]
        for page, name, title, icon in pages:
            self.stack.add_titled_with_icon(page, name, title, icon)

    def reload_pages(self) -> None:
        """Builds the pages again so they show the settings as they are now."""
        visible = self.stack.get_visible_child_name()
        for name in [p.get_name() for p in self.stack.get_pages()]:
            self.stack.remove(self.stack.get_child_by_name(name))
        self._add_pages()
        if visible:
            self.stack.set_visible_child_name(visible)

    def confirm_restore_defaults(self) -> None:
        dialog = Adw.AlertDialog(
            heading=_("Restore app defaults?"),
            body=_("Removes every Hyprland, display, shortcut, power button and startup command setting made in "
                   "this app, returning to Omarchy's own. The bar, theme, network and system settings are not touched. A backup of "
                   "the generated file is kept, and you can undo right after."))
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("restore", _("Restore"))
        dialog.set_response_appearance("restore", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_close_response("cancel")
        dialog.connect("response", lambda _d, r: r == "restore" and self._restore_defaults())
        dialog.present(self)

    def _restore_defaults(self) -> None:
        def done(result) -> None:
            if isinstance(result, Exception):
                self.toast(_("Could not restore: {error}").format(error=result))
                return
            previous, _backup = result
            self.reload_pages()
            toast = Adw.Toast(title=_("App defaults restored"), button_label=_("Undo"), timeout=10)
            toast.connect("button-clicked", lambda _t: bg(lambda: self.store.restore(previous), lambda _r: (
                self.reload_pages(), self.toast(_("Settings brought back")))))
            self.toasts.add_toast(toast)

        bg(self.store.reset_all, done)

    def show_search(self) -> None:
        if self.get_visible_dialog() is None:
            SearchDialog(self.stack).present(self)

    def show_dependencies(self) -> None:
        DependenciesDialog().present(self)

    def toast(self, message: str) -> None:
        self.toasts.add_toast(Adw.Toast(title=message, timeout=2))

    def _on_close(self, _win) -> bool:
        self.store.flush()  # make sure pending settings were written
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
