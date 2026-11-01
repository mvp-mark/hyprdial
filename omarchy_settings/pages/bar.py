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

from .. import core
from ..ui import bg, button_row, combo_row, switch_row

OMARCHY_PATH = os.environ.get("OMARCHY_PATH", "/usr/share/omarchy")
SHELL_CONFIG = core.CONF_DIR / "omarchy" / "shell.json"
SHELL_DEFAULTS = Path(OMARCHY_PATH) / "config" / "omarchy" / "shell.json"
BAR_OFF_FLAG = core.HOME / ".local/state/omarchy/toggles/bar-off"
STAY_AWAKE_FLAG = core.HOME / ".local/state/omarchy/indicators/stay-awake"

SECTIONS = ["left", "center", "right"]
POSITIONS = [("top", "Topo"), ("bottom", "Rodapé"), ("left", "Lateral esquerda"), ("right", "Lateral direita")]
IDLE_TIMES = [(60, "1 minuto"), (120, "2 minutos"), (150, "2 minutos e meio"), (300, "5 minutos"),
              (600, "10 minutos"), (900, "15 minutos"), (1800, "30 minutos"), (3600, "1 hora"), (0, "Nunca")]

# Nomes em português para os widgets do Omarchy; widgets de terceiros usam o nome do catálogo.
WIDGET_NAMES = {
    "omarchy.active-window": ("Janela ativa", "Título da janela em foco"),
    "omarchy.agents": ("Agentes de IA", "Uso e limites do Claude Code, Codex e Fireworks"),
    "omarchy.audio": ("Áudio", "Volume, saída de som e mixer por aplicativo"),
    "omarchy.bluetooth": ("Bluetooth", "Dispositivos e conexão"),
    "omarchy.clock": ("Relógio", "Data e hora, com calendário ao clicar"),
    "omarchy.dropbox": ("Dropbox", "Status de sincronização e arquivos recentes"),
    "omarchy.indicators": ("Indicadores", "Estados como gravação de tela e não perturbe"),
    "omarchy.keyboard-layout": ("Layout do teclado", "Layout atual; clique para alternar"),
    "omarchy.media": ("Mídia", "Controle da música ou vídeo tocando"),
    "omarchy.menu": ("Menu do Omarchy", "Abre o menu de comandos"),
    "omarchy.microphone": ("Microfone", "Estado do microfone e botão de mudo"),
    "omarchy.monitor": ("Tela", "Brilho e controles da tela"),
    "omarchy.network": ("Rede", "Wi-Fi e estado da conexão"),
    "omarchy.power": ("Energia", "Bateria, perfil de energia e uso do sistema"),
    "omarchy.spacer": ("Espaçador", "Espaço em branco"),
    "omarchy.system-update": ("Atualizações", "Avisa quando há atualização do Omarchy"),
    "omarchy.tailscale": ("Tailscale", "Status e troca de conexão da VPN"),
    "omarchy.tray": ("Bandeja do sistema", "Ícones de aplicativos em segundo plano"),
    "omarchy.weather": ("Clima", "Temperatura com detalhes ao clicar"),
    "omarchy.workspaces": ("Workspaces", "Números dos workspaces"),
}

WEEKDAYS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]


def clock_formats() -> list[tuple[str, str]]:
    """(formato Qt, rótulo com exemplo usando a hora atual)."""
    now = datetime.now()
    day, short = WEEKDAYS[now.weekday()], WEEKDAYS[now.weekday()][:3]
    hm, date = now.strftime("%H:%M"), now.strftime("%d/%m")
    h12 = f"{now.hour % 12 or 12}:{now:%M} {'PM' if now.hour >= 12 else 'AM'}"
    return [
        ("dddd HH:mm", f"Dia da semana e hora — {day} {hm}"),
        ("HH:mm", f"Só a hora — {hm}"),
        ("ddd dd/MM HH:mm", f"Dia, data e hora — {short} {date} {hm}"),
        ("dd/MM/yyyy HH:mm", f"Data completa e hora — {date}/{now:%Y} {hm}"),
        ("h:mm AP", f"Formato de 12 horas — {h12}"),
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
        return False, "comando não encontrado"
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

        self.bar_group = Adw.PreferencesGroup(title="Barra")
        self.bar_group.add(switch_row("Mostrar a barra", "Também dá para alternar pelo atalho do Omarchy",
                                      not BAR_OFF_FLAG.exists(), self._set_visible))
        positions = [p for p, _ in POSITIONS]
        position = bar.get("position", "top")
        self.bar_group.add(combo_row("Posição", "", [label for _, label in POSITIONS],
                                     positions.index(position) if position in positions else 0,
                                     lambda i: self._bar(["position", positions[i]], "Posição da barra alterada",
                                                         rebuild=True)))
        self.bar_group.add(switch_row("Fundo transparente", "Deixa ver o papel de parede atrás da barra",
                                      bool(bar.get("transparent")),
                                      lambda on: self._bar(["transparent", "true" if on else "false"])))
        self._add_clock_row(config)
        self.bar_group.add(button_row("Reiniciar o shell", "Use se a barra travar ou sumir", "Reiniciar",
                                      self._restart_shell))
        self.add(self.bar_group)

        self.add_group = Adw.PreferencesGroup(title="Adicionar widget")
        self.add_expander = Adw.ExpanderRow(title="Widgets disponíveis", subtitle="Carregando…")
        self.add_group.add(self.add_expander)
        self.add(self.add_group)

        self._idle_group(config)

        self.font_group = Adw.PreferencesGroup(title="Fonte do sistema",
                                               description="Aplicada ao terminal, barra e demais apps do Omarchy.")
        self.add(self.font_group)
        if core.have("omarchy-font-set"):
            bg(lambda: ([f.strip() for f in core.out(["omarchy-font-list"]).splitlines() if f.strip()],
                        core.out(["omarchy-font-current"])), self._populate_fonts)
        else:
            self.font_group.add(Adw.ActionRow(title="omarchy-font-set não encontrado",
                                              subtitle="Atualize o Omarchy para trocar fontes por aqui"))

        self.restore_group = restore = Adw.PreferencesGroup()
        restore.add(button_row("Restaurar barra padrão", "Volta posição, transparência e widgets ao padrão do Omarchy",
                               "Restaurar", self._confirm_defaults, "destructive-action"))
        self.add(restore)

        if not core.have("omarchy-bar"):
            self.bar_group.set_description("omarchy-bar não encontrado: atualize o Omarchy para usar esta página.")
        bg(widget_catalog, self._on_catalog)

    # -- barra
    def _bar(self, args: list[str], ok_msg: str | None = None, rebuild: bool = False) -> None:
        def done(res) -> None:
            ok, msg = res if isinstance(res, tuple) else (False, str(res))
            if not ok:
                self.win.toast(f"Falhou: {msg or 'erro desconhecido'}")
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
        if current not in [f for f, _ in formats]:
            formats.append((current, f"Personalizado — {current}"))
        values = [f for f, _ in formats]
        self.bar_group.add(combo_row("Formato do relógio", "Clique no relógio para ver o formato alternativo",
                                     [label for _, label in formats], values.index(current),
                                     lambda i: self._bar(["set", "omarchy.clock", "format", values[i]],
                                                         "Formato do relógio alterado")))

    def _restart_shell(self) -> None:
        self.win.toast("Reiniciando o shell…")

        def done(res) -> None:
            ok, msg = res if isinstance(res, tuple) else (False, str(res))
            self.win.toast("Shell reiniciado" if ok else f"Falhou: {msg}")

        bg(lambda: command(["omarchy-restart-shell"]), done)

    def _confirm_defaults(self) -> None:
        dialog = Adw.AlertDialog(heading="Restaurar a barra padrão?",
                                 body="A posição, a transparência e a lista de widgets voltam ao padrão do Omarchy.")
        dialog.add_response("cancel", "Cancelar")
        dialog.add_response("restore", "Restaurar")
        dialog.set_response_appearance("restore", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_close_response("cancel")
        dialog.connect("response", lambda _d, r: r == "restore" and self._bar(["defaults"], "Barra restaurada",
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
        titles = (["No topo", "No meio", "Na base"] if vertical else ["À esquerda", "No centro", "À direita"])

        # PreferencesPage só adiciona no fim: tira tudo que vem depois de "Barra" e repõe na ordem
        tail = [self.add_group, self.idle_group, self.font_group, self.restore_group]
        for group in self.widget_groups + tail:
            if group.get_parent() is not None:
                self.remove(group)
        self.widget_groups = []
        for idx, section in enumerate(SECTIONS):
            group = Adw.PreferencesGroup(title=f"Widgets {titles[idx].lower()}")
            items = layout[section]
            if not items:
                group.add(Adw.ActionRow(title="Vazio", subtitle="Mova widgets para cá com as setas"))
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
            (to_prev, "Mover para a seção anterior", si > 0,
             lambda: self._move(wid, section, pos, SECTIONS[si - 1], len(layout[SECTIONS[si - 1]]))),
            (before, "Mover antes", pos > 0, lambda: self._move(wid, section, pos, section, pos - 1)),
            (after, "Mover depois", pos < count - 1, lambda: self._move(wid, section, pos, section, pos + 1)),
            (to_next, "Mover para a próxima seção", si < len(SECTIONS) - 1,
             lambda: self._move(wid, section, pos, SECTIONS[si + 1], 0)),
            ("list-remove-symbolic", "Remover da barra", True, lambda: self._remove(wid, name)),
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
            self.win.toast(f"{name} removido da barra" if ok else f"Falhou: {msg}")
            GLib.timeout_add(300, self._refresh_widgets)

        bg(lambda: command(["omarchy-plugin-disable", wid]), done)

    def _fill_available(self, layout: dict) -> None:
        present = {i["id"] for items in layout.values() for i in items}
        available = sorted(((wid, n, d) for wid, (n, d) in self.catalog.items() if wid not in present),
                           key=lambda t: t[1].lower())
        expanded = self.add_expander.get_expanded()
        self.add_group.remove(self.add_expander)
        self.add_expander = Adw.ExpanderRow(title="Widgets disponíveis", expanded=expanded,
                                            subtitle=f"{len(available)} fora da barra" if available
                                            else "Todos os widgets já estão na barra")
        for wid, name, desc in available:
            self.add_expander.add_row(button_row(name, desc, "Adicionar", lambda w=wid, n=name: self._add(w, n)))
        self.add_group.add(self.add_expander)

    def _add(self, wid: str, name: str) -> None:
        def done(res) -> None:
            ok, msg = res if isinstance(res, tuple) else (False, str(res))
            self.win.toast(f"{name} adicionado à barra" if ok else f"Falhou: {msg}")
            GLib.timeout_add(300, self._refresh_widgets)

        bg(lambda: command(["omarchy-plugin-enable", wid]), done)

    # -- inatividade
    def _idle_group(self, config: dict) -> None:
        idle = config.get("idle") if isinstance(config.get("idle"), dict) else {}
        self.idle_group = Adw.PreferencesGroup(title="Inatividade",
                                               description="Contado a partir do momento em que você para de usar o "
                                                           "computador.")
        self.idle_group.add(self._idle_row("screensaver", "Proteção de tela após", "", idle.get("screensaver", 150)))
        self.idle_group.add(self._idle_row("lock", "Bloquear a tela após", "Pede a senha para voltar",
                                           idle.get("lock", 300)))
        self.idle_group.add(switch_row("Manter acordado", "Pausa proteção de tela e bloqueio até desligar isto",
                                       STAY_AWAKE_FLAG.exists(), self._set_stay_awake))
        self.add(self.idle_group)

    def _idle_row(self, key: str, title: str, subtitle: str, current) -> Adw.ComboRow:
        times = list(IDLE_TIMES)
        try:
            current = int(current)
        except (TypeError, ValueError):
            current = 0
        if current not in [s for s, _ in times]:
            times.insert(-1, (current, f"{current} segundos"))
        values = [s for s, _ in times]

        def on_select(i: int) -> None:
            bg(lambda: write_idle(key, values[i]),
               lambda ok: None if ok is True else self.win.toast("Não foi possível gravar shell.json"))

        return combo_row(title, subtitle, [label for _, label in times], values.index(current), on_select)

    def _set_stay_awake(self, on: bool) -> None:
        bg(lambda: command(["omarchy-toggle-idle", "stay-awake" if on else "allow-idle"]))

    # -- fontes
    def _populate_fonts(self, result) -> None:
        if isinstance(result, Exception) or not result[0]:
            self.font_group.add(Adw.ActionRow(title="Nenhuma fonte listada", subtitle="omarchy-font-list sem saída"))
            return
        fonts, current = result
        selected = fonts.index(current) if current in fonts else 0
        row = combo_row("Fonte", f"Atual: {current or 'desconhecida'}", fonts, selected,
                        lambda i: self._set_font(fonts[i]))
        self.font_group.add(row)

    def _set_font(self, name: str) -> None:
        self.win.toast(f"Aplicando {name}…")

        def done(res) -> None:
            ok = not isinstance(res, Exception) and res is not None and res.returncode == 0
            self.win.toast(f"Fonte {name} aplicada" if ok else f"Falha ao aplicar {name}")

        bg(lambda: core.run(["omarchy-font-set", name], timeout=60), done)
