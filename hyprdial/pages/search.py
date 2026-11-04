"""Search dialog (Ctrl+F): finds any setting by name across the pages and jumps to it."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Graphene", "1.0")
from gi.repository import Adw, GLib, Graphene, Gtk  # noqa: E402

from .. import search
from ..i18n import _
from ..ui import is_changed

HIGHLIGHT_CSS = ".search-hit { background-color: alpha(@accent_bg_color, 0.35); }"
_css_loaded = False


def children(widget: Gtk.Widget):
    child = widget.get_first_child()
    while child is not None:
        yield child
        child = child.get_next_sibling()


def ancestor(widget: Gtk.Widget, cls):
    w = widget.get_parent()
    while w is not None and not isinstance(w, cls):
        w = w.get_parent()
    return w


def collect(stack: Adw.ViewStack) -> list[search.Entry]:
    """Every titled row on every page, with its group's title."""
    entries = []
    for page in stack.get_pages():
        name, page_title = page.get_name(), page.get_title()

        def walk(widget: Gtk.Widget, name=name, page_title=page_title) -> None:
            if isinstance(widget, Adw.PreferencesRow) and widget.get_title():
                group = ancestor(widget, Adw.PreferencesGroup)
                subtitle = widget.get_subtitle() if isinstance(widget, (Adw.ActionRow, Adw.ExpanderRow)) else ""
                entries.append(
                    search.Entry(
                        widget.get_title(), subtitle or "", name, page_title, group.get_title() if group else "", widget
                    )
                )
            for child in children(widget):
                walk(child, name, page_title)

        walk(page.get_child())
    return search.unique(entries)


def reveal(stack: Adw.ViewStack, entry: search.Entry) -> None:
    """Shows the entry's page, opens the expanders around it, scrolls to it and highlights it for a moment."""
    global _css_loaded
    if not _css_loaded:
        provider = Gtk.CssProvider()
        provider.load_from_string(HIGHLIGHT_CSS)
        Gtk.StyleContext.add_provider_for_display(
            stack.get_display(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        _css_loaded = True
    row = entry.widget
    root = stack.get_root()
    if hasattr(root, "show_page"):
        root.show_page(entry.page)  # also leaves the sidebar on narrow windows
    else:
        stack.set_visible_child_name(entry.page)
    parent = row.get_parent()
    while parent is not None:
        if isinstance(parent, Adw.ExpanderRow):
            parent.set_expanded(True)
        parent = parent.get_parent()

    def scroll() -> bool:
        scrolled = ancestor(row, Gtk.ScrolledWindow)
        if scrolled is not None:
            ok, point = row.compute_point(scrolled.get_child(), Graphene.Point())
            if ok:
                scrolled.get_vadjustment().set_value(max(0, point.y - 80))
        row.add_css_class("search-hit")
        GLib.timeout_add(1800, lambda: row.remove_css_class("search-hit") or False)
        return False

    GLib.timeout_add(250, scroll)  # after the expanders have opened and the page has a size


class SearchDialog(Adw.Dialog):
    """Search box over every setting; with changed_only, the fixed list of settings that differ from Omarchy's."""

    def __init__(self, stack: Adw.ViewStack, changed_only: bool = False):
        title = _("Changed settings") if changed_only else _("Search settings")
        super().__init__(title=title, content_width=520, content_height=560)
        self.stack = stack
        self.entries = collect(stack)
        self.results: list[search.Entry] = []

        self.entry = Gtk.SearchEntry(placeholder_text=_("Search settings"), hexpand=True)
        self.entry.connect("search-changed", lambda _e: self._update())
        self.entry.connect("activate", lambda _e: self._open(0))
        self.list = Gtk.ListBox(
            css_classes=["boxed-list"],
            selection_mode=Gtk.SelectionMode.NONE,
            margin_start=12,
            margin_end=12,
            margin_top=6,
            margin_bottom=12,
        )
        self.list.connect("row-activated", lambda _l, row: self._open(row.get_index()))
        self.status = Adw.StatusPage(
            icon_name="system-search-symbolic", vexpand=True, title=_("Type the name of a setting")
        )
        scrolled = Gtk.ScrolledWindow(vexpand=True, child=self.list, hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.body = Gtk.Stack()
        self.body.add_named(self.status, "status")
        self.body.add_named(scrolled, "results")

        header = Adw.HeaderBar()
        view = Adw.ToolbarView(content=self.body)
        view.add_top_bar(header)
        self.set_child(view)
        if changed_only:
            self.status.set_icon_name("emblem-ok-symbolic")
            self.status.set_title(_("Nothing changed"))
            self.status.set_description(_("Every setting this app manages is at its default."))
            self._show([e for e in self.entries if is_changed(e.widget)])
            return
        header.set_title_widget(self.entry)
        self.set_focus(self.entry)
        self.entry.set_key_capture_widget(view)

    def _update(self) -> None:
        query = self.entry.get_text()
        self._show(search.search(self.entries, query))
        if not self.results:
            self.status.set_title(_("Nothing found") if query.strip() else _("Type the name of a setting"))

    def _show(self, results: list[search.Entry]) -> None:
        self.list.remove_all()
        self.results = results
        for e in self.results:
            where = " › ".join(p for p in (e.page_title, e.group) if p and p != e.title)
            row = Adw.ActionRow(title=e.title, subtitle=where, activatable=True, use_markup=False)
            row.add_suffix(Gtk.Image(icon_name="go-next-symbolic"))
            self.list.append(row)
        self.body.set_visible_child_name("results" if self.results else "status")

    def _open(self, index: int) -> None:
        if 0 <= index < len(self.results):
            entry = self.results[index]
            self.close()
            reveal(self.stack, entry)
