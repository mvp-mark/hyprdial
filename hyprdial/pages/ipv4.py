"""IPv4 form shared by wired and Wi-Fi connections: DHCP or manual address, DNS, auto-connect."""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from .. import network as net
from ..i18n import _

METHODS = ["auto", "manual"]


class Ipv4Fields:
    """Rows for a NetworkManager profile's IPv4 settings; the caller places `rows` where it wants."""

    def __init__(
        self,
        profile: net.Profile | None,
        autoconnect_subtitle: str,
        on_method_changed: Callable[[str], None] | None = None,
    ):
        p = profile or net.Profile(uuid="", name="")
        self.on_method_changed = on_method_changed
        self.method = Adw.ComboRow(title=_("Address"))
        self.method.set_model(Gtk.StringList.new([_("Automatic (DHCP)"), _("Manual")]))
        self.method.set_selected(1 if p.method == "manual" else 0)
        self.method.connect("notify::selected", lambda *_args: self._update())
        self.address = Adw.EntryRow(
            title=_("IP address (e.g. 192.168.1.50/24)"), text=p.addresses[0] if p.addresses else ""
        )
        self.gateway = Adw.EntryRow(title=_("Gateway (e.g. 192.168.1.1)"), text=p.gateway)
        self.dns = Adw.EntryRow(title=_("DNS servers, comma separated (optional)"), text=", ".join(p.dns))
        self.autoconnect = Adw.SwitchRow(
            title=_("Connect automatically"), subtitle=autoconnect_subtitle, active=p.autoconnect
        )
        for entry in (self.address, self.gateway, self.dns):
            entry.connect("changed", lambda e: e.remove_css_class("error"))
        self.rows: list[Gtk.Widget] = [self.method, self.address, self.gateway, self.dns, self.autoconnect]
        self._update()

    def summary(self) -> str:
        return _("Manual") if self._method() == "manual" else _("Automatic (DHCP)")

    def _method(self) -> str:
        return METHODS[self.method.get_selected()]

    def _update(self) -> None:
        manual = self._method() == "manual"
        self.address.set_visible(manual)
        self.gateway.set_visible(manual)
        if self.on_method_changed:
            self.on_method_changed(self.summary())

    def read(self) -> tuple[dict, bool]:
        """(settings for nmcli, autoconnect). Raises net.InvalidSettings and marks the bad field."""
        try:
            settings = net.normalize(
                self._method(), self.address.get_text(), self.gateway.get_text(), self.dns.get_text()
            )
        except net.InvalidSettings as err:
            {"address": self.address, "gateway": self.gateway, "dns": self.dns}[err.field].add_css_class("error")
            raise
        if settings["method"] == "manual":
            self.address.set_text(settings["address"])  # shows the /24 that was added
        return settings, self.autoconnect.get_active()


def invalid_message(err: net.InvalidSettings) -> str:
    return {
        "address": _("Invalid IP address: {value}"),
        "gateway": _("Invalid gateway: {value}"),
        "dns": _("Invalid DNS server: {value}"),
    }[err.field].format(value=err.value)
