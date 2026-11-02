"""Apps page: default apps (browser, terminal, editor, files, PDF, images) and web apps."""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from .. import apps, core
from ..i18n import _
from ..ui import bg
from .webapps import WebAppsGroup

KIND_TITLES = {"browser": _("Web browser"), "terminal": _("Terminal"), "editor": _("Text editor"),
               "files": _("File manager"), "pdf": _("PDF documents"), "images": _("Images")}
MIME_SUBTITLES = {"images": _("PNG, JPEG, WebP and GIF")}


def choice_row(kind: str, choices: list[tuple[str, str]], current: str, apply) -> Adw.ComboRow:
    """ComboRow over (name, label) choices that calls apply(kind, name) on change."""
    names = [name for name, _label in choices]
    row = Adw.ComboRow(title=KIND_TITLES[kind], subtitle=MIME_SUBTITLES.get(kind, ""))
    row.set_model(Gtk.StringList.new([label for _name, label in choices]))
    if current in names:
        row.set_selected(names.index(current))
    elif current:
        row.set_subtitle(_("Now: {name}").format(name=current))
    row.connect("notify::selected", lambda r, _p: apply(kind, names[r.get_selected()]))
    return row


class AppsPage(Adw.PreferencesPage):
    def __init__(self, win):
        super().__init__()
        self.win = win

        self.defaults = Adw.PreferencesGroup(title=_("Default apps"), description=_("Only installed apps are listed."))
        self.add(self.defaults)
        bg(self._read_defaults, self._populate_defaults)

        self.add(WebAppsGroup(win))

    # -- default apps
    @staticmethod
    def _read_defaults():
        by_command = apps.default_apps() if core.have("omarchy") else {}
        desktop = apps.desktop_apps()
        by_type = {kind: apps.mime_choices(kind, desktop) for kind in apps.MIME_KINDS} if core.have("xdg-mime") else {}
        return by_command, by_type

    def _populate_defaults(self, result) -> None:
        if isinstance(result, Exception):
            return
        by_command, by_type = result
        for kind in ("browser", "terminal", "editor"):
            if kind in by_command:
                self.defaults.add(choice_row(kind, *by_command[kind], self._set_command))
        for kind, (choices, current) in by_type.items():
            if choices:
                self.defaults.add(choice_row(kind, choices, current, self._set_mime))

    def _set_command(self, kind: str, name: str) -> None:
        bg(lambda: apps.set_default_app(kind, name), self._changed)

    def _set_mime(self, kind: str, desktop_id: str) -> None:
        bg(lambda: apps.set_mime_default(kind, desktop_id), self._changed)

    def _changed(self, res) -> None:
        ok = not isinstance(res, Exception) and res[0]
        self.win.toast(_("Default app changed") if ok else _("Could not change the default app"))
