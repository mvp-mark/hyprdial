"""Bluetooth group: adapter on/off, paired devices (connect, disconnect, forget, battery), search and pairing."""
from __future__ import annotations

import os
import subprocess
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

from .. import bluetooth as bt
from .. import core
from ..i18n import _, ngettext
from ..ui import bg, button_row

REFRESH_SECONDS = 10
PAIR_TIMEOUT = 60


def battery_icon(level: int) -> str:
    return f"battery-level-{min(100, round(level / 10) * 10)}-symbolic"


class PairSession:
    """One interactive bluetoothctl that pairs, trusts and connects a device.

    on_event(event) is called on the UI thread with PairParser's events, plus ("ended",) when the process exits.
    """

    def __init__(self, mac: str, on_event):
        self.mac, self.on_event = mac, on_event
        self.parser = bt.PairParser()
        self.proc: subprocess.Popen | None = None
        self.finished = False

    def start(self) -> bool:
        try:
            self.proc = subprocess.Popen(["bluetoothctl"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                         stderr=subprocess.STDOUT, start_new_session=True)
        except OSError:
            return False
        threading.Thread(target=self._read, daemon=True).start()
        self.send(bt.PAIR_START.format(mac=self.mac))
        GLib.timeout_add_seconds(PAIR_TIMEOUT, self._timeout)
        return True

    def send(self, text: str) -> None:
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.stdin.write(text.encode())
                self.proc.stdin.flush()
            except OSError:
                pass

    def stop(self) -> None:
        self.finished = True
        self.send("quit\n")
        if self.proc:
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    def _read(self) -> None:
        fd = self.proc.stdout.fileno()
        while True:
            try:
                chunk = os.read(fd, 4096)
            except OSError:
                break
            if not chunk:
                break
            for event in self.parser.feed(chunk.decode(errors="replace")):
                GLib.idle_add(self._emit, event)
        GLib.idle_add(self._emit, ("ended",))

    def _emit(self, event) -> bool:
        self.on_event(event)
        return False

    def _timeout(self) -> bool:
        if not self.finished:
            self.on_event(("failed", "timeout"))
        return False


class CodeDialog(Adw.AlertDialog):
    """Shows a pairing code: to type on the device, or to compare and confirm."""

    def __init__(self, name: str, code: str, confirm: bool, on_answer):
        if confirm:
            body = _("Check that “{name}” shows the same code, then confirm.").format(name=name)
        else:
            body = _("Type this code on “{name}” and press Enter.").format(name=name)
        super().__init__(heading=_("Pairing code"), body=body)
        self.set_extra_child(Gtk.Label(label=code, css_classes=["title-1"], margin_top=6))
        self.add_response("cancel", _("Cancel"))
        if confirm:
            self.add_response("confirm", _("Confirm"))
            self.set_response_appearance("confirm", Adw.ResponseAppearance.SUGGESTED)
            self.set_default_response("confirm")
        self.set_close_response("cancel")
        self.connect("response", lambda _d, r: on_answer(r))


class BluetoothGroup(Adw.PreferencesGroup):
    def __init__(self, win, open_tui):
        super().__init__(title=_("Bluetooth"))
        self.win, self.open_tui = win, open_tui
        self.rows: list[Gtk.Widget] = []
        self.snapshot = None
        self.busy = False
        self.scanning = False
        self.nearby: list[bt.Device] | None = None  # None until a search ran
        self.expanded = {"paired": True, "nearby": True}
        self.session: PairSession | None = None
        self.code_dialog: CodeDialog | None = None
        self._timer = 0
        self.connect("map", lambda _w: self._start_timer())
        self.connect("unmap", lambda _w: self._stop_timer())
        self.refresh()

    # -- refreshing
    def _start_timer(self) -> None:
        if not self._timer:
            self._timer = GLib.timeout_add_seconds(REFRESH_SECONDS, self._tick)

    def _stop_timer(self) -> None:
        if self._timer:
            GLib.source_remove(self._timer)
            self._timer = 0

    def _tick(self) -> bool:
        if not self.busy and not self.scanning and self.session is None:
            self.refresh()
        return True

    def refresh(self) -> None:
        def load() -> dict:
            on = bt.powered()
            if on is None:
                return {"error": _("No Bluetooth adapter found") if core.have("bluetoothctl")
                        else _("bluetoothctl is not installed")}
            return {"on": on, "devices": [d for d in bt.devices() if d.paired] if on else []}

        bg(load, self._rebuild)

    # -- building
    def _clear(self) -> None:
        for row in self.rows:
            self.remove(row)
        self.rows = []

    def _add(self, row: Gtk.Widget) -> None:
        self.rows.append(row)
        self.add(row)

    def _rebuild(self, data, force: bool = False) -> None:
        if isinstance(data, Exception):
            return
        if data == self.snapshot and not force:
            return  # nothing changed: keep the rows (and whatever is expanded) as they are
        self.snapshot = data
        self._clear()
        if "error" in data:
            self._add(Adw.ActionRow(title=data["error"]))
            self._add_advanced()
            return

        connected = [d for d in data["devices"] if d.connected]
        status = _("Off") if not data["on"] else (
            ngettext("{n} device connected", "{n} devices connected", len(connected)).format(n=len(connected))
            if connected else _("On, nothing connected"))
        power = Adw.SwitchRow(title="Bluetooth", subtitle=status, active=data["on"])
        power.connect("notify::active", lambda r, _p: self._set_power(r.get_active()))
        self._add(power)

        if data["on"]:
            paired = Adw.ExpanderRow(title=_("Paired devices"), expanded=self.expanded["paired"],
                                     subtitle=ngettext("{n} paired", "{n} paired", len(data["devices"])).format(
                                         n=len(data["devices"])))
            paired.connect("notify::expanded", lambda e, _p: self.expanded.update(paired=e.get_expanded()))
            if not data["devices"]:
                paired.add_row(Adw.ActionRow(title=_("No paired devices"),
                                             subtitle=_("Put the device in pairing mode and search below")))
            for d in data["devices"]:
                paired.add_row(self._paired_row(d))
            self._add(paired)
            self._add_nearby()
        self._add_advanced()

    def _add_nearby(self) -> None:
        if self.scanning:
            row = Adw.ActionRow(title=_("Searching for devices…"),
                                subtitle=_("Put the device in pairing mode now"))
            row.add_suffix(Gtk.Spinner(spinning=True, valign=Gtk.Align.CENTER))
            self._add(row)
            return
        if self.nearby is None:
            self._add(button_row(_("Pair a new device"), _("Searches for {n} seconds").format(n=bt.SCAN_SECONDS),
                                 _("Search"), self._scan))
            return
        nearby = Adw.ExpanderRow(title=_("Nearby devices"), expanded=self.expanded["nearby"],
                                 subtitle=ngettext("{n} found", "{n} found", len(self.nearby)).format(
                                     n=len(self.nearby)))
        nearby.connect("notify::expanded", lambda e, _p: self.expanded.update(nearby=e.get_expanded()))
        if not self.nearby:
            nearby.add_row(Adw.ActionRow(title=_("No devices found"),
                                         subtitle=_("Check that the device is in pairing mode and search again")))
        for d in self.nearby:
            row = Adw.ActionRow(title=d.name, subtitle=d.mac, use_markup=False)
            row.add_prefix(Gtk.Image(icon_name=bt.KIND_ICONS[d.kind]))
            btn = Gtk.Button(label=_("Pair"), valign=Gtk.Align.CENTER, css_classes=["suggested-action"])
            btn.connect("clicked", lambda _b, d=d: self._pair(d))
            row.add_suffix(btn)
            nearby.add_row(row)
        again = Adw.ActionRow(title=_("Search again"))
        btn = Gtk.Button(icon_name="view-refresh-symbolic", valign=Gtk.Align.CENTER, css_classes=["flat"])
        btn.connect("clicked", lambda _b: self._scan())
        again.add_suffix(btn)
        again.set_activatable_widget(btn)
        nearby.add_row(again)
        self._add(nearby)

    def _add_advanced(self) -> None:
        self._add(button_row(_("Advanced"), _("Full Bluetooth manager (bluetui)"), _("Open"),
                             lambda: self.open_tui("bluetui")))

    def _paired_row(self, d: bt.Device) -> Adw.ActionRow:
        subtitle = _("Connected") if d.connected else _("Not connected")
        row = Adw.ActionRow(title=d.name, subtitle=subtitle, use_markup=False)
        row.add_prefix(Gtk.Image(icon_name=bt.KIND_ICONS[d.kind]))
        if d.battery is not None:
            box = Gtk.Box(spacing=4, valign=Gtk.Align.CENTER, css_classes=["dim-label"])
            box.append(Gtk.Image(icon_name=battery_icon(d.battery)))
            box.append(Gtk.Label(label=f"{d.battery}%"))
            row.add_suffix(box)
        btn = Gtk.Button(label=_("Disconnect") if d.connected else _("Connect"), valign=Gtk.Align.CENTER)
        btn.connect("clicked", lambda _b: self._toggle(d))
        row.add_suffix(btn)
        forget = Gtk.Button(icon_name="user-trash-symbolic", valign=Gtk.Align.CENTER, css_classes=["flat"],
                            tooltip_text=_("Forget"))
        forget.connect("clicked", lambda _b: self._confirm_forget(d))
        row.add_suffix(forget)
        return row

    # -- actions
    def _run(self, args: list[str], ok_message: str) -> None:
        self.busy = True

        def done(result) -> None:
            self.busy = False
            ok, error = (False, str(result)) if isinstance(result, Exception) else result
            self.win.toast(ok_message if ok else _("Failed: {error}").format(error=error))
            self.snapshot = None
            self.refresh()

        bg(lambda: bt.run(args), done)

    def _set_power(self, on: bool) -> None:
        def done(ok) -> None:
            if ok is not True:
                self.win.toast(_("Could not change Bluetooth"))
            self.snapshot = None
            if not on:
                self.nearby = None
            self.refresh()

        bg(lambda: bt.set_power(on), done)

    def _toggle(self, d: bt.Device) -> None:
        if d.connected:
            self._run(bt.disconnect(d.mac), _("{name} disconnected").format(name=d.name))
        else:
            self.win.toast(_("Connecting to {name}…").format(name=d.name))
            self._run(bt.connect(d.mac), _("{name} connected").format(name=d.name))

    def _confirm_forget(self, d: bt.Device) -> None:
        dialog = Adw.AlertDialog(heading=_("Forget “{name}”?").format(name=d.name),
                                 body=_("To use it again, you'll have to pair it again."))
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("forget", _("Forget"))
        dialog.set_response_appearance("forget", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_close_response("cancel")
        dialog.connect("response", lambda _d, r: r == "forget" and self._run(
            bt.forget(d.mac), _("{name} forgotten").format(name=d.name)))
        dialog.present(self.win)

    def _scan(self) -> None:
        self.scanning = True
        self._rebuild(self.snapshot, force=True)

        def done(found) -> None:
            self.scanning = False
            self.nearby = [] if isinstance(found, Exception) else found
            self._rebuild(self.snapshot, force=True)

        bg(bt.scan, done)

    # -- pairing
    def _pair(self, d: bt.Device) -> None:
        if self.session is not None:
            return
        self.session = PairSession(d.mac, lambda event: self._on_pair_event(d, event))
        if not self.session.start():
            self.session = None
            self.win.toast(_("Could not start bluetoothctl"))
            return
        self.win.toast(_("Pairing with {name}…").format(name=d.name))

    def _close_code(self) -> None:
        if self.code_dialog is not None:
            self.code_dialog.force_close()
            self.code_dialog = None

    def _finish(self, message: str | None) -> None:
        self._close_code()
        if self.session is not None:
            session, self.session = self.session, None
            threading.Thread(target=session.stop, daemon=True).start()
        if message:
            self.win.toast(message)
        self.nearby = None
        self.snapshot = None
        self.refresh()

    def _on_pair_event(self, d: bt.Device, event: tuple) -> None:
        session = self.session
        if session is None:
            return
        kind = event[0]
        if kind in ("show", "confirm"):
            self._close_code()

            def answer(response: str) -> None:
                self.code_dialog = None
                if self.session is not session:
                    return
                if kind == "confirm" and response == "confirm":
                    session.send("yes\n")
                elif response == "cancel":
                    session.send("no\n")
                    self._finish(_("Pairing canceled"))

            self.code_dialog = CodeDialog(d.name, event[1], kind == "confirm", answer)
            self.code_dialog.present(self.win)
        elif kind == "input":
            self._finish(_("{name} asks for a PIN typed here; pair it with Advanced (bluetui)").format(name=d.name))
        elif kind == "paired":
            self._close_code()
            session.send(bt.AFTER_PAIR.format(mac=d.mac))
        elif kind == "connected":
            self._finish(_("{name} paired and connected").format(name=d.name))
        elif kind == "connect-failed":
            self._finish(_("{name} paired, but it didn't connect; try Connect").format(name=d.name))
        elif kind == "failed":
            messages = {"not-found": _("{name} is no longer in range; search again"),
                        "rejected": _("{name} rejected the pairing"),
                        "timeout": _("Pairing with {name} took too long"),
                        "already": _("{name} is already paired")}
            reason = event[1]
            self._finish(messages[reason].format(name=d.name) if reason in messages
                         else _("Could not pair with {name}").format(name=d.name))
        elif kind == "ended":
            self._finish(_("Could not pair with {name}").format(name=d.name))
