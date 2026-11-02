"""Sound page: output and input devices, their volume, per-app volume, test sound and the full mixer (wiremix).

Updates live from `pactl subscribe` while the page is visible."""
from __future__ import annotations

import subprocess
import threading
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402

from .. import core, sound
from ..i18n import _
from ..ui import bg, button_row, switch_row

REFRESH_DELAY = 300  # ms: pactl sends bursts of events; one read covers a whole burst
USER_GRACE = 1.0  # s: a volume the user just moved isn't overwritten by the events it causes
OVERAMP_KEY = "sound_overamp"


class VolumeRow(Adw.ActionRow):
    """Volume scale plus mute button for one device or stream; `kind` is a pactl object type."""

    def __init__(self, kind: str, title: str, subtitle: str = "", icon: str | None = None):
        super().__init__(title=title, subtitle=subtitle, use_markup=False, title_lines=1, subtitle_lines=1)
        self.kind = kind
        self.index: int | None = None
        self._timer = 0
        self._touched = 0.0
        self._syncing = False
        if icon:
            theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
            self.add_prefix(Gtk.Image(icon_name=icon if theme.has_icon(icon) else "audio-x-generic-symbolic",
                                      pixel_size=24))
        self.scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.scale.set_draw_value(True)
        self.scale.set_value_pos(Gtk.PositionType.RIGHT)
        self.scale.set_format_value_func(lambda _s, v: f"{v:.0f}%")
        self.scale.set_size_request(240, -1)
        self.scale.set_valign(Gtk.Align.CENTER)
        self.scale.connect("value-changed", self._on_volume)
        self.mute = Gtk.ToggleButton(icon_name="audio-volume-high-symbolic", valign=Gtk.Align.CENTER,
                                     tooltip_text=_("Mute"), css_classes=["flat"])
        self.mute.connect("toggled", self._on_mute)
        self.add_suffix(self.scale)
        self.add_suffix(self.mute)

    def update(self, index: int, volume: float, muted: bool, limit: int) -> None:
        self.index = index
        if time.monotonic() - self._touched < USER_GRACE or self._timer:
            return
        self._syncing = True
        percent = round(volume * 100)
        self.scale.set_range(0, max(limit, percent))
        self.scale.set_value(percent)
        self.mute.set_active(muted)
        self._mute_icon(muted)
        self._syncing = False

    def set_limit(self, limit: int) -> None:
        self._syncing = True
        self.scale.set_range(0, max(limit, self.scale.get_value()))
        self._syncing = False

    def _mute_icon(self, muted: bool) -> None:
        self.mute.set_icon_name("audio-volume-muted-symbolic" if muted else "audio-volume-high-symbolic")
        self.mute.set_tooltip_text(_("Unmute") if muted else _("Mute"))

    def _on_volume(self, scale: Gtk.Scale) -> None:
        if self._syncing or self.index is None:
            return
        self._touched = time.monotonic()
        if self._timer:
            GLib.source_remove(self._timer)
        kind, index, value = self.kind, self.index, scale.get_value() / 100

        def apply() -> bool:
            self._timer = 0
            self._touched = time.monotonic()
            bg(lambda: sound.set_volume(kind, index, value))
            return False

        self._timer = GLib.timeout_add(150, apply)

    def _on_mute(self, button: Gtk.ToggleButton) -> None:
        self._mute_icon(button.get_active())
        if self._syncing or self.index is None:
            return
        self._touched = time.monotonic()
        kind, index, on = self.kind, self.index, button.get_active()
        bg(lambda: sound.set_mute(kind, index, on))


class Watcher:
    """Runs `pactl subscribe` and calls on_event (on the UI thread) for every event line."""

    def __init__(self, on_event):
        self.on_event = on_event
        self.proc: subprocess.Popen | None = None

    def start(self) -> None:
        if self.proc is not None:
            return
        try:
            self.proc = subprocess.Popen(["pactl", "subscribe"], stdout=subprocess.PIPE,
                                         stderr=subprocess.DEVNULL, text=True)
        except OSError:
            return
        threading.Thread(target=self._read, args=(self.proc,), daemon=True).start()

    def _read(self, proc: subprocess.Popen) -> None:
        for line in proc.stdout:
            if "Event" in line and "client" not in line:
                GLib.idle_add(lambda: self.on_event() or False)

    def stop(self) -> None:
        if self.proc is not None:
            self.proc.kill()
            self.proc.wait()
            self.proc = None


class DeviceGroup(Adw.PreferencesGroup):
    """Device choice (the default one) plus the volume of the chosen device."""

    def __init__(self, page, kind: str, title: str, chooser: str, volume: str, empty: str):
        super().__init__(title=title)
        self.page, self.kind, self.empty = page, kind, empty
        self.names: list[str] = []
        self._syncing = False
        self.combo = Adw.ComboRow(title=chooser)
        self.combo.set_model(Gtk.StringList.new([]))
        self.combo.connect("notify::selected", self._on_selected)
        self.volume = VolumeRow(kind, volume)
        self.add(self.combo)
        self.add(self.volume)

    def update(self, devices: list[sound.Device], default: str, limit: int) -> None:
        self._syncing = True
        names = [d.name for d in devices]
        if names != self.names:
            self.names = names
            self.combo.set_model(Gtk.StringList.new([d.description for d in devices] or [self.empty]))
        current = next((d for d in devices if d.name == default), devices[0] if devices else None)
        if current:
            self.combo.set_selected(names.index(current.name))
            self.volume.update(current.index, current.volume, current.muted, limit)
        self.combo.set_sensitive(bool(devices))
        self.volume.set_visible(current is not None)
        self._syncing = False

    def _on_selected(self, row, _p) -> None:
        i = row.get_selected()
        if self._syncing or not 0 <= i < len(self.names):
            return
        name = self.names[i]
        bg(lambda: sound.set_default(self.kind, name),
           lambda ok: None if ok is True else self.page.win.toast(_("Could not change the device")))


class StreamGroup(Adw.PreferencesGroup):
    """One row per app stream, kept in place across updates so a moving scale isn't rebuilt."""

    def __init__(self, kind: str, title: str, description: str, empty: str):
        super().__init__(title=title, description=description)
        self.kind = kind
        self.rows: dict[int, VolumeRow] = {}
        self.placeholder = Adw.ActionRow(title=empty, css_classes=["dim-label"])
        self.add(self.placeholder)

    def update(self, streams: list[sound.Stream], limit: int) -> None:
        live = {s.index for s in streams}
        for index in [i for i in self.rows if i not in live]:
            self.remove(self.rows.pop(index))
        for s in streams:
            row = self.rows.get(s.index)
            if row is None:
                row = self.rows[s.index] = VolumeRow(self.kind, s.app, s.media, s.icon)
                self.add(row)
            else:
                row.set_title(s.app)
                row.set_subtitle(s.media)
            row.update(s.index, s.volume, s.muted, limit)
        self.placeholder.set_visible(not streams)

    def set_limit(self, limit: int) -> None:
        for row in self.rows.values():
            row.set_limit(limit)


class SoundPage(Adw.PreferencesPage):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.store = win.store
        self._refresh_timer = 0
        self._loading = False
        self.overamp = bool(self.store.extras.get(OVERAMP_KEY))

        if not core.have("pactl"):
            group = Adw.PreferencesGroup(title=_("Sound"))
            group.add(Adw.ActionRow(title=_("pactl is not installed"),
                                    subtitle=_("It comes with PipeWire's PulseAudio support (pipewire-pulse)")))
            self.add(group)
            return

        self.output = DeviceGroup(self, "sink", _("Output"), _("Output device"), _("Volume"),
                                  _("No output device"))
        self.add(self.output)
        test = sound.find_test_sound()
        if test is not None and core.have("pw-play"):
            self.output.add(button_row(_("Test sound"), _("Plays a short sound on the output device"),
                                       _("Play"), lambda: bg(lambda: sound.play(test))))
        self.output.add(switch_row(_("Allow volume above 100%"), _("Louder, but the sound may distort"),
                                   self.overamp, self._set_overamp))

        self.input = DeviceGroup(self, "source", _("Input"), _("Microphone"), _("Input volume"),
                                 _("No microphone"))
        self.add(self.input)

        self.playing = StreamGroup("sink-input", _("Apps playing"), _("Volume of each app playing sound."),
                                   _("Nothing is playing"))
        self.add(self.playing)
        self.recording = StreamGroup("source-output", _("Using the microphone"),
                                     _("Apps recording sound right now."), _("No app is using the microphone"))
        self.add(self.recording)

        advanced = Adw.PreferencesGroup(title=_("Advanced"))
        advanced.add(button_row(_("Full mixer"), _("Profiles, moving an app to another device (wiremix)"),
                                _("Open"), self._mixer))
        self.add(advanced)

        self.watcher = Watcher(self._schedule_refresh)
        self.connect("map", lambda _w: (self.watcher.start(), self._refresh()))
        self.connect("unmap", lambda _w: self.watcher.stop())
        self._refresh()

    def limit(self) -> int:
        return 150 if self.overamp else 100

    def _schedule_refresh(self) -> None:
        if self._refresh_timer:
            return  # at most one read per REFRESH_DELAY, even under a steady flow of events

        def fire() -> bool:
            self._refresh_timer = 0
            self._refresh()
            return False

        self._refresh_timer = GLib.timeout_add(REFRESH_DELAY, fire)

    def _refresh(self) -> None:
        if self._loading:
            self._schedule_refresh()  # read again once the running read ends
            return
        self._loading = True
        bg(sound.snapshot, self._apply)

    def _apply(self, snap) -> None:
        self._loading = False
        if isinstance(snap, Exception):
            return
        limit = self.limit()
        self.output.update(snap.outputs, snap.default_output, limit)
        self.input.update(snap.inputs, snap.default_input, limit)
        self.playing.update(snap.playing, limit)
        self.recording.update(snap.recording, limit)

    def _set_overamp(self, on: bool) -> None:
        self.overamp = on
        bg(lambda: self.store.set_extra(OVERAMP_KEY, True if on else None, reload=False))
        limit = self.limit()
        for row in (self.output.volume, self.input.volume):
            row.set_limit(limit)
        self.playing.set_limit(limit)
        self.recording.set_limit(limit)

    def _mixer(self) -> None:
        if not core.have("wiremix"):
            self.win.toast(_("{cmd} is not installed; install it from ☰ → Dependencies").format(cmd="wiremix"))
            return
        core.launch_tui("wiremix")
