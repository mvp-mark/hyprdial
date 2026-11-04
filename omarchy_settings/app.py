"""Main window and entry point."""

from __future__ import annotations

import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, Gtk  # noqa: E402

from . import __version__, host
from .core import HyprStore
from .i18n import _
from .pages.accessibility import AccessibilityPage
from .pages.apps import AppsPage
from .pages.bar import BarPage
from .pages.connectivity import ConnectivityPage
from .pages.dependencies import DependenciesDialog
from .pages.hyprland import AppearancePage, InputPage
from .pages.monitors import MonitorsPage
from .pages.power import PowerPage
from .pages.search import SearchDialog
from .pages.security import SecurityPage
from .pages.shortcuts import ShortcutsPage
from .pages.sound import SoundPage
from .pages.system import SystemPage
from .pages.themes import ThemesPage
from .ui import ThemeAccent, bg, confirm

APP_ID = "org.omarchy.Settings"

# Sidebar sections, in the spirit of Omarchy's menu (Style, Hardware, System). Titles are functions so they are
# translated when the window is built.
SECTIONS = {"style": lambda: _("Style"), "hardware": lambda: _("Hardware"), "system": lambda: _("System")}
PAGES = [
    ("style", "themes", lambda: _("Themes"), "preferences-desktop-theme-symbolic", ThemesPage),
    ("style", "appearance", lambda: _("Appearance"), "preferences-desktop-appearance-symbolic", AppearancePage),
    ("style", "bar", lambda: _("Bar and fonts"), "preferences-desktop-font-symbolic", BarPage),
    ("hardware", "monitors", lambda: _("Displays"), "preferences-desktop-display-symbolic", MonitorsPage),
    ("hardware", "sound", lambda: _("Sound"), "audio-volume-high-symbolic", SoundPage),
    ("hardware", "power", lambda: _("Power"), "system-shutdown-symbolic", PowerPage),
    ("hardware", "input", lambda: _("Input"), "input-keyboard-symbolic", InputPage),
    ("hardware", "connectivity", lambda: _("Connectivity"), "network-wireless-symbolic", ConnectivityPage),
    ("system", "apps", lambda: _("Apps"), "view-app-grid-symbolic", AppsPage),
    ("system", "shortcuts", lambda: _("Shortcuts"), "preferences-desktop-keyboard-shortcuts-symbolic", ShortcutsPage),
    (
        "system",
        "accessibility",
        lambda: _("Accessibility"),
        "preferences-desktop-accessibility-symbolic",
        AccessibilityPage,
    ),
    ("system", "security", lambda: _("Security"), "security-high-symbolic", SecurityPage),
    ("system", "system", lambda: _("System"), "computer-symbolic", SystemPage),
]
OMARCHY_ONLY = {"themes", "bar", "security"}  # hidden on plain Hyprland


def visible_pages() -> list[tuple]:
    return [p for p in PAGES if host.is_omarchy() or p[1] not in OMARCHY_ONLY]


class Window(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application):
        super().__init__(application=app, title=_("Omarchy Settings"), default_width=1000, default_height=720)
        self.store = HyprStore()
        problem = host.config_problem(host.hyprland_version())
        self.store.read_only = problem is not None
        self.accent = ThemeAccent(self.get_display())

        self.stack = Adw.ViewStack(vexpand=True)
        self._add_pages()

        menu = Gio.Menu()
        menu.append(_("Changed settings…"), "win.changed")
        menu.append(_("Dependencies…"), "win.dependencies")
        menu.append(_("Restore app defaults…"), "win.restore-defaults")
        self._add_actions()

        # sidebar: the pages by section, like Omarchy's menu
        sidebar_header = Adw.HeaderBar()
        sidebar_header.pack_start(
            Gtk.Button(
                icon_name="system-search-symbolic", tooltip_text=_("Search settings (Ctrl+F)"), action_name="win.search"
            )
        )
        sidebar_header.pack_end(
            Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu, tooltip_text=_("Main menu"))
        )
        self.sidebar = Gtk.ListBox(css_classes=["navigation-sidebar"])
        self.sidebar.set_header_func(self._section_header)
        self.sidebar.connect("row-activated", lambda _l, row: self.show_page(row.page_name))
        self._fill_sidebar()
        sidebar_view = Adw.ToolbarView(
            content=Gtk.ScrolledWindow(child=self.sidebar, hscrollbar_policy=Gtk.PolicyType.NEVER)
        )
        sidebar_view.add_top_bar(sidebar_header)

        content_view = Adw.ToolbarView(content=self.stack)
        content_view.add_top_bar(Adw.HeaderBar())
        if problem:
            content_view.add_top_bar(Adw.Banner(title=problem, revealed=True, use_markup=False))
        self.content = Adw.NavigationPage(child=content_view, title="")
        self.split = Adw.NavigationSplitView(
            sidebar=Adw.NavigationPage(child=sidebar_view, title=_("Omarchy Settings")),
            content=self.content,
            min_sidebar_width=220,
            sidebar_width_fraction=0.28,
            max_sidebar_width=260,
        )
        # narrow windows show one pane at a time, with a back button
        narrow = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 640sp"))
        narrow.add_setter(self.split, "collapsed", True)
        self.add_breakpoint(narrow)

        self.stack.connect("notify::visible-child-name", lambda *_a: self._sync_sidebar())
        self._sync_sidebar()

        self.toasts = Adw.ToastOverlay()
        self.toasts.set_child(self.split)
        self.set_content(self.toasts)
        self.connect("close-request", self._on_close)

    def _add_pages(self) -> None:
        for _section, name, title, icon, page in visible_pages():
            self.stack.add_titled_with_icon(page(self), name, title(), icon)

    def _fill_sidebar(self) -> None:
        for section, name, title, icon, _page in visible_pages():
            box = Gtk.Box(spacing=12, margin_top=6, margin_bottom=6, margin_start=6, margin_end=6)
            box.append(Gtk.Image(icon_name=icon))
            box.append(Gtk.Label(label=title(), xalign=0, ellipsize=3))  # 3 = Pango.EllipsizeMode.END
            row = Gtk.ListBoxRow(child=box)
            row.page_name, row.section = name, section
            self.sidebar.append(row)

    @staticmethod
    def _section_header(row: Gtk.ListBoxRow, before: Gtk.ListBoxRow | None) -> None:
        if before is not None and before.section == row.section:
            row.set_header(None)
            return
        label = Gtk.Label(label=SECTIONS[row.section](), xalign=0, css_classes=["heading", "dim-label"])
        label.set_margin_start(12)
        label.set_margin_top(6 if before is None else 18)
        label.set_margin_bottom(6)
        row.set_header(label)

    def show_page(self, name: str) -> None:
        self.stack.set_visible_child_name(name)
        self.split.set_show_content(True)

    def _sync_sidebar(self) -> None:
        """Keeps the sidebar selection and the content title on the visible page (search changes it too)."""
        name = self.stack.get_visible_child_name()
        row = self.sidebar.get_first_child()
        while row is not None:
            if getattr(row, "page_name", None) == name:
                self.sidebar.select_row(row)
                break
            row = row.get_next_sibling()
        page = self.stack.get_page(self.stack.get_visible_child()) if self.stack.get_visible_child() else None
        self.content.set_title(page.get_title() if page else "")

    def _add_actions(self) -> None:
        action = Gio.SimpleAction(name="search")
        action.connect("activate", lambda *_args: self.show_search())
        self.add_action(action)
        # bubble phase: the shortcut recorder, which captures keys, gets Ctrl+F first
        keys = Gtk.ShortcutController(propagation_phase=Gtk.PropagationPhase.BUBBLE)
        keys.add_shortcut(
            Gtk.Shortcut(
                trigger=Gtk.ShortcutTrigger.parse_string("<Control>f"), action=Gtk.NamedAction.new("win.search")
            )
        )
        self.add_controller(keys)
        action = Gio.SimpleAction(name="changed")
        action.connect("activate", lambda *_args: SearchDialog(self.stack, changed_only=True).present(self))
        self.add_action(action)
        action = Gio.SimpleAction(name="dependencies")
        action.connect("activate", lambda *_args: self.show_dependencies())
        self.add_action(action)
        action = Gio.SimpleAction(name="restore-defaults")
        action.connect("activate", lambda *_args: self.confirm_restore_defaults())
        self.add_action(action)

    def reload_pages(self) -> None:
        """Builds the pages again so they show the settings as they are now."""
        visible = self.stack.get_visible_child_name()
        for name in [p.get_name() for p in self.stack.get_pages()]:
            self.stack.remove(self.stack.get_child_by_name(name))
        self._add_pages()
        if visible:
            self.stack.set_visible_child_name(visible)

    def confirm_restore_defaults(self) -> None:
        confirm(
            self,
            heading=_("Restore app defaults?"),
            body=_(
                "Removes every Hyprland, display, shortcut, power button and startup command setting made in "
                "this app, returning to the defaults. The bar, theme, network and system settings are not touched. "
                "A backup of the generated file is kept, and you can undo right after."
            ),
            action=_("Restore"),
            on_confirm=lambda: self._restore_defaults(),
        )

    def _restore_defaults(self) -> None:
        def done(result) -> None:
            if isinstance(result, Exception):
                self.toast(_("Could not restore: {error}").format(error=result))
                return
            previous, _backup = result
            self.reload_pages()
            toast = Adw.Toast(title=_("App defaults restored"), button_label=_("Undo"), timeout=10)
            toast.connect(
                "button-clicked",
                lambda _t: bg(
                    lambda: self.store.restore(previous),
                    lambda _r: (self.reload_pages(), self.toast(_("Settings brought back"))),
                ),
            )
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
