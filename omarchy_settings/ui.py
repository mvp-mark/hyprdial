"""Helpers de interface compartilhados pelas páginas."""
from __future__ import annotations

import threading
from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402


def bg(fn: Callable, done: Callable | None = None) -> None:
    """Executa fn em thread e entrega o resultado (ou a exceção) a done na thread da UI."""

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
