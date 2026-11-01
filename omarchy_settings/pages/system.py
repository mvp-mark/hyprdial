"""System page: date and time, language, default apps, notifications and about (with Omarchy updates)."""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from .. import core, system
from ..i18n import _
from ..ui import bg, button_row, switch_row

LANGUAGES = {"en": _("English"), "pt": _("Portuguese"), "es": _("Spanish"), "fr": _("French"), "de": _("German"),
             "it": _("Italian"), "nl": _("Dutch"), "pl": _("Polish"), "ru": _("Russian"), "uk": _("Ukrainian"),
             "ja": _("Japanese"), "zh": _("Chinese"), "ko": _("Korean"), "tr": _("Turkish"), "sv": _("Swedish")}
KIND_TITLES = {"browser": _("Web browser"), "terminal": _("Terminal"), "editor": _("Text editor")}
ABOUT_TITLES = {"omarchy": _("Omarchy version"), "hostname": _("Computer name"), "kernel": _("Kernel"),
                "cpu": _("Processor"), "cores": _("Threads"), "memory": _("Memory")}


def locale_label(loc: str) -> str:
    name = LANGUAGES.get(loc.split("_")[0].split(".")[0])
    return f"{name} — {loc}" if name else loc


def searchable_combo(title: str, options: list[str], labels: list[str], current: str) -> Adw.ComboRow:
    row = Adw.ComboRow(title=title, enable_search=True)
    row.set_expression(Gtk.PropertyExpression.new(Gtk.StringObject, None, "string"))
    row.set_search_match_mode(Gtk.StringFilterMatchMode.SUBSTRING)
    row.set_model(Gtk.StringList.new(labels))
    if current in options:
        row.set_selected(options.index(current))
    return row


class SystemPage(Adw.PreferencesPage):
    def __init__(self, win):
        super().__init__()
        self.win = win

        self.time_group = Adw.PreferencesGroup(title=_("Date and time"))
        self.add(self.time_group)
        if core.have("timedatectl"):
            bg(lambda: (system.time_settings(), system.timezones()), self._populate_time)

        self.lang_group = Adw.PreferencesGroup(
            title=_("Language"), description=_("Used by apps, this one included, after you log out and back in."))
        self.add(self.lang_group)
        if core.have("localectl"):
            bg(system.locale_settings, self._populate_language)

        self.apps_group = Adw.PreferencesGroup(title=_("Default apps"),
                                               description=_("Only installed apps are listed."))
        self.add(self.apps_group)
        if core.have("omarchy"):
            bg(system.default_apps, self._populate_apps)

        self.notify_group = Adw.PreferencesGroup(title=_("Notifications"))
        self.add(self.notify_group)
        if core.have("omarchy-shell"):
            bg(system.dnd, self._populate_notifications)

        self.about_group = Adw.PreferencesGroup(title=_("About this computer"))
        self.add(self.about_group)
        bg(system.about, self._populate_about)

    # -- helpers
    def _apply_row(self, combo: Adw.ComboRow, options: list[str], current: str, apply) -> None:
        """Adds an Apply button to combo, enabled only when the choice differs from what is in use."""
        btn = Gtk.Button(label=_("Apply"), valign=Gtk.Align.CENTER, css_classes=["suggested-action"], sensitive=False)
        state = {"current": current}
        combo.connect("notify::selected", lambda r, _p: btn.set_sensitive(options[r.get_selected()] != state["current"]))

        def clicked(_b) -> None:
            choice = options[combo.get_selected()]
            btn.set_sensitive(False)

            def done(res) -> None:
                ok, error = (False, str(res)) if isinstance(res, Exception) else res
                if ok:
                    state["current"] = choice
                    self.win.toast(_("Changed to {value}").format(value=choice))
                else:
                    btn.set_sensitive(True)
                    self.win.toast(_("Failed: {error}").format(error=error) if error else _("Not changed"))

            bg(lambda: apply(choice), done)

        btn.connect("clicked", clicked)
        combo.add_suffix(btn)

    # -- date and time
    def _populate_time(self, result) -> None:
        if isinstance(result, Exception):
            return
        settings, zones = result
        if zones:
            row = searchable_combo(_("Time zone"), zones, zones, settings["timezone"])
            row.set_subtitle(_("Type to search"))

            def apply(zone: str):
                ok, error = system.set_timezone(zone)
                if ok:
                    system.refresh_clock()
                return ok, error

            self._apply_row(row, zones, settings["timezone"], apply)
            self.time_group.add(row)
        if settings["can_ntp"]:
            subtitle = _("Synchronized") if settings["synced"] else _("Keeps the clock right through the internet")

            def set_ntp(on: bool) -> None:
                bg(lambda: system.set_ntp(on), lambda res: None if not isinstance(res, Exception) and res[0]
                   else self.win.toast(_("Could not change automatic time")))

            self.time_group.add(switch_row(_("Set the time automatically"), subtitle, settings["ntp"], set_ntp))
        self.time_group.add(Adw.ActionRow(title=_("Clock format"),
                                          subtitle=_("12 or 24 hours: Bar and fonts → Clock format")))

    # -- language
    def _populate_language(self, result) -> None:
        if isinstance(result, Exception):
            return
        current, available = result
        if not available:
            self.lang_group.add(Adw.ActionRow(title=_("No languages listed")))
            return
        row = searchable_combo(_("System language"), available, [locale_label(loc) for loc in available], current)

        self._apply_row(row, available, current, system.set_locale)
        self.lang_group.add(row)
        self.lang_group.add(Adw.ActionRow(title=_("Only languages generated on this system are listed"),
                                          subtitle=_("Others need to be enabled in /etc/locale.gen first")))

    # -- default apps
    def _populate_apps(self, apps) -> None:
        if isinstance(apps, Exception) or not apps:
            return
        for kind in ("browser", "terminal", "editor"):
            if kind not in apps:
                continue
            choices, current = apps[kind]
            names = [name for name, _label in choices]
            row = Adw.ComboRow(title=KIND_TITLES[kind])
            row.set_model(Gtk.StringList.new([label for _name, label in choices]))
            if current in names:
                row.set_selected(names.index(current))
            else:
                row.set_subtitle(_("Now: {name}").format(name=current) if current else "")

            def changed(r, _p, kind=kind, names=names) -> None:
                name = names[r.get_selected()]
                bg(lambda: system.set_default_app(kind, name), lambda res: self.win.toast(
                    _("Default app changed") if not isinstance(res, Exception) and res[0]
                    else _("Could not change the default app")))

            row.connect("notify::selected", changed)
            self.apps_group.add(row)

    # -- notifications
    def _populate_notifications(self, on) -> None:
        if on is None or isinstance(on, Exception):
            self.notify_group.add(Adw.ActionRow(title=_("The Omarchy shell isn't answering")))
            return

        def set_dnd(value: bool) -> None:
            bg(lambda: system.set_dnd(value), lambda ok: None if ok is True
               else self.win.toast(_("Could not change Do not disturb")))

        self.notify_group.add(switch_row(_("Do not disturb"), _("Hides notifications; critical ones still show"),
                                         on, set_dnd))
        self.notify_group.add(button_row(_("Recent notifications"), _("Shows them again on screen"), _("Show"),
                                         lambda: bg(system.show_history)))

    # -- about
    def _populate_about(self, info) -> None:
        if isinstance(info, Exception):
            return
        for key, value in info:
            row = Adw.ActionRow(title=ABOUT_TITLES[key])
            row.add_suffix(Gtk.Label(label=value, selectable=True, css_classes=["dim-label"], xalign=1, wrap=True))
            self.about_group.add(row)
        if core.have(system.UPDATE_COMMAND[0]):
            self.about_group.add(button_row(_("Update Omarchy"), _("Opens a terminal with the update"), _("Update"),
                                            lambda: core.spawn(system.UPDATE_COMMAND), "suggested-action"))
