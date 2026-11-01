"""Página de rede, Bluetooth e áudio (atalhos para as TUIs do Omarchy + controles diretos)."""
from __future__ import annotations

import re

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

from .. import core
from ..i18n import _
from ..ui import bg, button_row, switch_row

SINK = "@DEFAULT_AUDIO_SINK@"
SOURCE = "@DEFAULT_AUDIO_SOURCE@"


def get_volume(target: str) -> tuple[float, bool]:
    """Retorna (volume 0..1.5, mudo)."""
    text = core.out(["wpctl", "get-volume", target])
    m = re.search(r"Volume:\s*([\d.]+)", text)
    return (float(m.group(1)) if m else 0.0, "[MUTED]" in text)


def bluetooth_powered() -> bool | None:
    if not core.have("bluetoothctl"):
        return None
    return "Powered: yes" in core.out(["bluetoothctl", "show"])


class ConnectivityPage(Adw.PreferencesPage):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self._vol_timer = 0

        net = Adw.PreferencesGroup(title=_("Network and Bluetooth"))
        net.add(button_row("Wi-Fi", _("Networks and connections (impala)"), _("Open"), lambda: self._tui("impala")))
        net.add(button_row(_("Bluetooth devices"), _("Pair and connect (bluetui)"), _("Open"), lambda: self._tui("bluetui")))
        self.bt_group = net
        self.add(net)
        bg(bluetooth_powered, self._add_bt_switch)

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

    # -- Bluetooth
    def _add_bt_switch(self, powered) -> None:
        if isinstance(powered, Exception) or powered is None:
            return
        self.bt_group.add(switch_row("Bluetooth", _("Turns the adapter on or off"), powered, self._set_bt))

    def _set_bt(self, on: bool) -> None:
        def done(res) -> None:
            if isinstance(res, Exception) or res is None or res.returncode != 0:
                self.win.toast(_("Could not change Bluetooth"))

        bg(lambda: core.run(["bluetoothctl", "power", "on" if on else "off"]), done)

    # -- Áudio
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
