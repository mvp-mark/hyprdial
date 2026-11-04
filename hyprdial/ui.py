"""Widget helpers shared by the pages."""

from __future__ import annotations

import threading
from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

from . import core
from .i18n import _


def bg(fn: Callable, done: Callable | None = None) -> None:
    """Runs fn in a thread and hands the result (or the exception) to done on the UI thread."""

    def work() -> None:
        try:
            result = fn()
        except Exception as exc:  # noqa: BLE001
            result = exc
        if done:

            def cb() -> bool:
                done(result)
                return False

            GLib.idle_add(cb)

    threading.Thread(target=work, daemon=True).start()


def to_float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def to_bool(value, default: bool) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def spin_row(title, subtitle, lo, hi, step, value, on_change, digits=0) -> Adw.SpinRow:
    row = Adw.SpinRow.new_with_range(lo, hi, step)
    row.set_title(title)
    row.set_subtitle(subtitle)
    row.set_digits(digits)
    row.set_value(value)
    row.connect("notify::value", lambda r, _p: on_change(r.get_value() if digits else int(r.get_value())))
    return row


def switch_row(title, subtitle, active, on_change) -> Adw.SwitchRow:
    row = Adw.SwitchRow(title=title, subtitle=subtitle)
    row.set_active(active)
    row.connect("notify::active", lambda r, _p: on_change(r.get_active()))
    return row


def combo_row(title, subtitle, options, selected, on_change) -> Adw.ComboRow:
    row = Adw.ComboRow(title=title, subtitle=subtitle)
    row.set_model(Gtk.StringList.new(options))
    row.set_selected(max(0, min(selected, len(options) - 1)))
    row.connect("notify::selected", lambda r, _p: on_change(r.get_selected()))
    return row


def entry_row(title, text, on_apply) -> Adw.EntryRow:
    row = Adw.EntryRow(title=title)
    row.set_text(text)
    row.set_show_apply_button(True)
    row.connect("apply", lambda r: on_apply(r.get_text().strip()))
    return row


def button_row(title, subtitle, label, on_click, style: str | None = None) -> Adw.ActionRow:
    row = Adw.ActionRow(title=title, subtitle=subtitle)
    btn = Gtk.Button(label=label, valign=Gtk.Align.CENTER)
    if style:
        btn.add_css_class(style)
    btn.connect("clicked", lambda _b: on_click())
    row.add_suffix(btn)
    row.set_activatable_widget(btn)
    return row


def on_ui_thread(fn: Callable, *args) -> None:
    """Runs fn(*args) on the UI thread; for callbacks that come from worker threads."""
    GLib.idle_add(lambda: fn(*args) or False)


# A bar of the accent color on the row's left edge, like KDE's "highlight changed settings"; it takes no space, so
# titles stay aligned.
CHANGED_CSS = "row.changed { box-shadow: inset 3px 0 @accent_bg_color; }"


def set_changed(row: Gtk.Widget, on: bool) -> None:
    """Marks a row whose setting differs from Omarchy's default; "Changed settings" lists the marked rows."""
    if on:
        row.add_css_class("changed")
        row.set_tooltip_text(_("Changed from the default"))
    else:
        row.remove_css_class("changed")
        row.set_tooltip_text(None)


def is_changed(row: Gtk.Widget) -> bool:
    return row.has_css_class("changed")


class Debouncer:
    """Calls fn with the latest arguments once they stop coming for delay_ms (sliders, typing).

    With restart=False it is a throttle instead: the first call schedules fn and later ones within delay_ms are
    folded into it, so a steady stream of calls still runs fn every delay_ms."""

    def __init__(self, delay_ms: int, fn: Callable, restart: bool = True):
        self.delay_ms, self.fn, self.restart = delay_ms, fn, restart
        self._source = 0
        self._args: tuple = ()

    @property
    def pending(self) -> bool:
        return bool(self._source)

    def __call__(self, *args) -> None:
        self._args = args
        if self._source:
            if not self.restart:
                return
            GLib.source_remove(self._source)
        self._source = GLib.timeout_add(self.delay_ms, self._fire)

    def cancel(self) -> None:
        if self._source:
            GLib.source_remove(self._source)
            self._source = 0

    def _fire(self) -> bool:
        self._source = 0
        self.fn(*self._args)
        return False


def refresh_while_mapped(widget: Gtk.Widget, seconds: int, tick: Callable[[], None]) -> None:
    """Calls tick every few seconds, only while the widget is on screen."""
    state = {"source": 0}

    def start(_w) -> None:
        if not state["source"]:
            state["source"] = GLib.timeout_add_seconds(seconds, lambda: tick() or True)

    def stop(_w) -> None:
        if state["source"]:
            GLib.source_remove(state["source"])
            state["source"] = 0

    widget.connect("map", start)
    widget.connect("unmap", stop)


def confirm(
    parent: Gtk.Widget, heading: str, body: str, action: str, on_confirm: Callable[[], None], destructive: bool = True
) -> None:
    """Asks before doing something hard to undo; on_confirm runs only if the user picks the action."""
    dialog = Adw.AlertDialog(heading=heading, body=body)
    dialog.add_response("cancel", _("Cancel"))
    dialog.add_response("confirm", action)
    dialog.set_response_appearance(
        "confirm", Adw.ResponseAppearance.DESTRUCTIVE if destructive else Adw.ResponseAppearance.SUGGESTED
    )
    dialog.set_default_response("cancel")
    dialog.set_close_response("cancel")
    dialog.connect("response", lambda _d, response: response == "confirm" and on_confirm())
    dialog.present(parent)


def missing_row(program: str, hint: str = "") -> Adw.ActionRow:
    """Shown in place of controls whose program isn't installed."""
    return Adw.ActionRow(title=_("{name} is not installed").format(name=program), subtitle=hint, use_markup=False)


def launch_tui(win, cmd: str) -> None:
    """Opens one of Omarchy's terminal apps, or says how to install it."""
    if not core.have(cmd):
        win.toast(_("{cmd} is not installed; install it from ☰ → Dependencies").format(cmd=cmd))
        return
    core.launch_tui(cmd)


class ThemeAccent:
    """Uses the current Omarchy theme's accent color, and follows it when the theme changes."""

    def __init__(self, display):
        from . import themes_data as td  # only the window needs it

        self.td = td
        self.provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(display, self.provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        base = Gtk.CssProvider()
        base.load_from_string(CHANGED_CSS)
        Gtk.StyleContext.add_provider_for_display(display, base, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.apply()
        # omarchy-theme-set swaps ~/.local/state/omarchy/current/theme: watch its parent folder
        self.monitor = Gio.File.new_for_path(str(td.STATE)).monitor_directory(Gio.FileMonitorFlags.NONE, None)
        self.reload = Debouncer(500, self.apply)
        self.monitor.connect("changed", lambda *_a: self.reload())

    def apply(self) -> None:
        colors = self.td.accent()
        self.provider.load_from_string(self.td.accent_css(colors) if colors else "")
