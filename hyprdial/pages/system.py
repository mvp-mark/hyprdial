"""System page: date and time, language, notifications, printers and about (with Omarchy updates)."""

from __future__ import annotations

import shutil

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, Gtk  # noqa: E402

from .. import __version__, core, host, system
from ..i18n import _
from ..ui import Debouncer, bg, button_row, missing_row, switch_row

LANGUAGES = {
    "en": _("English"),
    "pt": _("Portuguese"),
    "es": _("Spanish"),
    "fr": _("French"),
    "de": _("German"),
    "it": _("Italian"),
    "nl": _("Dutch"),
    "pl": _("Polish"),
    "ru": _("Russian"),
    "uk": _("Ukrainian"),
    "ja": _("Japanese"),
    "zh": _("Chinese"),
    "ko": _("Korean"),
    "tr": _("Turkish"),
    "sv": _("Swedish"),
}
ABOUT_TITLES = {
    "omarchy": _("Omarchy version"),
    "hostname": _("Computer name"),
    "kernel": _("Kernel"),
    "cpu": _("Processor"),
    "cores": _("Threads"),
    "memory": _("Memory"),
}


def locale_label(loc: str, description: str = "") -> str:
    """Translated language name for the common ones, else glibc's English description."""
    name = LANGUAGES.get(loc.split("_")[0].split(".")[0]) or description
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
            title=_("Language"), description=_("Used by apps, this one included, after you log out and back in.")
        )
        self.add(self.lang_group)
        self.lang_rows: list[Gtk.Widget] = []
        self.use_after_install: str | None = None  # applied once the language is installed
        self.layout = ""
        if core.have("localectl"):
            self._load_language()
            # installing a language (in the terminal opened below) changes this folder
            self.archive_monitor = Gio.File.new_for_path(str(system.LOCALE_DIR)).monitor_directory(
                Gio.FileMonitorFlags.NONE, None
            )
            self.reload_language = Debouncer(1000, self._load_language)
            self.archive_monitor.connect("changed", lambda *_a: self.reload_language())

        self.notify_group = Adw.PreferencesGroup(title=_("Notifications"))
        if core.have("omarchy-shell"):  # the Omarchy shell shows the notifications
            self.add(self.notify_group)
            bg(system.dnd, self._populate_notifications)

        printers = Adw.PreferencesGroup(title=_("Printers"))
        if core.have("lpstat"):
            printers.add(
                button_row(
                    _("Manage printers"),
                    _("Add printers and see the print queue in the browser (CUPS)"),
                    _("Open"),
                    lambda: core.spawn(["xdg-open", system.PRINTERS_URL]),
                )
            )
        else:
            printers.add(missing_row("CUPS", _("Install the cups package to use printers")))
        self.add(printers)

        self.about_group = Adw.PreferencesGroup(title=_("About this computer"))
        self.add(self.about_group)
        bg(self._load_about, self._populate_about)

    # -- helpers
    def _apply_row(self, combo: Adw.ComboRow, options: list[str], current: str, apply) -> None:
        """Adds an Apply button to combo, enabled only when the choice differs from what is in use."""
        btn = Gtk.Button(label=_("Apply"), valign=Gtk.Align.CENTER, css_classes=["suggested-action"], sensitive=False)
        state = {"current": current}
        combo.connect(
            "notify::selected", lambda r, _p: btn.set_sensitive(options[r.get_selected()] != state["current"])
        )

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
                bg(
                    lambda: system.set_ntp(on),
                    lambda res: (
                        None
                        if not isinstance(res, Exception) and res[0]
                        else self.win.toast(_("Could not change automatic time"))
                    ),
                )

            self.time_group.add(switch_row(_("Set the time automatically"), subtitle, settings["ntp"], set_ntp))
        if host.is_omarchy():  # the clock is in the Omarchy shell bar
            self.time_group.add(
                Adw.ActionRow(title=_("Clock format"), subtitle=_("12 or 24 hours: Bar and fonts → Clock format"))
            )

    # -- language
    def _load_language(self) -> None:
        def load():
            current, available = system.locale_settings()
            installable = system.installable(available)
            self.layout = system.keyboard_layout()
            suggested = system.suggest_install(self.layout, installable)
            return current, available, [(name, system.describe(name)) for name in installable], suggested

        bg(load, self._populate_language)

    def _add_lang_row(self, row: Gtk.Widget) -> None:
        self.lang_group.add(row)
        self.lang_rows.append(row)

    def _populate_language(self, result) -> None:
        if isinstance(result, Exception):
            return
        for row in self.lang_rows:
            self.lang_group.remove(row)
        self.lang_rows = []
        current, available, installable, suggested = result
        pending = (
            system.installed_locale(self.use_after_install, available, self.layout) if self.use_after_install else None
        )
        if pending:
            # installed with "Install and use": apply it now that locale-gen is done
            self.use_after_install = None
            bg(lambda: system.set_locale(pending), lambda res: self._used_installed(pending, res))
        if available:
            row = searchable_combo(_("System language"), available, [locale_label(loc) for loc in available], current)
            self._apply_row(row, available, current, system.set_locale)
            self._add_lang_row(row)
        else:
            self._add_lang_row(Adw.ActionRow(title=_("No languages listed")))
        if not installable:
            return
        names = [loc for loc, _desc in installable]
        combo = searchable_combo(
            _("Install a language"), names, [locale_label(*item) for item in installable], suggested
        )
        combo.set_subtitle(_("Suggested from your keyboard layout") if suggested else _("Type to search"))
        btn = Gtk.Button(label=_("Install"), valign=Gtk.Align.CENTER)
        btn.connect("clicked", lambda _b: self._confirm_install(names[combo.get_selected()]))
        combo.add_suffix(btn)
        self._add_lang_row(combo)

    def _confirm_install(self, name: str) -> None:
        dialog = Adw.AlertDialog(
            heading=_("Install {language}?").format(language=name),
            body=_(
                "Opens a terminal that asks for your password, enables the language in /etc/locale.gen "
                "and runs locale-gen. With “Install and use” it also becomes the system language when it finishes "
                "(from your next login)."
            )
            if system.language_method() == "locale-gen"
            else _(
                "Opens a terminal that asks for your password and installs the language's package. With "
                "“Install and use” it also becomes the system language when it finishes (from your next login)."
            ),
        )
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("install", _("Install"))
        dialog.add_response("use", _("Install and use"))
        dialog.set_response_appearance("use", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("use")
        dialog.set_close_response("cancel")

        def respond(_d, response: str) -> None:
            if response in ("install", "use"):
                self.use_after_install = name if response == "use" else None
                core.spawn(system.install_command(name))

        dialog.connect("response", respond)
        dialog.present(self.win)

    def _used_installed(self, name: str, res) -> None:
        ok, error = (False, str(res)) if isinstance(res, Exception) else res
        if ok:
            self.win.toast(_("{language} is the system language from your next login").format(language=name))
            self._load_language()
        else:
            self.win.toast(_("Failed: {error}").format(error=error) if error else _("Not changed"))

    # -- notifications
    def _populate_notifications(self, on) -> None:
        if on is None or isinstance(on, Exception):
            self.notify_group.add(Adw.ActionRow(title=_("The Omarchy shell isn't answering")))
            return

        def set_dnd(value: bool) -> None:
            bg(
                lambda: system.set_dnd(value),
                lambda ok: None if ok is True else self.win.toast(_("Could not change Do not disturb")),
            )

        self.notify_group.add(
            switch_row(_("Do not disturb"), _("Hides notifications; critical ones still show"), on, set_dnd)
        )
        self.notify_group.add(
            button_row(
                _("Recent notifications"), _("Shows them again on screen"), _("Show"), lambda: bg(system.show_history)
            )
        )

    # -- about
    @staticmethod
    def _load_about():
        location = system.app_location()
        return system.about(), location, system.other_copies(location)

    def _populate_about(self, result) -> None:
        if isinstance(result, Exception):
            return
        info, location, others = result
        self._add_app_rows(location, others)
        for key, value in info:
            row = Adw.ActionRow(title=ABOUT_TITLES[key])
            row.add_suffix(Gtk.Label(label=value, selectable=True, css_classes=["dim-label"], xalign=1, wrap=True))
            self.about_group.add(row)
        if core.have(system.UPDATE_COMMAND[0]):
            row = button_row(
                _("Update Omarchy"), _("Checking for updates…"), _("Update"), lambda: core.spawn(system.UPDATE_COMMAND)
            )
            self.about_group.add(row)
            if core.have("omarchy-update-available"):
                bg(system.update_status, lambda res: self._show_update(row, res))
            else:
                row.set_subtitle(_("Opens a terminal with the update"))
        if system.can_snapshot():
            self.about_group.add(
                button_row(
                    _("Create a snapshot now"),
                    _("A restore point of the system; asks for your password in a terminal"),
                    _("Create"),
                    lambda: core.spawn(system.SNAPSHOT_COMMAND),
                )
            )
            self.about_group.add(
                Adw.ActionRow(
                    title=_("Going back to a snapshot"),
                    subtitle=_("Choose it in the boot menu when the computer starts"),
                )
            )

    # -- this app
    def _add_app_rows(self, location: str, others: list[str]) -> None:
        where = {
            "package": _("package {name}").format(name=system.PACKAGE),
            "local": _("installed with install.sh"),
            "source": _("running from the source folder"),
        }
        row = Adw.ActionRow(title="Hyprdial", subtitle=f"{__version__} · {where[location]}")
        self.about_group.add(row)
        bg(system.latest_release, lambda latest: self._show_latest(row, latest))
        if not others:
            return
        remove = {
            "package": system.package_removal(),
            "local": "rm -r ~/.local/share/hyprdial ~/.local/bin/hyprdial ~/.local/bin/omarchy-settings",
            "old": "rm -r ~/.local/share/omarchy-settings ~/.local/bin/omarchy-settings "
            "~/.local/share/applications/org.omarchy.Settings.desktop",
        }
        other = {
            "package": _("the package {name}").format(name=system.PACKAGE),
            "local": _("a copy from install.sh"),
            "old": _("a copy from install.sh with the app's old name, omarchy-settings"),
        }[others[0]]
        warning = Adw.ActionRow(
            title=_("Installed twice"),
            subtitle=_(
                "Also installed: {other}. The launcher opens only one of them ({path}); "
                "remove the one you don't use with {command}"
            ).format(
                other=other,
                path=shutil.which("hyprdial") or "hyprdial",
                command=remove[others[0]],
            ),
            subtitle_selectable=True,
        )
        warning.add_prefix(Gtk.Image(icon_name="dialog-warning-symbolic"))
        self.about_group.add(warning)

    def _show_latest(self, row: Adw.ActionRow, latest) -> None:
        if isinstance(latest, Exception) or not system.is_newer(latest, __version__):
            return
        row.set_subtitle(row.get_subtitle() + " · " + _("version {version} is available").format(version=latest))
        btn = Gtk.Button(label=_("See"), valign=Gtk.Align.CENTER)
        btn.connect("clicked", lambda _b: core.spawn(["xdg-open", system.RELEASES_URL]))
        row.add_suffix(btn)

    def _show_update(self, row: Adw.ActionRow, res) -> None:
        state, detail = (None, "") if isinstance(res, Exception) else res
        if state == "available":
            row.set_subtitle(_("Update available: {version}").format(version=detail))
            row.get_activatable_widget().add_css_class("suggested-action")
        elif state == "current":
            row.set_subtitle(_("Omarchy is up to date"))
        else:
            row.set_subtitle(_("Opens a terminal with the update"))
