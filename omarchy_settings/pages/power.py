"""Power page: power profile, night light (on/off, warmth, schedule), power button and idle."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from .. import core, power
from ..i18n import _
from ..ui import Debouncer, bg, combo_row, missing_row, switch_row
from .bar import IDLE_TIMES, STAY_AWAKE_FLAG, command, idle_label, read_shell, write_idle

PROFILE_LABELS = {
    "power-saver": (_("Power saver"), _("Less heat and noise, lower performance")),
    "balanced": (_("Balanced"), _("Performance when needed, saves power otherwise")),
    "performance": (_("Performance"), _("Highest performance, more power and heat")),
}
BUTTON_ACTIONS = [
    ("menu", _("Show the system menu")),
    ("lock", _("Lock the screen")),
    ("suspend", _("Suspend")),
    ("shutdown", _("Shut down")),
    ("nothing", _("Do nothing")),
]


class PowerPage(Adw.PreferencesPage):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.store = win.store
        self._warmth = Debouncer(300, self._apply_warmth)
        self._syncing = False

        self.profile_group = Adw.PreferencesGroup(title=_("Power profile"))
        self.add(self.profile_group)
        if core.have("powerprofilesctl"):
            bg(power.profiles, self._populate_profiles)
        else:
            self.profile_group.add(missing_row("power-profiles-daemon"))

        self.night_group = Adw.PreferencesGroup(
            title=_("Night light"), description=_("Warmer screen colors to reduce blue light.")
        )
        self.add(self.night_group)
        if core.have("hyprsunset"):
            bg(lambda: (power.temperature(), self._read_schedule()), self._populate_night)
        else:
            self.night_group.add(missing_row("hyprsunset"))

        button = Adw.PreferencesGroup(title=_("Power button"))
        current = self.store.extras.get("power_button", "menu")
        keys = [k for k, _label in BUTTON_ACTIONS]
        button.add(
            combo_row(
                _("When the power button is pressed"),
                _("Works on the lock screen too"),
                [label for _k, label in BUTTON_ACTIONS],
                keys.index(current) if current in keys else 0,
                lambda i: self._set_button(keys[i]),
            )
        )
        self.add(button)

        self._idle_group(read_shell())

    # -- power profile
    def _populate_profiles(self, result) -> None:
        if isinstance(result, Exception) or not result[0]:
            self.profile_group.add(Adw.ActionRow(title=_("No power profiles available")))
            return
        available, active = result
        row = Adw.ComboRow(title=_("Profile"))
        row.set_model(Gtk.StringList.new([PROFILE_LABELS[p][0] for p in available]))
        if active in available:
            row.set_selected(available.index(active))
        row.set_subtitle(PROFILE_LABELS[available[row.get_selected()]][1])

        def changed(r, _p) -> None:
            name = available[r.get_selected()]
            r.set_subtitle(PROFILE_LABELS[name][1])
            bg(
                lambda: power.set_profile(name),
                lambda ok: None if ok is True else self.win.toast(_("Could not change the power profile")),
            )

        row.connect("notify::selected", changed)
        self.profile_group.add(row)

    # -- night light
    def _read_schedule(self):
        try:
            return power.parse_schedule(power.HYPRSUNSET_CONF.read_text())
        except OSError:
            return None

    def _populate_night(self, result) -> None:
        if isinstance(result, Exception):
            return
        temp, schedule = result
        scheduled = bool(self.store.extras.get("nightlight_schedule")) and schedule is not None
        warmth = self.store.extras.get("nightlight_temp") or (schedule[2] if schedule else power.DEFAULT_TEMP)

        self.night_switch = switch_row(
            _("Night light"), _("Turns it on or off now"), power.nightlight_on(temp), self._set_night
        )
        self.night_group.add(self.night_switch)

        row = Adw.ActionRow(title=_("Warmth"), subtitle=_("Lower is warmer"))
        self.warmth = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 2500, 6000, 100)
        self.warmth.set_value(warmth)
        self.warmth.set_draw_value(True)
        self.warmth.set_format_value_func(lambda _s, v: f"{int(v)} K")
        self.warmth.set_value_pos(Gtk.PositionType.RIGHT)
        self.warmth.set_size_request(260, -1)
        self.warmth.set_valign(Gtk.Align.CENTER)
        self.warmth.connect("value-changed", self._on_warmth)
        row.add_suffix(self.warmth)
        self.night_group.add(row)

        start, end = (schedule[0], schedule[1]) if schedule else ("20:00", "07:00")
        self.schedule = Adw.ExpanderRow(
            title=_("Turn on automatically"),
            show_enable_switch=True,
            enable_expansion=scheduled,
            expanded=scheduled,
            subtitle=_("Every day at the times below"),
        )
        self.start = Adw.EntryRow(title=_("Turns on at (HH:MM)"), text=start, show_apply_button=True)
        self.end = Adw.EntryRow(title=_("Turns off at (HH:MM)"), text=end, show_apply_button=True)
        for entry in (self.start, self.end):
            entry.connect("apply", lambda _e: self._save_schedule(True))
            entry.connect("changed", lambda e: e.remove_css_class("error"))
            self.schedule.add_row(entry)
        self.schedule.connect("notify::enable-expansion", lambda r, _p: self._save_schedule(r.get_enable_expansion()))
        self.night_group.add(self.schedule)

    def _set_night(self, on: bool) -> None:
        temp = int(self.warmth.get_value()) if on else power.OFF_TEMP
        bg(
            lambda: power.set_temperature(temp),
            lambda ok: None if ok is True else self.win.toast(_("Could not change the night light")),
        )

    def _on_warmth(self, scale: Gtk.Scale) -> None:
        self._warmth(int(scale.get_value()))

    def _apply_warmth(self, temp: int) -> None:
        on = self.night_switch.get_active()
        scheduled = self.schedule.get_enable_expansion()

        def work() -> None:
            self.store.set_extra("nightlight_temp", temp, reload=False)
            if on:
                power.set_temperature(temp)
            if scheduled:
                self._write_schedule(temp)

        bg(work)

    def _schedule_times(self) -> tuple[str, str] | None:
        start, end = power.valid_time(self.start.get_text()), power.valid_time(self.end.get_text())
        for entry, value in ((self.start, start), (self.end, end)):
            if value is None:
                entry.add_css_class("error")
        if start is None or end is None:
            self.win.toast(_("Use times like 20:00 and 07:00"))
            return None
        if start == end:
            self.end.add_css_class("error")
            self.win.toast(_("The start and end times must be different"))
            return None
        self.start.set_text(start)
        self.end.set_text(end)
        return start, end

    def _write_schedule(self, temp: int) -> None:
        start, end = power.valid_time(self.start.get_text()), power.valid_time(self.end.get_text())
        if start and end and start != end:
            power.write_schedule(start, end, temp)
            core.run(["omarchy-restart-hyprsunset"], timeout=15)

    def _save_schedule(self, on: bool) -> None:
        if self._syncing:
            return
        temp = int(self.warmth.get_value())
        if on:
            times = self._schedule_times()
            if times is None:
                self._syncing = True  # back to off without "turning off" a schedule that was never saved
                self.schedule.set_enable_expansion(False)
                self._syncing = False
                return

            def work() -> None:
                power.write_schedule(*times, temp)
                self.store.set_extra("nightlight_schedule", True)
                core.run(["omarchy-restart-hyprsunset"], timeout=15)

            bg(
                work,
                lambda r: self.win.toast(
                    _("Night light scheduled from {start} to {end}").format(start=times[0], end=times[1])
                    if not isinstance(r, Exception)
                    else _("Could not save the schedule")
                ),
            )
        else:

            def work() -> None:
                power.restore_schedule()
                self.store.set_extra("nightlight_schedule", None)
                core.run(["omarchy-restart-hyprsunset"], timeout=15)

            bg(
                work,
                lambda r: self.win.toast(
                    _("Night light schedule turned off")
                    if not isinstance(r, Exception)
                    else _("Could not save the schedule")
                ),
            )

    # -- power button
    def _set_button(self, action: str) -> None:
        bg(
            lambda: self.store.set_extra("power_button", None if action == "menu" else action),
            lambda r: self.win.toast(
                _("Power button changed") if not isinstance(r, Exception) else _("Could not save the setting")
            ),
        )

    # -- idle
    def _idle_group(self, config: dict) -> None:
        idle = config.get("idle") if isinstance(config.get("idle"), dict) else {}
        self.idle_group = Adw.PreferencesGroup(
            title=_("Idle"), description=_("Counted from the moment you stop using the computer.")
        )
        self.idle_group.add(self._idle_row("screensaver", _("Screensaver after"), "", idle.get("screensaver", 150)))
        self.idle_group.add(
            self._idle_row(
                "lock", _("Lock the screen after"), _("Asks for the password to come back"), idle.get("lock", 300)
            )
        )
        self.idle_group.add(
            switch_row(
                _("Stay awake"),
                _("Pauses the screensaver and lock until you turn this off"),
                STAY_AWAKE_FLAG.exists(),
                self._set_stay_awake,
            )
        )
        self.add(self.idle_group)

    def _idle_row(self, key: str, title: str, subtitle: str, current) -> Adw.ComboRow:
        values = list(IDLE_TIMES)
        try:
            current = int(current)
        except (TypeError, ValueError):
            current = 0
        if current not in values:
            values.insert(-1, current)

        def on_select(i: int) -> None:
            bg(
                lambda: write_idle(key, values[i]),
                lambda ok: None if ok is True else self.win.toast(_("Could not write shell.json")),
            )

        return combo_row(title, subtitle, [idle_label(s) for s in values], values.index(current), on_select)

    def _set_stay_awake(self, on: bool) -> None:
        bg(lambda: command(["omarchy-toggle-idle", "stay-awake" if on else "allow-idle"]))
