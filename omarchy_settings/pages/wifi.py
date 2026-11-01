"""Wi-Fi group: radio, available networks, password and hidden networks, saved networks with IPv4 settings."""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("NM", "1.0")
from gi.repository import Adw, GLib, Gtk, NM  # noqa: E402

from .. import core
from .. import network as net
from .. import wifi
from ..i18n import _, ngettext
from ..ui import bg, button_row
from .ipv4 import Ipv4Fields, invalid_message

REFRESH_SECONDS = 10
KEY_MGMT = {"psk": "wpa-psk", "sae": "sae"}


def security_label(kind: str, security: str) -> str:
    return {"open": _("Open"), "owe": _("Open (encrypted)"), "enterprise": _("Enterprise (802.1X)")}.get(
        kind, security or _("Secured"))


def save_with_password(ssid: str, password: str, kind: str, hidden: bool, iface: str, done) -> None:
    """Saves a new Wi-Fi profile with its password through libnm (over D-Bus, never on a command line).

    Calls done(uuid, None) or done(None, error) on the UI thread.
    """
    try:
        client = NM.Client.new(None)
        conn = NM.SimpleConnection.new()
        s_con = NM.SettingConnection.new()
        s_con.set_property(NM.SETTING_CONNECTION_ID, ssid)
        s_con.set_property(NM.SETTING_CONNECTION_UUID, NM.utils_uuid_generate())
        s_con.set_property(NM.SETTING_CONNECTION_TYPE, NM.SETTING_WIRELESS_SETTING_NAME)
        s_con.set_property(NM.SETTING_CONNECTION_INTERFACE_NAME, iface)
        s_wifi = NM.SettingWireless.new()
        s_wifi.set_property(NM.SETTING_WIRELESS_SSID, GLib.Bytes.new(ssid.encode()))
        s_wifi.set_property(NM.SETTING_WIRELESS_HIDDEN, hidden)
        s_ip4 = NM.SettingIP4Config.new()
        s_ip4.set_property(NM.SETTING_IP_CONFIG_METHOD, "auto")
        settings = [s_con, s_wifi, s_ip4]
        if kind in KEY_MGMT:
            s_sec = NM.SettingWirelessSecurity.new()
            s_sec.set_property(NM.SETTING_WIRELESS_SECURITY_KEY_MGMT, KEY_MGMT[kind])
            s_sec.set_property(NM.SETTING_WIRELESS_SECURITY_PSK, password)
            settings.append(s_sec)
        for setting in settings:
            conn.add_setting(setting)
        conn.verify()
    except GLib.Error as err:
        done(None, err.message)
        return

    def finished(c, result) -> None:
        try:
            done(c.add_connection_finish(result).get_uuid(), None)
        except GLib.Error as err:
            done(None, err.message)

    client.add_connection_async(conn, True, None, finished)


class PasswordDialog(Adw.AlertDialog):
    """Asks for a password; with hidden=True also for the network name and security."""

    SECURITY = [("psk", "WPA/WPA2"), ("sae", "WPA3"), ("open", None)]

    def __init__(self, ssid: str | None, on_connect):
        super().__init__(heading=_("Connect to “{ssid}”").format(ssid=ssid) if ssid else _("Hidden network"))
        self.ssid = ssid
        self.on_connect = on_connect
        group = Adw.PreferencesGroup()
        self.name = Adw.EntryRow(title=_("Network name (SSID)"))
        self.security = Adw.ComboRow(title=_("Security"))
        self.security.set_model(Gtk.StringList.new([label or _("None") for _k, label in self.SECURITY]))
        self.password = Adw.PasswordEntryRow(title=_("Password"))
        if ssid is None:
            group.add(self.name)
            group.add(self.security)
            self.name.connect("changed", lambda *_args: self._update())
            self.security.connect("notify::selected", lambda *_args: self._update())
        group.add(self.password)
        self.password.connect("changed", lambda *_args: self._update())
        self.password.connect("entry-activated", lambda *_args: self._activate())
        self.hint = Gtk.Label(css_classes=["dim-label"], wrap=True, margin_top=6)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.append(group)
        box.append(self.hint)
        self.set_extra_child(box)
        self.add_response("cancel", _("Cancel"))
        self.add_response("connect", _("Connect"))
        self.set_response_appearance("connect", Adw.ResponseAppearance.SUGGESTED)
        self.set_default_response("connect")
        self.set_close_response("cancel")
        self.connect("response", self._on_response)
        self._update()

    def kind(self) -> str:
        return self.SECURITY[self.security.get_selected()][0] if self.ssid is None else "psk"

    def _update(self) -> None:
        needs_password = self.kind() != "open"
        self.password.set_visible(needs_password)
        length = len(self.password.get_text())
        ok_password = not needs_password or 8 <= length <= 63
        ok_name = self.ssid is not None or bool(self.name.get_text().strip())
        self.hint.set_label(_("WPA passwords have 8 to 63 characters.") if needs_password and length and
                            not ok_password else "")
        self.set_response_enabled("connect", ok_password and ok_name)

    def _activate(self) -> None:
        """Enter in the password field connects, like the Connect button."""
        if self.get_response_enabled("connect"):
            self.response("connect")
            self.force_close()

    def _on_response(self, _d, response: str) -> None:
        if response == "connect":
            ssid = self.ssid or self.name.get_text().strip()
            self.on_connect(ssid, self.password.get_text() if self.kind() != "open" else "", self.kind(),
                            self.ssid is None)


class WifiGroup(Adw.PreferencesGroup):
    def __init__(self, win, open_tui):
        super().__init__(title=_("Wi-Fi"))
        self.win = win
        self.open_tui = open_tui
        self.rows: list[Gtk.Widget] = []
        self.snapshot = None
        self.busy = False
        self.iface = ""
        self.expanded = {"networks": True, "saved": False}
        scan = Gtk.Button(icon_name="view-refresh-symbolic", valign=Gtk.Align.CENTER, css_classes=["flat"],
                          tooltip_text=_("Search for networks"))
        scan.connect("clicked", lambda _b: self.refresh(rescan=True))
        self.set_header_suffix(scan)
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
        if not self.busy:
            self.refresh()
        return True

    def refresh(self, rescan: bool = False) -> None:
        if not core.have("nmcli"):
            self._rebuild({"error": _("NetworkManager (nmcli) is not available")})
            return

        def load() -> dict:
            dev = wifi.device()
            if dev is None:
                return {"error": _("No Wi-Fi adapter found")}
            radio = wifi.radio_enabled()
            info = net.parse_fields(core.out(["nmcli", "-t", "-f", "GENERAL.CONNECTION,IP4.ADDRESS", "device",
                                              "show", dev[0]]))
            return {"iface": dev[0], "state": dev[1], "radio": radio,
                    "connection": (info.get("GENERAL.CONNECTION") or [""])[0],
                    "ip": (info.get("IP4.ADDRESS") or [""])[0].split("/")[0],
                    "networks": wifi.scan(rescan) if radio else [], "saved": wifi.saved()}

        bg(load, self._rebuild)

    # -- building
    def _clear(self) -> None:
        for row in self.rows:
            self.remove(row)
        self.rows = []

    def _add(self, row: Gtk.Widget) -> None:
        self.rows.append(row)
        self.add(row)

    def _rebuild(self, data) -> None:
        if isinstance(data, Exception):
            return
        if data == self.snapshot:
            return  # nothing changed: keep the rows (and whatever is expanded) as they are
        self.snapshot = data
        self._clear()
        if "error" in data:
            self._add(Adw.ActionRow(title=data["error"]))
            return
        self.iface = data["iface"]

        status = _("Off")
        if data["radio"]:
            if data["state"].startswith("connected") and data["connection"]:
                status = _("Connected to {name}").format(name=data["connection"])
                if data["ip"]:
                    status += f" · {data['ip']}"
            elif data["state"].startswith("connecting"):
                status = _("Connecting…")
            else:
                status = _("Not connected")
        radio = Adw.SwitchRow(title=_("Wi-Fi"), subtitle=status, active=data["radio"])
        radio.connect("notify::active", lambda r, _p: self._set_radio(r.get_active()))
        self._add(radio)

        saved_by_ssid = {s.ssid: s for s in data["saved"]}
        if data["radio"]:
            networks = Adw.ExpanderRow(title=_("Available networks"), expanded=self.expanded["networks"],
                                       subtitle=ngettext("{n} found", "{n} found", len(data["networks"])).format(n=len(data["networks"])))
            networks.connect("notify::expanded", lambda e, _p: self.expanded.update(networks=e.get_expanded()))
            if not data["networks"]:
                networks.add_row(Adw.ActionRow(title=_("No networks found"),
                                               subtitle=_("Use the refresh button above to search again")))
            for n in data["networks"]:
                networks.add_row(self._network_row(n, saved_by_ssid.get(n.ssid)))
            self._add(networks)
            self._add(button_row(_("Hidden network"), _("Connect to a network that doesn't broadcast its name"),
                                 _("Connect…"), lambda: self._ask_password(None)))

        if data["saved"]:
            saved = Adw.ExpanderRow(title=_("Saved networks"), expanded=self.expanded["saved"],
                                    subtitle=ngettext("{n} saved", "{n} saved", len(data["saved"])).format(n=len(data["saved"])))
            saved.connect("notify::expanded", lambda e, _p: self.expanded.update(saved=e.get_expanded()))
            for s in data["saved"]:
                saved.add_row(self._saved_row(s))
            self._add(saved)
        self._add(button_row(_("Advanced"), _("Full Wi-Fi manager (impala)"), _("Open"),
                             lambda: self.open_tui("impala")))

    def _network_row(self, n: wifi.Network, saved: wifi.Saved | None) -> Adw.ActionRow:
        if n.in_use:
            subtitle = _("Connected")
        elif saved:
            subtitle = _("Saved") + " · " + security_label(n.kind, n.security)
        else:
            subtitle = security_label(n.kind, n.security)
        row = Adw.ActionRow(title=n.ssid, subtitle=subtitle, use_markup=False)
        row.add_prefix(Gtk.Image(icon_name=wifi.signal_icon(n.signal), tooltip_text=f"{n.signal}%"))
        if n.kind not in ("open", "owe"):
            row.add_suffix(Gtk.Image(icon_name="changes-prevent-symbolic", css_classes=["dim-label"]))
        btn = Gtk.Button(label=_("Disconnect") if n.in_use else _("Connect"), valign=Gtk.Align.CENTER)
        btn.connect("clicked", lambda _b: self._disconnect() if n.in_use else self._connect(n, saved))
        row.add_suffix(btn)
        return row

    def _saved_row(self, s: wifi.Saved) -> Adw.ActionRow:
        subtitle = _("Connected") if s.active else (_("Connects automatically") if s.autoconnect
                                                     else _("Doesn't connect automatically"))
        if s.name != s.ssid:  # several profiles can exist for the same network
            subtitle += " · " + _("profile “{name}”").format(name=s.name)
        row = Adw.ActionRow(title=s.ssid, subtitle=subtitle, use_markup=False)
        settings = Gtk.Button(icon_name="emblem-system-symbolic", valign=Gtk.Align.CENTER, css_classes=["flat"],
                              tooltip_text=_("IPv4 settings"))
        settings.connect("clicked", lambda _b: self._edit_saved(s))
        forget = Gtk.Button(icon_name="user-trash-symbolic", valign=Gtk.Align.CENTER, css_classes=["flat"],
                            tooltip_text=_("Forget"))
        forget.connect("clicked", lambda _b: self._confirm_forget(s))
        row.add_suffix(settings)
        row.add_suffix(forget)
        return row

    # -- actions
    def _run(self, commands: list[list[str]], ok_message: str, on_fail=None) -> None:
        self.busy = True

        def done(result) -> None:
            self.busy = False
            if isinstance(result, Exception):
                result = (False, str(result), 0)
            ok, error, _index = result
            if ok:
                self.win.toast(ok_message)
            elif on_fail:
                on_fail(error)
            else:
                self.win.toast(_("Failed: {error}").format(error=error))
            self.snapshot = None
            self.refresh()

        bg(lambda: net.run_all(commands), done)

    def _set_radio(self, on: bool) -> None:
        def done(_result) -> None:
            self.snapshot = None
            self.refresh(rescan=on)

        bg(lambda: wifi.set_radio(on), done)

    def _disconnect(self) -> None:
        self._run([["nmcli", "device", "disconnect", self.iface]], _("Disconnected"))

    def _connect(self, n: wifi.Network, saved: wifi.Saved | None) -> None:
        if saved:
            self.win.toast(_("Connecting to {ssid}…").format(ssid=n.ssid))
            self._run([wifi.connect_saved(saved.uuid, self.iface)], _("Connected to {name}").format(name=n.ssid))
        elif n.kind in ("open", "owe"):
            self.win.toast(_("Connecting to {ssid}…").format(ssid=n.ssid))
            self._run([wifi.connect_open(n.ssid, self.iface)], _("Connected to {name}").format(name=n.ssid))
        elif n.kind == "enterprise":
            self.win.toast(_("Enterprise (802.1X) networks need more settings; use Advanced (impala)"))
        else:
            self._ask_password(n)

    def _ask_password(self, n: wifi.Network | None) -> None:
        def connect(ssid: str, password: str, kind: str, hidden: bool) -> None:
            if n is not None:
                kind = n.kind
            self.win.toast(_("Connecting to {ssid}…").format(ssid=ssid))
            self.busy = True

            def saved(uuid, error) -> None:
                if uuid is None:
                    self.busy = False
                    self.win.toast(_("Failed: {error}").format(error=error))
                    return

                def failed(err: str) -> None:
                    # a failed new network is not kept, so a wrong password isn't left saved
                    bg(lambda: core.run(wifi.forget(uuid)))
                    reason = wifi.failure_reason(err)
                    messages = {"wrong-password": _("Wrong password for {ssid}"),
                                "not-found": _("Network {ssid} not found"),
                                "unavailable": _("Wi-Fi is off or unavailable")}
                    self.win.toast(messages[reason].format(ssid=ssid) if reason in messages
                                   else _("Failed: {error}").format(error=err))

                self._run([wifi.connect_saved(uuid, self.iface)], _("Connected to {name}").format(name=ssid),
                          on_fail=failed)

            save_with_password(ssid, password, kind, hidden, self.iface, saved)

        PasswordDialog(n.ssid if n else None, connect).present(self.win)

    def _edit_saved(self, s: wifi.Saved) -> None:
        def show(profile) -> None:
            if not isinstance(profile, net.Profile):
                self.win.toast(_("Could not read the settings of {ssid}").format(ssid=s.ssid))
                return
            fields = Ipv4Fields(profile, _("When the network is in range"))
            dialog = Adw.AlertDialog(heading=s.ssid)
            group = Adw.PreferencesGroup()
            for row in fields.rows:
                group.add(row)
            dialog.set_extra_child(group)
            dialog.add_response("cancel", _("Cancel"))
            dialog.add_response("save", _("Save"))
            dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)
            dialog.set_close_response("cancel")

            def on_response(_d, response: str) -> None:
                if response != "save":
                    return
                try:
                    settings, autoconnect = fields.read()
                except net.InvalidSettings as err:
                    self.win.toast(invalid_message(err))
                    return
                commands = net.save_commands(self.iface, profile, settings, autoconnect)
                if not s.active:
                    commands = commands[:1]  # only reconnect the network in use
                self._run(commands, _("Settings saved"))

            dialog.connect("response", on_response)
            dialog.present(self.win)

        bg(lambda: net.read_profile(s.uuid), show)

    def _confirm_forget(self, s: wifi.Saved) -> None:
        dialog = Adw.AlertDialog(heading=_("Forget “{ssid}”?").format(ssid=s.ssid),
                                 body=_("The saved password and settings are deleted."))
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("forget", _("Forget"))
        dialog.set_response_appearance("forget", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_close_response("cancel")
        dialog.connect("response", lambda _d, r: r == "forget" and self._run(
            [wifi.forget(s.uuid)], _("{ssid} forgotten").format(ssid=s.ssid)))
        dialog.present(self.win)
