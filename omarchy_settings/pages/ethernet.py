"""Wired (Ethernet) group: status, diagnosis, reconnect, and IPv4 settings (DHCP or manual, DNS)."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from .. import core
from .. import network as net
from ..i18n import _
from ..ui import bg, refresh_while_mapped
from .ipv4 import Ipv4Fields, invalid_message

REFRESH_SECONDS = 5


def status_text(w: net.Wired) -> str:
    if not w.carrier:
        return _("No cable connected")
    if w.connected:
        parts = [_("Connected")]
        if w.speed:
            parts.append(_("{speed} Mb/s").format(speed=w.speed))
        if w.addresses:
            parts.append(w.addresses[0].split("/")[0])
        return " · ".join(parts)
    if w.connecting:
        return _("Cable connected, getting an address…")
    return _("Cable connected, not connected to the network")


def diagnosis_text(code: str) -> tuple[str, str]:
    return {
        "no-cable": (_("No cable detected"), _("Check that the cable is firmly plugged in at both ends.")),
        "slow-link": (
            _("The link is running at 10 Mb/s"),
            _(
                "A gigabit port stuck at 10 Mb/s usually means a damaged cable or a bad port. "
                "Try another cable or another port on the router."
            ),
        ),
        "no-address": (
            _("No address from the network"),
            _(
                "Nothing on the cable answered the request for an address (DHCP). Check that the other "
                "end is a router, or set a manual address below."
            ),
        ),
    }.get(code, ("", ""))


class DeviceRows:
    """Rows for one Ethernet port: built once; refresh() only updates their text."""

    def __init__(self, group: EthernetGroup, w: net.Wired, profile: net.Profile | None, title: str):
        self.group, self.device, self.profile = group, w.device, profile
        self.rows: list[Gtk.Widget] = []

        self.status = Adw.ActionRow(title=title)
        self.icon = Gtk.Image(icon_name="network-wired-symbolic")
        self.status.add_prefix(self.icon)
        self.action_btn = Gtk.Button(valign=Gtk.Align.CENTER)
        self.action_btn.connect("clicked", lambda _b: self.group.toggle_connection(self))
        self.status.add_suffix(self.action_btn)
        self.rows.append(self.status)

        self.warning = Adw.ActionRow(title_lines=2, subtitle_lines=4)
        self.warning.add_prefix(Gtk.Image(icon_name="dialog-warning-symbolic", css_classes=["warning"]))
        self.rows.append(self.warning)

        self.details = Adw.ExpanderRow(title=_("Details"))
        self.detail_labels: dict[str, Gtk.Label] = {}
        for key, label in (
            ("mac", _("Hardware address")),
            ("ip", _("IPv4 address")),
            ("gateway", _("Gateway")),
            ("dns", _("DNS servers")),
            ("speed", _("Link speed")),
        ):
            row = Adw.ActionRow(title=label)
            value = Gtk.Label(selectable=True, css_classes=["dim-label"], xalign=1)
            row.add_suffix(value)
            self.details.add_row(row)
            self.detail_labels[key] = value
        self.rows.append(self.details)

        self.rows.append(self._settings_form(profile))
        self.refresh(w)

    # -- status
    def refresh(self, w: net.Wired) -> None:
        self.wired = w
        self.status.set_subtitle(status_text(w))
        self.icon.set_from_icon_name("network-wired-symbolic" if w.connected else "network-wired-disconnected-symbolic")
        self.action_btn.set_label(_("Disconnect") if w.connected or w.connecting else _("Connect"))
        self.action_btn.set_sensitive(w.carrier or w.connected)
        title, help_text = diagnosis_text(net.diagnosis(w))
        self.warning.set_visible(bool(title))
        self.warning.set_title(title)
        self.warning.set_subtitle(help_text)
        none = "—"
        self.detail_labels["mac"].set_label(w.mac or none)
        self.detail_labels["ip"].set_label(", ".join(w.addresses) or none)
        self.detail_labels["gateway"].set_label(w.gateway or none)
        self.detail_labels["dns"].set_label(", ".join(w.dns) or none)
        self.detail_labels["speed"].set_label(_("{speed} Mb/s").format(speed=w.speed) if w.speed else none)

    # -- settings
    def _settings_form(self, profile: net.Profile | None) -> Adw.ExpanderRow:
        self.form = Adw.ExpanderRow(title=_("IPv4 settings"))
        self.fields = Ipv4Fields(profile, _("When the cable is plugged in"), self.form.set_subtitle)
        self.form.set_subtitle(self.fields.summary())
        apply = Adw.ActionRow(title=_("Save and reconnect"))
        self.apply_btn = Gtk.Button(label=_("Apply"), valign=Gtk.Align.CENTER, css_classes=["suggested-action"])
        self.apply_btn.connect("clicked", lambda _b: self.group.save(self))
        apply.add_suffix(self.apply_btn)
        for row in [*self.fields.rows, apply]:
            self.form.add_row(row)
        return self.form


class EthernetGroup(Adw.PreferencesGroup):
    def __init__(self, win):
        super().__init__(title=_("Wired (Ethernet)"))
        self.win = win
        self.devices: dict[str, DeviceRows] = {}
        self.extra_rows: list[Gtk.Widget] = []
        self.busy = False
        refresh = Gtk.Button(
            icon_name="view-refresh-symbolic", valign=Gtk.Align.CENTER, css_classes=["flat"], tooltip_text=_("Refresh")
        )
        refresh.connect("clicked", lambda _b: self.refresh())
        self.set_header_suffix(refresh)
        refresh_while_mapped(self, REFRESH_SECONDS, self._tick)
        self.refresh()

    # -- refreshing (only while the page is visible)
    def _tick(self) -> None:
        if not self.busy:
            self.refresh()

    def refresh(self) -> None:
        if not core.have("nmcli"):
            self._show_message(_("NetworkManager (nmcli) is not available"))
            return
        bg(net.wired_devices, self._populate)

    def _show_message(self, text: str) -> None:
        self._clear()
        row = Adw.ActionRow(title=text)
        self.extra_rows.append(row)
        self.add(row)

    def _clear(self) -> None:
        for d in self.devices.values():
            for row in d.rows:
                self.remove(row)
        for row in self.extra_rows:
            self.remove(row)
        self.devices, self.extra_rows = {}, []

    def _populate(self, devices) -> None:
        if isinstance(devices, Exception):
            return
        if not devices:
            self._show_message(_("No Ethernet port found"))
            return
        if set(self.devices) == {w.device for w in devices}:
            for w in devices:  # same ports: update in place, keeping whatever is being typed in the form
                self.devices[w.device].refresh(w)
            return
        bg(lambda: [(w, net.profile_for(w.device)) for w in devices], self._build)

    def _build(self, pairs) -> None:
        if isinstance(pairs, Exception):
            return
        self._clear()
        for w, profile in pairs:
            title = _("Cable") if len(pairs) == 1 else w.device
            rows = DeviceRows(self, w, profile, title)
            self.devices[w.device] = rows
            for row in rows.rows:
                self.add(row)

    # -- actions
    def toggle_connection(self, d: DeviceRows) -> None:
        connected = d.wired.connected or d.wired.connecting
        self._run(
            lambda: net.disconnect(d.device) if connected else net.connect(d.device),
            _("Disconnected") if connected else _("Connected"),
            d,
        )

    def save(self, d: DeviceRows) -> None:
        try:
            settings, autoconnect = d.fields.read()
        except net.InvalidSettings as err:
            self.win.toast(invalid_message(err))
            return
        commands = net.save_commands(d.device, d.profile, settings, autoconnect)
        self.win.toast(_("Saving and reconnecting…"))
        self._run(lambda: net.run_all(commands), _("Settings saved and connected"), d, saving=True)

    def _run(self, work, ok_message: str, d: DeviceRows, saving: bool = False) -> None:
        self.busy = True
        d.action_btn.set_sensitive(False)
        d.apply_btn.set_sensitive(False)

        def done(result) -> None:
            self.busy = False
            d.apply_btn.set_sensitive(True)
            if isinstance(result, Exception):
                result = (False, str(result), 0)
            ok, error, index = result
            if ok:
                self.win.toast(ok_message)
            elif saving and index > 0:
                self.win.toast(_("Settings saved, but the connection didn't come up: {error}").format(error=error))
            else:
                self.win.toast(_("Failed: {error}").format(error=error))
            if saving:
                self.devices = {}  # rebuild: the profile may have been created or renamed
            self.refresh()

        bg(work, done)
