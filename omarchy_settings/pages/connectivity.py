"""Network and Bluetooth page (Ethernet, Wi-Fi and Bluetooth settings, Omarchy's TUIs)."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw  # noqa: E402

from ..ui import launch_tui
from .bluetooth import BluetoothGroup
from .ethernet import EthernetGroup
from .wifi import WifiGroup


class ConnectivityPage(Adw.PreferencesPage):
    def __init__(self, win):
        super().__init__()
        self.win = win

        self.add(EthernetGroup(win))
        self.add(WifiGroup(win, lambda cmd: launch_tui(win, cmd)))

        self.add(BluetoothGroup(win, lambda cmd: launch_tui(win, cmd)))
