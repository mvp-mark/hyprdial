"""Saving a Wi-Fi network with its password through libnm, over D-Bus, so the password never appears on a command
line. No GTK, but it needs PyGObject's NM bindings, so it isn't part of the unit tests."""

from __future__ import annotations

import gi

gi.require_version("NM", "1.0")
from gi.repository import NM, GLib  # noqa: E402

KEY_MGMT = {"psk": "wpa-psk", "sae": "sae"}


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
