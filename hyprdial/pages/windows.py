"""Windows page: rules for what happens when an app's window opens, and the rules already in the config files."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from .. import core
from .. import windowrules as wr
from ..i18n import _
from ..ui import bg, confirm, set_changed

WORKSPACES = [""] + [str(n) for n in range(1, 11)]


class RuleDialog(Adw.Dialog):
    """Creates or edits a rule; Save is enabled only when the rule is valid."""

    def __init__(self, rule: dict | None, on_save):
        super().__init__(title=_("Edit rule") if rule else _("New rule"), content_width=560, content_height=680)
        self.on_save = on_save
        rule = dict(rule or {})
        self.windows: list[wr.Window] = []

        group = Adw.PreferencesGroup()
        self.problem = Gtk.Label(wrap=True, xalign=0, css_classes=["error"], margin_bottom=6)
        self.app_row = Adw.ComboRow(title=_("Open window"), subtitle=_("Loading…"), sensitive=False)
        group.add(self.app_row)
        self.class_row = Adw.EntryRow(title=_("App (window class)"), text=rule.get("class", ""))
        self.class_row.connect("changed", lambda _r: self._update())
        group.add(self.class_row)

        effects = Adw.PreferencesGroup(title=_("When it opens"))
        self.switches: dict[str, Adw.SwitchRow] = {}
        for key, title, subtitle in (
            ("float", _("Float"), _("Over the other windows instead of tiled")),
            ("center", _("Center"), _("For floating windows")),
            ("pin", _("Show on every workspace"), _("For floating windows")),
            ("fullscreen", _("Fullscreen"), ""),
            ("maximize", _("Maximized"), ""),
            ("idle", _("Keep the screen on in fullscreen"), _("For videos and games")),
        ):
            row = Adw.SwitchRow(title=title, subtitle=subtitle, active=bool(rule.get(key)))
            row.connect("notify::active", lambda *_a: self._update())
            self.switches[key] = row
            effects.add(row)

        size = rule.get("size") or [800, 600]
        self.size_row = Adw.ExpanderRow(
            title=_("Size"),
            subtitle=_("For floating windows"),
            show_enable_switch=True,
            enable_expansion=bool(rule.get("size")),
        )
        self.width = Adw.SpinRow.new_with_range(100, 7680, 10)
        self.width.set_title(_("Width"))
        self.width.set_value(size[0])
        self.height = Adw.SpinRow.new_with_range(100, 4320, 10)
        self.height.set_title(_("Height"))
        self.height.set_value(size[1])
        for row in (self.width, self.height):
            row.connect("notify::value", lambda *_a: self._update())
            self.size_row.add_row(row)
        self.size_row.connect("notify::enable-expansion", lambda *_a: self._update())
        effects.add(self.size_row)

        self.workspace_row = Adw.ComboRow(title=_("Workspace"))
        self.workspace_row.set_model(Gtk.StringList.new([_("Where it was opened")] + WORKSPACES[1:]))
        current = str(rule.get("workspace") or "")
        self.workspace_row.set_selected(WORKSPACES.index(current) if current in WORKSPACES else 0)
        self.workspace_row.connect("notify::selected", lambda *_a: self._update())
        effects.add(self.workspace_row)
        self.silent_row = Adw.SwitchRow(
            title=_("Open in the background"),
            subtitle=_("Without switching to that workspace"),
            active=bool(rule.get("silent")),
        )
        effects.add(self.silent_row)

        opacity = rule.get("opacity")
        self.opacity_row = Adw.SpinRow.new_with_range(10, 100, 5)
        self.opacity_row.set_title(_("Opacity (%)"))
        self.opacity_row.set_subtitle(_("100 keeps the usual opacity"))
        self.opacity_row.set_value(round(opacity * 100) if opacity is not None else 100)
        self.opacity_row.connect("notify::value", lambda *_a: self._update())
        effects.add(self.opacity_row)

        page = Adw.PreferencesPage()
        self.problem_group = Adw.PreferencesGroup()
        self.problem_group.add(self.problem)
        page.add(self.problem_group)
        page.add(group)
        page.add(effects)

        header = Adw.HeaderBar(show_end_title_buttons=False, show_start_title_buttons=False)
        cancel = Gtk.Button(label=_("Cancel"))
        cancel.connect("clicked", lambda _b: self.close())
        self.save_btn = Gtk.Button(label=_("Save"), css_classes=["suggested-action"])
        self.save_btn.connect("clicked", lambda _b: self._save())
        header.pack_start(cancel)
        header.pack_end(self.save_btn)
        view = Adw.ToolbarView(content=page)
        view.add_top_bar(header)
        self.set_child(view)
        self.set_default_widget(self.save_btn)
        self._update()
        bg(wr.open_windows, self._fill_windows)

    def _fill_windows(self, windows) -> None:
        self.windows = [] if isinstance(windows, Exception) else windows
        if not self.windows:
            self.app_row.set_subtitle(_("No open windows; type the class below"))
            return
        self.app_row.set_model(Gtk.StringList.new([_("Choose…")] + [f"{w.app} — {w.title}" for w in self.windows]))
        self.app_row.set_subtitle(_("Fills in the class below"))
        self.app_row.set_sensitive(True)
        self.app_row.connect("notify::selected", self._picked)

    def _picked(self, row, _pspec) -> None:
        index = row.get_selected()
        if index > 0:
            self.class_row.set_text(self.windows[index - 1].app)

    def rule(self) -> dict:
        rule: dict = {"class": self.class_row.get_text().strip()}
        for key, row in self.switches.items():
            if row.get_active():
                rule[key] = True
        if self.size_row.get_enable_expansion():
            rule["size"] = [int(self.width.get_value()), int(self.height.get_value())]
        workspace = WORKSPACES[self.workspace_row.get_selected()]
        if workspace:
            rule["workspace"] = workspace
            if self.silent_row.get_active():
                rule["silent"] = True
        if int(self.opacity_row.get_value()) < 100:
            rule["opacity"] = round(self.opacity_row.get_value() / 100, 2)
        return rule

    def _update(self) -> None:
        problem = wr.problem(self.rule())
        self.problem.set_label(problem or "")
        self.problem_group.set_visible(problem is not None)
        self.save_btn.set_sensitive(problem is None)
        self.silent_row.set_sensitive(self.workspace_row.get_selected() > 0)

    def _save(self) -> None:
        if wr.problem(self.rule()) is None:
            self.on_save(self.rule())
            self.close()


class WindowsPage(Adw.PreferencesPage):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.store = win.store

        self.mine = Adw.PreferencesGroup(
            title=_("Your rules"),
            description=_("Applied when the app's window opens; windows already open don't change."),
        )
        new = Gtk.Button(label=_("New rule"), css_classes=["suggested-action"], valign=Gtk.Align.CENTER)
        new.connect("clicked", lambda _b: RuleDialog(None, lambda r: self._save(None, r)).present(self.win))
        self.mine.set_header_suffix(new)
        self.mine_rows: list[Gtk.Widget] = []
        self.add(self.mine)

        self.theirs = Adw.PreferencesGroup(
            title=_("In your config files"), description=_("Read only; edit the files to change them.")
        )
        self.theirs_rows: list[Gtk.Widget] = []
        self.add(self.theirs)

        self._fill_mine()
        bg(wr.config_rules, self._fill_theirs)

    def _rules(self) -> list[dict]:
        return [r for r in self.store.extras.get("window_rules", []) if isinstance(r, dict)]

    def _fill_mine(self) -> None:
        for row in self.mine_rows:
            self.mine.remove(row)
        self.mine_rows = []
        rules = self._rules()
        if not rules:
            row = Adw.ActionRow(
                title=_("No rules yet"), subtitle=_("Use “New rule” to choose how an app's window opens")
            )
            self.mine.add(row)
            self.mine_rows.append(row)
        for index, rule in enumerate(rules):
            row = Adw.ActionRow(title=rule.get("class", ""), subtitle=wr.describe(rule), use_markup=False)
            edit = Gtk.Button(icon_name="document-edit-symbolic", tooltip_text=_("Edit"), valign=Gtk.Align.CENTER)
            edit.add_css_class("flat")
            edit.connect(
                "clicked", lambda _b, i=index, r=rule: RuleDialog(r, lambda new: self._save(i, new)).present(self.win)
            )
            delete = Gtk.Button(icon_name="user-trash-symbolic", tooltip_text=_("Delete"), valign=Gtk.Align.CENTER)
            delete.add_css_class("flat")
            delete.connect("clicked", lambda _b, i=index, r=rule: self._confirm_delete(i, r))
            row.add_suffix(edit)
            row.add_suffix(delete)
            set_changed(row, True)
            self.mine.add(row)
            self.mine_rows.append(row)

    def _fill_theirs(self, found) -> None:
        for row in self.theirs_rows:
            self.theirs.remove(row)
        self.theirs_rows = []
        found = [] if isinstance(found, Exception) else found
        if not found:
            row = Adw.ActionRow(title=_("No window rules in ~/.config/hypr"))
            self.theirs.add(row)
            self.theirs_rows.append(row)
        for rule in found:
            row = Adw.ActionRow(title=rule.file, subtitle=rule.text, use_markup=False, subtitle_selectable=True)
            self.theirs.add(row)
            self.theirs_rows.append(row)
        self.theirs.set_header_suffix(
            Gtk.Button(
                label=_("Open folder"),
                valign=Gtk.Align.CENTER,
                css_classes=["flat"],
            )
        )
        self.theirs.get_header_suffix().connect(
            "clicked", lambda _b: core.spawn(["xdg-open", str(core.HYPR_MAIN.parent)])
        )

    def _store(self, rules: list[dict], message: str) -> None:
        def done(res) -> None:
            self.win.toast(message if not isinstance(res, Exception) else _("Could not save the rule"))
            self._fill_mine()

        bg(lambda: self.store.set_extra("window_rules", rules or None), done)

    def _save(self, index: int | None, rule: dict) -> None:
        rules = self._rules()
        if index is None:
            rules.append(rule)
        else:
            rules[index] = rule
        self._store(rules, _("Rule saved; it applies to windows opened from now on"))

    def _confirm_delete(self, index: int, rule: dict) -> None:
        confirm(
            self.win,
            heading=_("Delete the rule for {app}?").format(app=rule.get("class", "")),
            body=_("Windows of this app open as usual again."),
            action=_("Delete"),
            on_confirm=lambda: self._store([r for i, r in enumerate(self._rules()) if i != index], _("Rule deleted")),
        )
