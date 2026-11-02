"""Security page: fingerprint, FIDO2 key and SSH server, set up or removed in a terminal."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from .. import core, security
from ..i18n import _
from ..ui import bg, confirm

TITLES = {
    "fingerprint": (_("Fingerprint"), _("Unlock sudo and password prompts with your finger")),
    "fido2": (_("Security key (FIDO2)"), _("Unlock sudo and password prompts with a hardware key")),
    "sshd": (_("SSH server"), _("Lets you sign in to this computer from another one")),
}


class SecurityPage(Adw.PreferencesPage):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.group = Adw.PreferencesGroup(
            title=_("Sign-in and access"),
            description=_("Each one opens a terminal, which asks for your password and shows what it does."),
        )
        self.add(self.group)
        self.rows: list[Gtk.Widget] = []
        # set up in a terminal: read the state again whenever the page comes back
        self.connect("map", lambda _w: self.refresh())
        self.refresh()

    def refresh(self) -> None:
        bg(security.states, self._populate)

    def _populate(self, states) -> None:
        if isinstance(states, Exception):
            return
        for row in self.rows:
            self.group.remove(row)
        self.rows = []
        for state in states:
            title, subtitle = TITLES[state.key]
            if state.key == "sshd" and state.configured:
                subtitle = _("Running") if state.detail == "active" else _("Set up, but not running")
            elif state.configured:
                subtitle = _("Ready to use")
            row = Adw.ActionRow(title=title, subtitle=subtitle)
            if state.configured:
                remove = Gtk.Button(label=_("Remove"), valign=Gtk.Align.CENTER)
                remove.connect("clicked", lambda _b, s=state, t=title: self._confirm_remove(s.key, t))
                row.add_suffix(remove)
            setup = Gtk.Button(
                label=_("Set up again") if state.configured else _("Set up"),
                valign=Gtk.Align.CENTER,
                css_classes=[] if state.configured else ["suggested-action"],
            )
            setup.connect("clicked", lambda _b, k=state.key: core.spawn(security.command(k)))
            row.add_suffix(setup)
            self.rows.append(row)
            self.group.add(row)

    def _confirm_remove(self, key: str, title: str) -> None:
        confirm(
            self.win,
            heading=_("Remove {name}?").format(name=title),
            body=_("Opens a terminal that undoes the setup; it asks for your password."),
            action=_("Remove"),
            on_confirm=lambda: core.spawn(security.command(key, remove=True)),
        )
