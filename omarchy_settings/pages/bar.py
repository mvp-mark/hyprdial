"""Página da barra (Omarchy shell), inatividade e fontes do sistema.

A barra é do omarchy-shell (Quickshell). Posição, transparência e widgets são alterados pelos comandos
`omarchy-bar` e `omarchy-plugin-*`, que conversam com o shell em execução; só a inatividade é gravada
direto em ~/.config/omarchy/shell.json, do mesmo jeito que os comandos do Omarchy fazem.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

from .. import core, deps, waybar
from ..i18n import _, ngettext
from ..ui import bg, button_row, combo_row, switch_row

OMARCHY_PATH = os.environ.get("OMARCHY_PATH", "/usr/share/omarchy")
SHELL_CONFIG = core.CONF_DIR / "omarchy" / "shell.json"
SHELL_DEFAULTS = Path(OMARCHY_PATH) / "config" / "omarchy" / "shell.json"
BAR_OFF_FLAG = core.HOME / ".local/state/omarchy/toggles/bar-off"
STAY_AWAKE_FLAG = core.HOME / ".local/state/omarchy/indicators/stay-awake"

SECTIONS = ["left", "center", "right"]
POSITIONS = [("top", _("Top")), ("bottom", _("Bottom")), ("left", _("Left side")), ("right", _("Right side"))]
IDLE_TIMES = [60, 120, 150, 300, 600, 900, 1800, 3600, 0]


def idle_label(seconds: int) -> str:
    if seconds == 0:
        return _("Never")
    if seconds == 150:
        return _("2½ minutes")
    if seconds % 3600 == 0:
        return ngettext("{n} hour", "{n} hours", seconds // 3600).format(n=seconds // 3600)
    if seconds % 60 == 0:
        return ngettext("{n} minute", "{n} minutes", seconds // 60).format(n=seconds // 60)
    return ngettext("{n} second", "{n} seconds", seconds).format(n=seconds)

# Nomes traduzíveis para os widgets do Omarchy; widgets de terceiros usam o nome do catálogo.
WIDGET_NAMES = {
    "omarchy.active-window": (_("Active window"), _("Title of the focused window")),
    "omarchy.agents": (_("AI agents"), _("Claude Code, Codex and Fireworks usage and limits")),
    "omarchy.audio": (_("Audio"), _("Volume, sound output and per-app mixer")),
    "omarchy.bluetooth": ("Bluetooth", _("Devices and connection")),
    "omarchy.clock": (_("Clock"), _("Date and time, with a calendar on click")),
    "omarchy.dropbox": ("Dropbox", _("Sync status and recent files")),
    "omarchy.indicators": (_("Indicators"), _("States like screen recording and do not disturb")),
    "omarchy.keyboard-layout": (_("Keyboard layout"), _("Current layout; click to switch")),
    "omarchy.media": (_("Media"), _("Controls for the music or video playing")),
    "omarchy.menu": (_("Omarchy menu"), _("Opens the command menu")),
    "omarchy.microphone": (_("Microphone"), _("Microphone state and mute button")),
    "omarchy.monitor": (_("Display"), _("Brightness and display controls")),
    "omarchy.network": (_("Network"), _("Wi-Fi and connection state")),
    "omarchy.power": (_("Power"), _("Battery, power profile and system usage")),
    "omarchy.spacer": (_("Spacer"), _("Blank space")),
    "omarchy.system-update": (_("Updates"), _("Tells you when an Omarchy update is available")),
    "omarchy.tailscale": ("Tailscale", _("VPN status and connection switching")),
    "omarchy.tray": (_("System tray"), _("Icons of background apps")),
    "omarchy.weather": (_("Weather"), _("Temperature with details on click")),
    "omarchy.workspaces": (_("Workspaces"), _("Workspace numbers")),
}

def clock_formats() -> list[tuple[str, str]]:
    """(formato Qt, rótulo com exemplo usando a hora atual)."""
    now = datetime.now()
    day, short = now.strftime("%A"), now.strftime("%a")  # nomes no idioma do sistema
    hm, date = now.strftime("%H:%M"), now.strftime("%d/%m")
    h12 = f"{now.hour % 12 or 12}:{now:%M} {'PM' if now.hour >= 12 else 'AM'}"
    return [
        ("dddd HH:mm", _("Weekday and time — {example}").format(example=f"{day} {hm}")),
        ("HH:mm", _("Time only — {example}").format(example=hm)),
        ("ddd dd/MM HH:mm", _("Day, date and time — {example}").format(example=f"{short} {date} {hm}")),
        ("dd/MM/yyyy HH:mm", _("Full date and time — {example}").format(example=f"{date}/{now:%Y} {hm}")),
        ("h:mm AP", _("12-hour format — {example}").format(example=h12)),
    ]


# ------------------------------------------------------------------ configuração do shell
def read_shell() -> dict:
    """Mesma regra do omarchy-shell-config: o arquivo do usuário, ou os padrões se ele estiver vazio."""
    for path in (SHELL_CONFIG, SHELL_DEFAULTS):
        try:
            if path.stat().st_size:
                data = json.loads(path.read_text())
                if isinstance(data, dict):
                    return data
        except (OSError, ValueError):
            continue
    return {}


def bar_layout(config: dict) -> dict[str, list[dict]]:
    layout = (config.get("bar") or {}).get("layout") or {}
    result = {}
    for section in SECTIONS:
        items = layout.get(section) if isinstance(layout.get(section), list) else []
        result[section] = [i if isinstance(i, dict) else {"id": str(i)} for i in items]
    return result


def write_idle(key: str, seconds: int) -> bool:
    config = read_shell()
    config.setdefault("version", 1)
    idle = config.get("idle") if isinstance(config.get("idle"), dict) else {}
    idle[key] = seconds
    config["idle"] = idle
    try:
        SHELL_CONFIG.parent.mkdir(parents=True, exist_ok=True)
        tmp = SHELL_CONFIG.with_suffix(".tmp")
        tmp.write_text(json.dumps(config, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
        os.replace(tmp, SHELL_CONFIG)
    except OSError:
        return False
    core.run(["omarchy-shell", "shell", "reloadConfig"])
    return True


def widget_catalog() -> dict[str, tuple[str, str]]:
    """id -> (nome, descrição) de todos os widgets de barra conhecidos pelo shell."""
    try:
        catalog = json.loads(core.out(["omarchy-plugin-catalog"], timeout=15))
    except (ValueError, TypeError):
        catalog = []
    result = {}
    for item in catalog if isinstance(catalog, list) else []:
        if isinstance(item, dict) and item.get("barWidget"):
            result[item["id"]] = WIDGET_NAMES.get(item["id"], (item.get("name") or item["id"],
                                                                item.get("description") or ""))
    return result


def command(args: list[str]) -> tuple[bool, str]:
    r = core.run(args, timeout=20)
    if r is None:
        return False, _("command not found")
    return r.returncode == 0, (r.stderr or r.stdout).strip()


# ------------------------------------------------------------------ página
class BarPage(Adw.PreferencesPage):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.catalog: dict[str, tuple[str, str]] = {}
        self.widget_groups: list[Adw.PreferencesGroup] = []
        config = read_shell()
        bar = config.get("bar") or {}

        self.bar_group = Adw.PreferencesGroup(title=_("Bar"))
        self.bar_group.add(switch_row(_("Show the bar"), _("You can also toggle it with the Omarchy shortcut"),
                                      not BAR_OFF_FLAG.exists(), self._set_visible))
        positions = [p for p, _label in POSITIONS]
        position = bar.get("position", "top")
        self.bar_group.add(combo_row(_("Position"), "", [label for _pos, label in POSITIONS],
                                     positions.index(position) if position in positions else 0,
                                     lambda i: self._bar(["position", positions[i]], _("Bar position changed"),
                                                         rebuild=True)))
        self.bar_group.add(switch_row(_("Transparent background"), _("Shows the wallpaper behind the bar"),
                                      bool(bar.get("transparent")),
                                      lambda on: self._bar(["transparent", "true" if on else "false"])))
        self._add_clock_row(config)
        self.bar_group.add(button_row(_("Restart the shell"), _("Use it if the bar freezes or disappears"), _("Restart"),
                                      self._restart_shell))
        self.add(self.bar_group)

        self.add_group = Adw.PreferencesGroup(title=_("Add widget"))
        self.add_expander = Adw.ExpanderRow(title=_("Available widgets"), subtitle=_("Loading…"))
        self.add_group.add(self.add_expander)
        self.add(self.add_group)

        self._idle_group(config)

        self.waybar_group = Adw.PreferencesGroup(
            title=_("Waybar"),
            description=_("Optional alternative bar. Omarchy doesn't manage Waybar; its colors follow the "
                          "Omarchy theme."))
        self.waybar_rows: list[Gtk.Widget] = []
        self.add(self.waybar_group)
        self._fill_waybar()

        self.font_group = Adw.PreferencesGroup(title=_("System font"),
                                               description=_("Applied to the terminal, bar and other Omarchy apps."))
        self.add(self.font_group)
        if core.have("omarchy-font-set"):
            bg(lambda: ([f.strip() for f in core.out(["omarchy-font-list"]).splitlines() if f.strip()],
                        core.out(["omarchy-font-current"])), self._populate_fonts)
        else:
            self.font_group.add(Adw.ActionRow(title=_("omarchy-font-set not found"),
                                              subtitle=_("Update Omarchy to change fonts from here")))

        self.restore_group = restore = Adw.PreferencesGroup()
        restore.add(button_row(_("Restore default bar"), _("Returns position, transparency and widgets to Omarchy's default"),
                               _("Restore"), self._confirm_defaults, "destructive-action"))
        self.add(restore)

        if not core.have("omarchy-bar"):
            self.bar_group.set_description(_("omarchy-bar not found: update Omarchy to use this page."))
        bg(widget_catalog, self._on_catalog)

    # -- barra
    def _bar(self, args: list[str], ok_msg: str | None = None, rebuild: bool = False) -> None:
        def done(res) -> None:
            ok, msg = res if isinstance(res, tuple) else (False, str(res))
            if not ok:
                self.win.toast(_("Failed: {error}").format(error=msg or _("unknown error")))
            elif ok_msg:
                self.win.toast(ok_msg)
            if rebuild or not ok:
                GLib.timeout_add(300, self._refresh_widgets)

        bg(lambda: command(["omarchy-bar", *args]), done)

    def _set_visible(self, on: bool) -> None:
        # omarchy-toggle-bar controla a flag "bar-off": 'off' mostra a barra, 'on' esconde
        bg(lambda: command(["omarchy-toggle-bar", "off" if on else "on"]))

    def _add_clock_row(self, config: dict) -> None:
        clock = next((w for items in bar_layout(config).values() for w in items if w.get("id") == "omarchy.clock"),
                     None)
        if clock is None:
            return
        formats = clock_formats()
        current = clock.get("format", "dddd HH:mm")
        if current not in [f for f, _label in formats]:
            formats.append((current, _("Custom — {format}").format(format=current)))
        values = [f for f, _label in formats]
        self.bar_group.add(combo_row(_("Clock format"), _("Click the clock to see the alternate format"),
                                     [label for _fmt, label in formats], values.index(current),
                                     lambda i: self._bar(["set", "omarchy.clock", "format", values[i]],
                                                         _("Clock format changed"))))

    def _restart_shell(self) -> None:
        self.win.toast(_("Restarting the shell…"))

        def done(res) -> None:
            ok, msg = res if isinstance(res, tuple) else (False, str(res))
            self.win.toast(_("Shell restarted") if ok else _("Failed: {error}").format(error=msg))

        bg(lambda: command(["omarchy-restart-shell"]), done)

    def _confirm_defaults(self) -> None:
        dialog = Adw.AlertDialog(heading=_("Restore the default bar?"),
                                 body=_("The position, transparency and widget list return to Omarchy's default."))
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("restore", _("Restore"))
        dialog.set_response_appearance("restore", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_close_response("cancel")
        dialog.connect("response", lambda _d, r: r == "restore" and self._bar(["defaults"], _("Bar restored"),
                                                                               rebuild=True))
        dialog.present(self.win)

    # -- widgets
    def _on_catalog(self, catalog) -> None:
        self.catalog = catalog if isinstance(catalog, dict) else {}
        self._refresh_widgets()

    def _refresh_widgets(self) -> bool:
        config = read_shell()
        layout = bar_layout(config)
        vertical = (config.get("bar") or {}).get("position") in ("left", "right")
        titles = ([_("Widgets at the top"), _("Widgets in the middle"), _("Widgets at the bottom")] if vertical
                  else [_("Widgets on the left"), _("Widgets in the center"), _("Widgets on the right")])

        # PreferencesPage só adiciona no fim: tira tudo que vem depois de "Barra" e repõe na ordem
        tail = [self.add_group, self.idle_group, self.waybar_group, self.font_group, self.restore_group]
        for group in self.widget_groups + tail:
            if group.get_parent() is not None:
                self.remove(group)
        self.widget_groups = []
        for idx, section in enumerate(SECTIONS):
            group = Adw.PreferencesGroup(title=titles[idx])
            items = layout[section]
            if not items:
                group.add(Adw.ActionRow(title=_("Empty"), subtitle=_("Move widgets here with the arrows")))
            for pos, item in enumerate(items):
                group.add(self._widget_row(section, pos, len(items), item["id"], layout, vertical))
            self.widget_groups.append(group)
        for group in self.widget_groups + tail:
            self.add(group)
        self._fill_available(layout)
        return False

    def _widget_row(self, section: str, pos: int, count: int, wid: str, layout: dict, vertical: bool):
        name, desc = self.catalog.get(wid, WIDGET_NAMES.get(wid, (wid, "")))
        row = Adw.ActionRow(title=name, subtitle=desc)
        si = SECTIONS.index(section)
        before, after = ("go-up-symbolic", "go-down-symbolic") if not vertical else ("go-previous-symbolic",
                                                                                   "go-next-symbolic")
        to_prev, to_next = ("go-previous-symbolic", "go-next-symbolic") if not vertical else ("go-up-symbolic",
                                                                                              "go-down-symbolic")
        buttons = [
            (to_prev, _("Move to the previous section"), si > 0,
             lambda: self._move(wid, section, pos, SECTIONS[si - 1], len(layout[SECTIONS[si - 1]]))),
            (before, _("Move earlier"), pos > 0, lambda: self._move(wid, section, pos, section, pos - 1)),
            (after, _("Move later"), pos < count - 1, lambda: self._move(wid, section, pos, section, pos + 1)),
            (to_next, _("Move to the next section"), si < len(SECTIONS) - 1,
             lambda: self._move(wid, section, pos, SECTIONS[si + 1], 0)),
            ("list-remove-symbolic", _("Remove from the bar"), True, lambda: self._remove(wid, name)),
        ]
        box = Gtk.Box(spacing=2, valign=Gtk.Align.CENTER)
        for icon, tip, sensitive, action in buttons:
            btn = Gtk.Button(icon_name=icon, tooltip_text=tip, sensitive=sensitive)
            btn.add_css_class("flat")
            btn.connect("clicked", lambda _b, a=action: a())
            box.append(btn)
        row.add_suffix(box)
        return row

    def _move(self, wid: str, from_section: str, from_index: int, section: str, index: int) -> None:
        self._bar(["move", wid, "--from-section", from_section, "--from-index", str(from_index),
                   "--section", section, "--index", str(index)], rebuild=True)

    def _remove(self, wid: str, name: str) -> None:
        def done(res) -> None:
            ok, msg = res if isinstance(res, tuple) else (False, str(res))
            self.win.toast(_("{name} removed from the bar").format(name=name) if ok
                           else _("Failed: {error}").format(error=msg))
            GLib.timeout_add(300, self._refresh_widgets)

        bg(lambda: command(["omarchy-plugin-disable", wid]), done)

    def _fill_available(self, layout: dict) -> None:
        present = {i["id"] for items in layout.values() for i in items}
        available = sorted(((wid, n, d) for wid, (n, d) in self.catalog.items() if wid not in present),
                           key=lambda t: t[1].lower())
        expanded = self.add_expander.get_expanded()
        self.add_group.remove(self.add_expander)
        self.add_expander = Adw.ExpanderRow(title=_("Available widgets"), expanded=expanded,
                                            subtitle=ngettext("{n} not on the bar", "{n} not on the bar", len(available)).format(n=len(available))
                                            if available
                                            else _("Every widget is already on the bar"))
        for wid, name, desc in available:
            self.add_expander.add_row(button_row(name, desc, _("Add"), lambda w=wid, n=name: self._add(w, n)))
        self.add_group.add(self.add_expander)

    def _add(self, wid: str, name: str) -> None:
        def done(res) -> None:
            ok, msg = res if isinstance(res, tuple) else (False, str(res))
            self.win.toast(_("{name} added to the bar").format(name=name) if ok
                           else _("Failed: {error}").format(error=msg))
            GLib.timeout_add(300, self._refresh_widgets)

        bg(lambda: command(["omarchy-plugin-enable", wid]), done)

    # -- Waybar
    def _fill_waybar(self) -> None:
        for row in self.waybar_rows:
            self.waybar_group.remove(row)
        self.waybar_rows = []

        def add(row: Gtk.Widget) -> None:
            self.waybar_rows.append(row)
            self.waybar_group.add(row)

        if not waybar.installed():
            add(button_row(_("Waybar is not installed"), _("Install it to use it instead of the Omarchy bar"),
                           _("Install"), self._install_waybar, "suggested-action"))
            return
        add(switch_row(_("Use Waybar instead of the Omarchy bar"),
                       _("Starts Waybar now and at login, and hides the Omarchy bar"),
                       waybar.enabled(), self._set_waybar))
        positions = list(waybar.POSITIONS)
        current = waybar.read_position() if waybar.has_config() else "top"
        labels = dict(POSITIONS)
        add(combo_row(_("Waybar position"), "", [labels[p] for p in positions], positions.index(current),
                      lambda i: self._waybar_position(positions[i])))
        add(button_row(_("Restart Waybar"), _("Applies changes made to its files"), _("Restart"),
                       self._restart_waybar))
        add(button_row(_("Edit config.jsonc"), _("Modules and layout"), _("Open"),
                       lambda: self._edit_waybar(waybar.CONFIG)))
        add(button_row(_("Edit style.css"), _("Sizes, fonts and spacing; colors come from the theme"), _("Open"),
                       lambda: self._edit_waybar(waybar.STYLE)))
        add(button_row(_("Restore Waybar files"), _("Recreates config.jsonc and style.css; the current ones are "
                                                    "kept as .omarchy-settings.bak"),
                       _("Restore"), self._reset_waybar))

    def _install_waybar(self) -> None:
        self.win.toast(_("Installing Waybar…"))

        def done(res) -> None:
            ok = not isinstance(res, Exception) and res is not None and res.returncode == 0
            self.win.toast(_("Waybar installed") if ok else _("Waybar was not installed"))
            self._fill_waybar()

        bg(lambda: core.run(deps.install_command(["waybar"]), timeout=900), done)

    def _set_waybar(self, on: bool) -> None:
        def done(res) -> None:
            if isinstance(res, Exception):
                self.win.toast(_("Failed: {error}").format(error=res))
            else:
                self.win.toast(_("Using Waybar") if on else _("Using the Omarchy bar"))

        bg(lambda: waybar.set_enabled(on), done)

    def _waybar_position(self, position: str) -> None:
        def work() -> None:
            waybar.ensure_config()
            waybar.write_position(position)
            if waybar.running():
                waybar.stop()  # a posição só muda de verdade recriando a janela
                waybar.start()

        bg(work, lambda _r: self.win.toast(_("Waybar position changed")))

    def _restart_waybar(self) -> None:
        def work() -> bool:
            was_running = waybar.running()
            waybar.ensure_config()
            waybar.stop()
            return waybar.start() if was_running or waybar.enabled() else False

        bg(work, lambda started: self.win.toast(_("Waybar restarted") if started is True
                                                 else _("Waybar isn't in use; turn it on above")))

    def _edit_waybar(self, path) -> None:
        waybar.ensure_config()
        core.open_in_editor(path)

    def _reset_waybar(self) -> None:
        def work() -> None:
            waybar.reset_config()
            if waybar.running():
                waybar.reload()

        bg(work, lambda _r: (self.win.toast(_("Waybar files restored")), self._fill_waybar()))

    # -- inatividade
    def _idle_group(self, config: dict) -> None:
        idle = config.get("idle") if isinstance(config.get("idle"), dict) else {}
        self.idle_group = Adw.PreferencesGroup(title=_("Idle"),
                                               description=_("Counted from the moment you stop using the computer."))
        self.idle_group.add(self._idle_row("screensaver", _("Screensaver after"), "", idle.get("screensaver", 150)))
        self.idle_group.add(self._idle_row("lock", _("Lock the screen after"), _("Asks for the password to come back"),
                                           idle.get("lock", 300)))
        self.idle_group.add(switch_row(_("Stay awake"), _("Pauses the screensaver and lock until you turn this off"),
                                       STAY_AWAKE_FLAG.exists(), self._set_stay_awake))
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
            bg(lambda: write_idle(key, values[i]),
               lambda ok: None if ok is True else self.win.toast(_("Could not write shell.json")))

        return combo_row(title, subtitle, [idle_label(s) for s in values], values.index(current), on_select)

    def _set_stay_awake(self, on: bool) -> None:
        bg(lambda: command(["omarchy-toggle-idle", "stay-awake" if on else "allow-idle"]))

    # -- fontes
    def _populate_fonts(self, result) -> None:
        if isinstance(result, Exception) or not result[0]:
            self.font_group.add(Adw.ActionRow(title=_("No fonts listed"), subtitle=_("omarchy-font-list returned nothing")))
            return
        fonts, current = result
        selected = fonts.index(current) if current in fonts else 0
        row = combo_row(_("Font"), _("Current: {font}").format(font=current or _("unknown")), fonts, selected,
                        lambda i: self._set_font(fonts[i]))
        self.font_group.add(row)

    def _set_font(self, name: str) -> None:
        self.win.toast(_("Applying {name}…").format(name=name))

        def done(res) -> None:
            ok = not isinstance(res, Exception) and res is not None and res.returncode == 0
            self.win.toast((_("Font {name} applied") if ok else _("Failed to apply {name}")).format(name=name))

        bg(lambda: core.run(["omarchy-font-set", name], timeout=60), done)
