"""Dependencies dialog: shows what is installed and installs what is missing (password through polkit)."""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from .. import core, deps
from ..i18n import _, ngettext
from ..ui import bg

# pkexec: 126 = password not given or rejected, 127 = not authorized
PKEXEC_CANCELLED = (126, 127)


class DependenciesDialog(Adw.PreferencesDialog):
    def __init__(self):
        super().__init__(title=_("Dependencies"))
        self.set_content_width(560)
        self.set_content_height(640)  # Adw.Dialog shrinks by itself if the window is smaller
        self.page = Adw.PreferencesPage()
        self.add(self.page)
        self.groups: list[Adw.PreferencesGroup] = []
        self.checks: dict[str, Gtk.CheckButton] = {}
        self.busy = False

        self.footer = Adw.PreferencesGroup()
        self.install_btn = Gtk.Button(halign=Gtk.Align.CENTER, css_classes=["pill", "suggested-action"])
        self.install_btn.connect("clicked", lambda _b: self._install())
        self.footer.add(self.install_btn)
        self.page.add(self.footer)
        self.refresh()

    def refresh(self) -> None:
        self.install_btn.set_label(_("Checking…"))
        self.install_btn.set_sensitive(False)
        bg(lambda: deps.missing([d.package for d in deps.dependencies()]), self._populate)

    def _populate(self, absent) -> None:
        if isinstance(absent, Exception):
            absent = set()
        for group in self.groups:
            self.page.remove(group)
        self.page.remove(self.footer)
        self.groups, self.checks = [], {}

        for name in deps.GROUPS:
            group = Adw.PreferencesGroup(title=deps.group_title(name))
            for d in (d for d in deps.dependencies() if d.group == name):
                row = Adw.ActionRow(title=d.package, subtitle=d.purpose, use_markup=False)
                if d.package in absent:
                    check = Gtk.CheckButton(active=d.default, valign=Gtk.Align.CENTER)
                    check.connect("toggled", lambda _c: self._update_button())
                    row.add_prefix(check)
                    row.set_activatable_widget(check)
                    row.add_suffix(Gtk.Label(label=_("Not installed"), css_classes=["dim-label"]))
                    self.checks[d.package] = check
                else:
                    row.add_suffix(Gtk.Image(icon_name="object-select-symbolic", tooltip_text=_("Installed")))
                group.add(row)
            self.groups.append(group)
            self.page.add(group)
        self.page.add(self.footer)
        self._update_button()

    def _selected(self) -> list[str]:
        return [pkg for pkg, check in self.checks.items() if check.get_active()]

    def _update_button(self) -> None:
        if self.busy:
            return
        selected = self._selected()
        if not self.checks:
            self.install_btn.set_label(_("Everything is installed"))
        elif not selected:
            self.install_btn.set_label(_("Select packages to install"))
        else:
            self.install_btn.set_label(ngettext("Install {n} package", "Install {n} packages",
                                                len(selected)).format(n=len(selected)))
        self.install_btn.set_sensitive(bool(selected))

    def _install(self) -> None:
        packages = self._selected()
        if not packages:
            return
        self.busy = True
        self.install_btn.set_sensitive(False)
        self.install_btn.set_label(_("Installing…"))

        def done(result) -> None:
            self.busy = False
            if isinstance(result, Exception) or result is None:
                message = _("Could not run pkexec")
            elif result.returncode == 0:
                message = _("Installed: {packages}").format(packages=", ".join(packages))
            elif result.returncode in PKEXEC_CANCELLED:
                message = _("Installation cancelled")
            else:
                last = (result.stderr or result.stdout).strip().splitlines()
                message = _("Installation failed: {error}").format(error=last[-1] if last else result.returncode)
            self.add_toast(Adw.Toast(title=message, timeout=4))
            self.refresh()

        bg(lambda: core.run(deps.install_command(packages), timeout=900), done)
