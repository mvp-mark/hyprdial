"""Startup apps group of the Apps page: XDG autostart switches, own commands and the user's autostart.lua."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from .. import autostart, core
from ..i18n import _, ngettext
from ..ui import bg, button_row, set_changed

EXTRAS_KEY = "autostart"


class StartupGroup(Adw.PreferencesGroup):
    def __init__(self, win):
        super().__init__(
            title=_("Startup apps"),
            description=_(
                "Started when you log in. Some apps are also started by the system's own config (the bar, "
                "input methods…), so one that is off here may still run."
            ),
        )
        self.win = win
        self.store = win.store
        self.rows: list[Gtk.Widget] = []

        self.commands = Adw.ExpanderRow(title=_("Your commands"), subtitle=_("Run at login through Hyprland"))
        set_changed(self.commands, False)
        self.add_command = Adw.EntryRow(
            title=_("Add a command (e.g. discord --start-minimized)"), show_apply_button=True
        )
        self.add_command.connect("apply", lambda r: self._add(r.get_text()))
        self.commands.add_row(self.add_command)
        self.command_rows: list[Gtk.Widget] = []

        self.lua = Adw.ExpanderRow(
            title=_("In {file}").format(file=autostart.startup_file().name),
            subtitle=core.home_path(autostart.startup_file()),
        )
        self.lua.add_row(
            button_row(
                _("Edit the file"),
                _("Changes there are yours; this app only reads them"),
                _("Open"),
                lambda: core.open_in_editor(autostart.startup_file()),
            )
        )
        self.lua_rows: list[Gtk.Widget] = []

        self.add(self.commands)
        self.add(self.lua)
        self._fill_commands()
        self.refresh()

    def refresh(self) -> None:
        bg(lambda: (autostart.entries(), autostart.lua_commands()), self._populate)

    def _populate(self, result) -> None:
        if isinstance(result, Exception):
            return
        entries, lua = result
        for row in self.rows:
            self.remove(row)
        self.rows = []
        for entry in entries:
            row = Adw.SwitchRow(title=entry.name, subtitle=entry.comment, active=entry.enabled, use_markup=False)
            row.connect("notify::active", lambda r, _p, entry=entry: self._toggle(entry, r.get_active()))
            self.rows.append(row)
            self.add(row)
        self._reorder()

        for row in self.lua_rows:
            self.lua.remove(row)
        self.lua_rows = [Adw.ActionRow(title=cmd, use_markup=False, css_classes=["monospace"]) for cmd in lua]
        if not lua:
            self.lua_rows = [Adw.ActionRow(title=_("No commands in the file"), css_classes=["dim-label"])]
        for row in self.lua_rows:
            self.lua.add_row(row)
        self.lua.set_subtitle(ngettext("{n} command", "{n} commands", len(lua)).format(n=len(lua)))

    def _reorder(self) -> None:
        """Keeps the two expanders after the switches."""
        for row in (self.commands, self.lua):
            self.remove(row)
            self.add(row)

    def _toggle(self, entry: autostart.Entry, on: bool) -> None:
        def done(res) -> None:
            if isinstance(res, Exception):
                self.win.toast(_("Could not change {name}").format(name=entry.name))
                self.refresh()
            else:
                entry.enabled = on

        bg(lambda: autostart.set_enabled(entry, on), done)

    # -- own commands
    def _current(self) -> list[str]:
        return list(self.store.extras.get(EXTRAS_KEY, []))

    def _fill_commands(self) -> None:
        for row in self.command_rows:
            self.commands.remove(row)
        self.command_rows = []
        for cmd in self._current():
            row = Adw.ActionRow(title=cmd, use_markup=False, css_classes=["monospace"])
            remove = Gtk.Button(
                icon_name="user-trash-symbolic", tooltip_text=_("Remove"), css_classes=["flat"], valign=Gtk.Align.CENTER
            )
            remove.connect("clicked", lambda _b, cmd=cmd: self._save([c for c in self._current() if c != cmd]))
            row.add_suffix(remove)
            self.command_rows.append(row)
            self.commands.add_row(row)
        n = len(self.command_rows)
        self.commands.set_subtitle(
            ngettext("{n} command", "{n} commands", n).format(n=n) if n else _("Run at login through Hyprland")
        )
        set_changed(self.commands, bool(n))

    def _add(self, text: str) -> None:
        cmd = autostart.valid_command(text)
        if cmd is None:
            self.win.toast(_("Type a command"))
            return
        if cmd in self._current():
            self.win.toast(_("This command is already there"))
            return
        self.add_command.set_text("")
        self._save(self._current() + [cmd])
        self.win.toast(_("It will start the next time you log in"))

    def _save(self, commands: list[str]) -> None:
        self.store.extras[EXTRAS_KEY] = commands  # shown right away; set_extra below writes it
        self._fill_commands()
        bg(lambda: self.store.set_extra(EXTRAS_KEY, commands or None, reload=False))
