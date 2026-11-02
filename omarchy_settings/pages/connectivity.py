"""Network and Bluetooth page (Ethernet, Wi-Fi and Bluetooth settings, Omarchy's TUIs)."""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw  # noqa: E402

from .. import core
from ..i18n import _
from .bluetooth import BluetoothGroup
from .ethernet import EthernetGroup
from .wifi import WifiGroup


class ConnectivityPage(Adw.PreferencesPage):
    def __init__(self, win):
        super().__init__()
        self.win = win

        self.add(EthernetGroup(win))
        self.add(WifiGroup(win, self._tui))

        self.add(BluetoothGroup(win, self._tui))

    def _tui(self, cmd: str) -> None:
        if not core.have(cmd):
            self.win.toast(_("{cmd} is not installed; install it from ☰ → Dependencies").format(cmd=cmd))
            return
        core.launch_tui(cmd)
