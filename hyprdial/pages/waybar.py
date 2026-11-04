"""Bar page on plain Hyprland: Waybar started with Hyprland, its position and its files (Omarchy has the Bar and
fonts page instead)."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from .. import core, deps, waybar
from ..i18n import _
from ..ui import bg, button_row, combo_row, missing_row, switch_row

POSITIONS = {"top": _("Top"), "bottom": _("Bottom"), "left": _("Left"), "right": _("Right")}


class WaybarPage(Adw.PreferencesPage):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.store = win.store
        self.group = Adw.PreferencesGroup(
            title=_("Waybar"), description=_("The bar at the edge of the screen: workspaces, clock, network, sound…")
        )
        self.rows: list[Gtk.Widget] = []
        self.add(self.group)
        self._fill()

    def _add(self, row: Gtk.Widget) -> None:
        self.rows.append(row)
        self.group.add(row)

    def _fill(self) -> None:
        for row in self.rows:
            self.group.remove(row)
        self.rows = []
        if not waybar.installed():
            if deps.can_install():
                self._add(button_row(_("Waybar is not installed"), "", _("Install"), self._install, "suggested-action"))
            else:
                self._add(missing_row("Waybar", _("Install it with your package manager")))
            return
        ours = bool(self.store.extras.get("waybar"))
        if not ours and waybar.running():
            self._add(
                Adw.ActionRow(
                    title=_("Waybar is already started by your config"),
                    subtitle=_("Position and files below still work; leave the switch off to avoid starting it twice"),
                )
            )
        self._add(
            switch_row(_("Start Waybar with Hyprland"), _("Starts it now and at every login"), ours, self._set_enabled)
        )
        positions = list(POSITIONS)
        current = waybar.read_position() if waybar.has_config() else "top"
        self._add(
            combo_row(
                _("Position"),
                "",
                list(POSITIONS.values()),
                positions.index(current) if current in positions else 0,
                lambda i: self._position(positions[i]),
            )
        )
        self._add(button_row(_("Restart Waybar"), _("Applies changes made to its files"), _("Restart"), self._restart))
        self._add(
            button_row(_("Edit config.jsonc"), _("Modules and layout"), _("Open"), lambda: self._edit(waybar.CONFIG))
        )
        self._add(
            button_row(_("Edit style.css"), _("Colors, sizes and fonts"), _("Open"), lambda: self._edit(waybar.STYLE))
        )
        self._add(
            button_row(
                _("Restore Waybar files"),
                _("Recreates config.jsonc and style.css; the current ones are kept as .hyprdial.bak"),
                _("Restore"),
                self._reset,
            )
        )

    def _install(self) -> None:
        self.win.toast(_("Installing Waybar…"))

        def done(res) -> None:
            ok = not isinstance(res, Exception) and res is not None and res.returncode == 0
            self.win.toast(_("Waybar installed") if ok else _("Waybar was not installed"))
            self._fill()

        bg(lambda: deps.install(["waybar"]), done)

    def _set_enabled(self, on: bool) -> None:
        def work() -> None:
            if on:
                waybar.ensure_config()
                waybar.start()
            else:
                waybar.stop()
            self.store.set_extra("waybar", True if on else None, reload=False)

        bg(
            work,
            lambda r: self.win.toast(
                _("Failed: {error}").format(error=r)
                if isinstance(r, Exception)
                else (_("Waybar started") if on else _("Waybar stopped"))
            ),
        )

    def _position(self, position: str) -> None:
        def work() -> None:
            waybar.ensure_config()
            waybar.write_position(position)
            if waybar.running():
                waybar.stop()  # the position only really changes when the window is recreated
                waybar.start()

        bg(work, lambda r: self.win.toast(_("Bar position changed") if not isinstance(r, Exception) else str(r)))

    def _restart(self) -> None:
        def work() -> bool:
            waybar.ensure_config()
            waybar.stop()
            return waybar.start()

        bg(work, lambda ok: self.win.toast(_("Waybar restarted") if ok is True else _("Could not start Waybar")))

    def _edit(self, path) -> None:
        waybar.ensure_config()
        core.open_in_editor(path)

    def _reset(self) -> None:
        def work() -> None:
            waybar.reset_config()
            if waybar.running():
                waybar.reload()

        bg(work, lambda r: self.win.toast(_("Waybar files restored") if not isinstance(r, Exception) else str(r)))
