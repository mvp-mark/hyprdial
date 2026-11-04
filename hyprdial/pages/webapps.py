"""Web apps group of the Apps page: the installed ones with a remove button, and a dialog to add one."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from .. import core, webapps
from ..i18n import _
from ..ui import bg, confirm

PROBLEMS = {
    "name": _("Type a name"),
    "slash": _('The name can\'t contain "/"'),
    "exists": _("There is already a web app with this name"),
    "url": _("Type a web address (https://…)"),
}


def app_icon(icon: str) -> Gtk.Image:
    image = Gtk.Image(pixel_size=32)
    if icon.startswith("/"):
        image.set_from_file(icon)
    else:
        image.set_from_icon_name(icon or "web-browser-symbolic")
    return image


class AddDialog(Adw.Dialog):
    def __init__(self, existing: list[webapps.WebApp], on_added):
        super().__init__(title=_("Add web app"), content_width=460)
        self.existing, self.on_added = existing, on_added
        self.name = Adw.EntryRow(title=_("Name"))
        self.url = Adw.EntryRow(title=_("Address"), input_purpose=Gtk.InputPurpose.URL)
        self.icon = Adw.EntryRow(title=_("Icon (optional)"))
        group = Adw.PreferencesGroup(
            description=_("Leave the icon empty to use the site's own icon, or type an image address or an icon name.")
        )
        for row in (self.name, self.url, self.icon):
            group.add(row)
            row.connect("entry-activated", lambda _r: self._add())
        self.error = Gtk.Label(css_classes=["error"], wrap=True, xalign=0, visible=False)
        self.button = Gtk.Button(label=_("Add"), css_classes=["suggested-action", "pill"], halign=Gtk.Align.CENTER)
        self.button.connect("clicked", lambda _b: self._add())
        self.spinner = Gtk.Spinner(spinning=True, visible=False)

        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=18,
            margin_top=12,
            margin_bottom=24,
            margin_start=24,
            margin_end=24,
        )
        for widget in (group, self.error, self.spinner, self.button):
            box.append(widget)
        view = Adw.ToolbarView(content=box)
        view.add_top_bar(Adw.HeaderBar())
        self.set_child(view)
        self.set_focus(self.name)

    def _add(self) -> None:
        name, url, icon = (r.get_text().strip() for r in (self.name, self.url, self.icon))
        problem = webapps.check(name, url, self.existing)
        if problem:
            self._show_error(PROBLEMS[problem])
            return
        self._busy(True)

        def done(res) -> None:
            self._busy(False)
            ok, message = (False, str(res)) if isinstance(res, Exception) else res
            if ok:
                self.close()
                self.on_added(name)
            elif "icon" in message.lower():
                self._show_error(_("Couldn't get the site's icon. Type an image address or an icon name."))
            else:
                self._show_error(message or _("Could not add the web app"))

        bg(lambda: webapps.install(name, url, icon), done)

    def _busy(self, on: bool) -> None:
        self.spinner.set_visible(on)
        self.button.set_sensitive(not on)
        self.error.set_visible(False)

    def _show_error(self, text: str) -> None:
        self.error.set_label(text)
        self.error.set_visible(True)


class WebAppsGroup(Adw.PreferencesGroup):
    def __init__(self, win):
        super().__init__(
            title=_("Web apps"), description=_("Sites that open in their own window, from the app launcher.")
        )
        self.win = win
        self.apps: list[webapps.WebApp] = []
        self.rows: list[Gtk.Widget] = []
        if not core.have("omarchy-webapp-install"):
            self.add(Adw.ActionRow(title=_("Omarchy's web app commands were not found")))
            return
        add = Gtk.Button(
            icon_name="list-add-symbolic", tooltip_text=_("Add web app"), css_classes=["flat"], valign=Gtk.Align.CENTER
        )
        add.connect("clicked", lambda _b: AddDialog(self.apps, self._added).present(self.win))
        self.set_header_suffix(add)
        self.refresh()

    def refresh(self) -> None:
        bg(webapps.web_apps, self._populate)

    def _populate(self, found) -> None:
        if isinstance(found, Exception):
            return
        for row in self.rows:
            self.remove(row)
        self.apps, self.rows = found, []
        for app in found:
            row = Adw.ActionRow(title=app.title, subtitle=app.url, use_markup=False, subtitle_lines=1)
            row.add_prefix(app_icon(app.icon))
            remove = Gtk.Button(
                icon_name="user-trash-symbolic", tooltip_text=_("Remove"), css_classes=["flat"], valign=Gtk.Align.CENTER
            )
            remove.connect("clicked", lambda _b, app=app: self._confirm_remove(app))
            row.add_suffix(remove)
            self.rows.append(row)
            self.add(row)
        if not found:
            empty = Adw.ActionRow(title=_("No web apps yet"), css_classes=["dim-label"])
            self.rows.append(empty)
            self.add(empty)

    def _added(self, name: str) -> None:
        self.win.toast(_("{name} added to the app launcher").format(name=name))
        self.refresh()

    def _confirm_remove(self, app: webapps.WebApp) -> None:
        confirm(
            self.win,
            heading=_("Remove {name}?").format(name=app.title),
            body=_("Removes it from the app launcher. The site itself and its data in the browser are kept."),
            action=_("Remove"),
            on_confirm=lambda: bg(lambda: webapps.remove(app.name), lambda res: self._removed(app, res)),
        )

    def _removed(self, app: webapps.WebApp, res) -> None:
        ok = not isinstance(res, Exception) and res[0]
        self.win.toast(
            _("{name} removed").format(name=app.title) if ok else _("Could not remove {name}").format(name=app.title)
        )
        self.refresh()
