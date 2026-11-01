"""Network, Bluetooth and audio page (Ethernet, Wi-Fi and Bluetooth settings, audio controls, Omarchy's TUIs)."""
from __future__ import annotations

import re

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

from .. import core
from ..i18n import _
from ..ui import bg, button_row, switch_row
from .bluetooth import BluetoothGroup
from .ethernet import EthernetGroup
from .wifi import WifiGroup

SINK = "@DEFAULT_AUDIO_SINK@"
SOURCE = "@DEFAULT_AUDIO_SOURCE@"


def get_volume(target: str) -> tuple[float, bool]:
    """Returns (volume 0..1.5, muted)."""
    text = core.out(["wpctl", "get-volume", target])
    m = re.search(r"Volume:\s*([\d.]+)", text)
    return (float(m.group(1)) if m else 0.0, "[MUTED]" in text)


class ConnectivityPage(Adw.PreferencesPage):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self._vol_timer = 0

        self.add(EthernetGroup(win))
        self.add(WifiGroup(win, self._tui))

        self.add(BluetoothGroup(win, self._tui))

        audio = Adw.PreferencesGroup(title=_("Audio"))
        self.add(audio)
        self.audio_group = audio
        if core.have("wpctl"):
            bg(lambda: (get_volume(SINK), get_volume(SOURCE)), self._populate_audio)
        audio.add(button_row(_("Full mixer"), _("Devices and per-app volume (wiremix)"), _("Open"),
                             lambda: self._tui("wiremix")))

    def _tui(self, cmd: str) -> None:
        if not core.have(cmd):
            self.win.toast(_("{cmd} is not installed; install it from ☰ → Dependencies").format(cmd=cmd))
            return
        core.launch_tui(cmd)

    # -- Audio
    def _populate_audio(self, result) -> None:
        if isinstance(result, Exception):
            return
        (vol, muted), (_mvol, mic_muted) = result

        row = Adw.ActionRow(title=_("Output volume"), subtitle=_("Default device"))
        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 150, 1)
        scale.set_value(round(vol * 100))
        scale.set_draw_value(True)
        scale.set_value_pos(Gtk.PositionType.RIGHT)
        scale.set_size_request(260, -1)
        scale.set_valign(Gtk.Align.CENTER)
        scale.connect("value-changed", self._on_volume)
        row.add_suffix(scale)
        self.audio_group.add(row)

        self.audio_group.add(switch_row(_("Mute output"), _("Mutes the default device"), muted,
                                        lambda on: self._mute(SINK, on)))
        self.audio_group.add(switch_row(_("Mute microphone"), _("Mutes the default input"), mic_muted,
                                        lambda on: self._mute(SOURCE, on)))

    def _on_volume(self, scale: Gtk.Scale) -> None:
        if self._vol_timer:
            GLib.source_remove(self._vol_timer)
        value = scale.get_value() / 100

        def apply() -> bool:
            self._vol_timer = 0
            bg(lambda: core.run(["wpctl", "set-volume", "-l", "1.5", SINK, f"{value:.2f}"]))
            return False

        self._vol_timer = GLib.timeout_add(150, apply)

    def _mute(self, target: str, on: bool) -> None:
        bg(lambda: core.run(["wpctl", "set-mute", target, "1" if on else "0"]))
