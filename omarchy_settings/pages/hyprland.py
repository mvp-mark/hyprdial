"""Página de ajustes do Hyprland: estilo, janelas, efeitos, teclado, mouse, touchpad e comportamento.

Cada linha mostra o valor em uso (estado salvo > Hyprland em execução > padrão) e, quando este app
sobrescreve a opção, um botão ↶ que devolve só aquela opção ao padrão do Omarchy.
"""
from __future__ import annotations

from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

from .. import core
from ..ui import bg, button_row, to_bool, to_float

# Estilos rápidos: chaves ausentes num estilo voltam ao padrão do Omarchy.
PRESET_KEYS = (
    "general:gaps_in", "general:gaps_out", "general:border_size", "decoration:rounding",
    "decoration:blur:enabled", "decoration:blur:size", "decoration:blur:passes",
    "decoration:shadow:enabled", "decoration:shadow:range", "decoration:inactive_opacity",
)
PRESETS = [
    ("Compacto", "Sem espaços nem enfeites: máximo de área útil", {
        "general:gaps_in": 0, "general:gaps_out": 0, "general:border_size": 1, "decoration:rounding": 0,
        "decoration:blur:enabled": False, "decoration:shadow:enabled": False,
    }),
    ("Omarchy", "O visual padrão do Omarchy", {}),
    ("Confortável", "Mais respiro entre as janelas e cantos suaves", {
        "general:gaps_in": 8, "general:gaps_out": 16, "general:border_size": 2, "decoration:rounding": 10,
        "decoration:shadow:enabled": True, "decoration:shadow:range": 12,
    }),
    ("Elegante", "Cantos arredondados, sombra, desfoque e janelas inativas translúcidas", {
        "general:gaps_in": 10, "general:gaps_out": 20, "general:border_size": 2, "decoration:rounding": 14,
        "decoration:blur:enabled": True, "decoration:blur:size": 6, "decoration:blur:passes": 2,
        "decoration:shadow:enabled": True, "decoration:shadow:range": 20, "decoration:inactive_opacity": 0.92,
    }),
]

LAYOUTS = [
    ("dwindle", "Dividir (padrão)", "Cada nova janela divide o espaço da janela em foco"),
    ("master", "Principal e pilha", "Uma janela grande à esquerda e as outras empilhadas ao lado"),
    ("scrolling", "Rolagem lateral", "Colunas lado a lado que rolam na horizontal, estilo niri"),
]

# (rótulo, layout, variante)
KEYBOARDS = [
    ("Português (Brasil, ABNT2)", "br", ""),
    ("Inglês (EUA)", "us", ""),
    ("Inglês (EUA, internacional com acentos)", "us", "intl"),
    ("Português (Portugal)", "pt", ""),
    ("Espanhol", "es", ""),
]

ACCEL = [("", "Padrão do dispositivo"), ("adaptive", "Adaptativa"), ("flat", "Desligada (bom para jogos)")]


def keyboard_index(layout: str, variant: str) -> int:
    """Posição na lista de layouts comuns; o último item é 'Personalizado'."""
    return next((i for i, (_, lay, var) in enumerate(KEYBOARDS) if (lay, var) == (layout, variant)), len(KEYBOARDS))


FOLLOW = [(1, "Ao passar o mouse"), (0, "Só ao clicar"), (2, "Ao clicar, mas o teclado segue o mouse")]


class HyprlandPage(Adw.PreferencesPage):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.store = win.store
        self.controls: dict[str, tuple[Callable, object, Gtk.Button]] = {}
        self.entries: dict[str, Adw.EntryRow] = {}
        self._updating = False

        self._style_group()
        self._windows_group()
        self._effects_group()
        self._keyboard_group()
        self._mouse_group()
        self._touchpad_group()
        self._behavior_group()

        reset = Adw.PreferencesGroup()
        reset.add(button_row("Restaurar padrões", "Volta todas as opções desta página ao padrão do Omarchy",
                             "Restaurar", self._reset_all, "destructive-action"))
        self.add(reset)

    # ------------------------------------------------------------------ grupos
    def _style_group(self) -> None:
        group = Adw.PreferencesGroup(
            title="Estilo rápido",
            description="Aplica vários ajustes de uma vez; depois dá para refinar cada um abaixo.",
        )
        for name, desc, values in PRESETS:
            group.add(button_row(name, desc, "Aplicar", lambda v=values, n=name: self._apply_preset(n, v)))
        self.add(group)

    def _windows_group(self) -> None:
        group = Adw.PreferencesGroup(title="Janelas")
        group.add(self._choice("general:layout", "Organização das janelas", LAYOUTS[0][0],
                               [(k, label) for k, label, _ in LAYOUTS], subtitle_for=self._layout_subtitle))
        group.add(self._spin("general:gaps_in", "Espaço entre janelas", "Em pixels", 0, 40, 1, 5))
        group.add(self._spin("general:gaps_out", "Margem até a borda da tela", "Em pixels", 0, 80, 1, 10))
        group.add(self._spin("general:border_size", "Espessura da borda", "A cor vem do tema; 0 esconde a borda",
                             0, 10, 1, 2))
        group.add(self._spin("decoration:rounding", "Cantos arredondados", "Raio em pixels; 0 deixa os cantos retos",
                             0, 30, 1, 0))
        group.add(self._switch("general:resize_on_border", "Redimensionar pela borda",
                               "Arraste a borda da janela com o mouse para mudar o tamanho", False))
        self.add(group)

    def _effects_group(self) -> None:
        group = Adw.PreferencesGroup(title="Transparência e efeitos",
                                     description="Efeitos usam mais GPU; em notebooks podem gastar bateria.")
        group.add(self._percent("decoration:active_opacity", "Opacidade da janela ativa", "100% é totalmente opaca",
                                30, 100, 1.0))
        group.add(self._percent("decoration:inactive_opacity", "Opacidade das outras janelas",
                                "Abaixo de 100% deixa ver o que está atrás", 30, 100, 1.0))
        group.add(self._switch("decoration:dim_inactive", "Escurecer janelas sem foco",
                               "Ajuda a ver qual janela está ativa", False))
        group.add(self._percent("decoration:dim_strength", "Intensidade do escurecimento", "", 0, 100, 0.5))

        blur = Adw.ExpanderRow(title="Desfoque (blur)", subtitle="Embaça o que aparece atrás de janelas translúcidas")
        blur.add_row(self._switch("decoration:blur:enabled", "Ativar desfoque", "", False))
        blur.add_row(self._spin("decoration:blur:size", "Intensidade", "Raio do desfoque", 1, 20, 1, 8))
        blur.add_row(self._spin("decoration:blur:passes", "Qualidade", "Mais passadas = mais suave e mais pesado",
                                1, 4, 1, 1))
        group.add(blur)

        shadow = Adw.ExpanderRow(title="Sombra", subtitle="Sombra suave em volta das janelas")
        shadow.add_row(self._switch("decoration:shadow:enabled", "Ativar sombra", "", False))
        shadow.add_row(self._spin("decoration:shadow:range", "Tamanho", "Em pixels", 1, 50, 1, 4))
        group.add(shadow)

        group.add(self._switch("animations:enabled", "Animações", "Transições ao abrir, fechar e trocar de workspace",
                               True))
        self.add(group)

    def _keyboard_group(self) -> None:
        group = Adw.PreferencesGroup(title="Teclado")
        group.add(self._keyboard_row())
        group.add(self._switch("input:numlock_by_default", "Num Lock ligado ao iniciar", "", False))
        group.add(self._spin("input:repeat_delay", "Espera antes de repetir",
                             "Milissegundos segurando a tecla até ela repetir", 100, 1000, 50, 600))
        group.add(self._spin("input:repeat_rate", "Velocidade da repetição", "Caracteres por segundo", 1, 100, 1, 25))

        advanced = Adw.ExpanderRow(title="Avançado", subtitle="Layouts múltiplos, variantes e opções do XKB")
        advanced.add_row(self._entry("input:kb_layout", "Layouts (ex.: br,us)", "us"))
        advanced.add_row(self._entry("input:kb_variant", "Variantes (ex.: ,intl)", ""))
        advanced.add_row(self._entry("input:kb_options", "Opções (ex.: compose:caps,grp:alts_toggle)", ""))
        group.add(advanced)
        self.add(group)

    def _mouse_group(self) -> None:
        group = Adw.PreferencesGroup(title="Mouse")
        group.add(self._spin("input:sensitivity", "Velocidade do cursor", "De -1 (mais lento) a 1 (mais rápido)",
                             -1, 1, 0.05, 0, digits=2))
        group.add(self._choice("input:accel_profile", "Aceleração", "", ACCEL))
        group.add(self._switch("input:natural_scroll", "Rolagem natural", "O conteúdo acompanha o movimento da roda",
                               False))
        group.add(self._spin("input:scroll_factor", "Velocidade da rolagem", "1 é o normal", 0.1, 5, 0.1, 1.0,
                             digits=1))
        group.add(self._switch("input:left_handed", "Modo canhoto", "Troca os botões esquerdo e direito", False))
        group.add(self._choice("input:follow_mouse", "Foco das janelas", 1, FOLLOW))
        self.add(group)

    def _touchpad_group(self) -> None:
        group = Adw.PreferencesGroup(title="Touchpad")
        group.add(self._switch("input:touchpad:tap-to-click", "Tocar para clicar", "", True))
        group.add(self._switch("input:touchpad:natural_scroll", "Rolagem natural", "Como no celular", False))
        group.add(self._switch("input:touchpad:clickfinger_behavior", "Clique com dois dedos = botão direito",
                               "Em vez de clicar no canto inferior direito", False))
        group.add(self._switch("input:touchpad:disable_while_typing", "Desativar enquanto digita",
                               "Evita mover o cursor sem querer", True))
        group.add(self._spin("input:touchpad:scroll_factor", "Velocidade da rolagem", "1 é o normal",
                             0.1, 3, 0.1, 1.0, digits=1))
        self.add(group)

    def _behavior_group(self) -> None:
        group = Adw.PreferencesGroup(title="Comportamento")
        group.add(self._switch("misc:focus_on_activate", "Focar janelas que pedem atenção",
                               "Ex.: ao abrir um link, o navegador vem para frente", False))
        group.add(self._switch("binds:workspace_back_and_forth", "Voltar ao workspace anterior",
                               "Ir para o workspace em que você já está volta para o anterior", False))
        group.add(self._switch("misc:middle_click_paste", "Colar com o botão do meio", "", True))
        group.add(self._switch("cursor:hide_on_key_press", "Esconder o cursor ao digitar", "", False))
        group.add(self._spin("cursor:inactive_timeout", "Esconder o cursor parado",
                             "Segundos sem mexer o mouse; 0 nunca esconde", 0, 60, 1, 0))
        self.add(group)

    # ------------------------------------------------------------------ linhas
    def _initial(self, key: str, default):
        saved = self.store.get(key)
        if saved is not None:
            return saved
        live = core.live_option(key)
        return default if live is None else live

    def _register(self, key: str, row, set_widget: Callable, default) -> None:
        """Botão ↶ por opção, visível só quando este app sobrescreve o valor."""
        undo = Gtk.Button(icon_name="edit-undo-symbolic", valign=Gtk.Align.CENTER,
                          tooltip_text="Voltar ao padrão do Omarchy")
        undo.add_css_class("flat")
        undo.set_visible(self.store.get(key) is not None)
        undo.connect("clicked", lambda _b: self._reset_keys([key]))
        row.add_suffix(undo)
        self.controls[key] = (set_widget, default, undo)

    def _changed(self, key: str, value) -> None:
        if self._updating:
            return
        self.store.set(key, value)
        self.controls[key][2].set_visible(True)
        if key in ("input:kb_layout", "input:kb_variant"):
            self._sync_keyboard_row()

    def _sync_keyboard_row(self) -> None:
        """Mantém a lista de layouts comuns de acordo com os campos de Avançado (após editar ou restaurar)."""
        layout = self.entries["input:kb_layout"].get_text().strip()
        variant = self.entries["input:kb_variant"].get_text().strip()
        updating, self._updating = self._updating, True
        try:
            self._kb_row.set_selected(keyboard_index(layout, variant))
        finally:
            self._updating = updating

    def _spin(self, key, title, subtitle, lo, hi, step, default, digits=0) -> Adw.SpinRow:
        row = Adw.SpinRow.new_with_range(lo, hi, step)
        row.set_title(title)
        row.set_subtitle(subtitle)
        row.set_digits(digits)
        row.set_value(to_float(self._initial(key, default), default))
        row.connect("notify::value",
                    lambda r, _p: self._changed(key, round(r.get_value(), digits) if digits else int(r.get_value())))
        self._register(key, row, lambda v: row.set_value(to_float(v, default)), default)
        return row

    def _percent(self, key, title, subtitle, lo, hi, default) -> Adw.SpinRow:
        """Opção de 0 a 1 mostrada como porcentagem."""
        row = Adw.SpinRow.new_with_range(lo, hi, 1)
        row.set_title(title)
        row.set_subtitle(subtitle)
        row.set_value(round(to_float(self._initial(key, default), default) * 100))
        row.connect("notify::value", lambda r, _p: self._changed(key, round(r.get_value() / 100, 2)))
        self._register(key, row, lambda v: row.set_value(round(to_float(v, default) * 100)), default)
        return row

    def _switch(self, key, title, subtitle, default) -> Adw.SwitchRow:
        row = Adw.SwitchRow(title=title, subtitle=subtitle)
        row.set_active(to_bool(self._initial(key, default), default))
        row.connect("notify::active", lambda r, _p: self._changed(key, r.get_active()))
        self._register(key, row, lambda v: row.set_active(to_bool(v, default)), default)
        return row

    def _choice(self, key, title, default, options, subtitle_for: Callable | None = None) -> Adw.ComboRow:
        """Lista de (valor, rótulo); um valor atual fora da lista entra como opção extra."""
        options = list(options)
        values = [str(v) for v, _ in options]
        current = str(self._initial(key, default))
        if current not in values:
            options.append((current, f"Personalizado ({current})"))
            values.append(current)
        row = Adw.ComboRow(title=title, subtitle=subtitle_for(current) if subtitle_for else "")
        row.set_model(Gtk.StringList.new([label for _, label in options]))
        row.set_selected(values.index(current))

        def on_selected(r, _p) -> None:
            value = options[r.get_selected()][0]
            if subtitle_for:
                r.set_subtitle(subtitle_for(str(value)))
            self._changed(key, value)

        def set_widget(v) -> None:
            v = str(v)
            if v in values:
                row.set_selected(values.index(v))
                if subtitle_for:
                    row.set_subtitle(subtitle_for(v))

        row.connect("notify::selected", on_selected)
        self._register(key, row, set_widget, default)
        return row

    @staticmethod
    def _layout_subtitle(value: str) -> str:
        return next((desc for k, _, desc in LAYOUTS if k == value), "")

    def _entry(self, key, title, default) -> Adw.EntryRow:
        row = self.entries[key] = Adw.EntryRow(title=title)
        row.set_text(str(self._initial(key, default) or ""))
        row.set_show_apply_button(True)
        row.connect("apply", lambda r: self._changed(key, r.get_text().strip()))
        self._register(key, row, lambda v: row.set_text(str(v or "")), default)
        return row

    def _keyboard_row(self) -> Adw.ComboRow:
        """Atalho para os layouts mais comuns; o resto fica em Avançado."""
        layout = str(self._initial("input:kb_layout", "us"))
        variant = str(self._initial("input:kb_variant", "") or "")
        labels = [label for label, _, _ in KEYBOARDS] + ["Personalizado (veja Avançado)"]
        current = keyboard_index(layout, variant)
        row = self._kb_row = Adw.ComboRow(title="Layout do teclado", subtitle="Teste digitando acentos e ç depois de trocar")
        row.set_model(Gtk.StringList.new(labels))
        row.set_selected(current)

        def on_selected(r, _p) -> None:
            i = r.get_selected()
            if i >= len(KEYBOARDS) or self._updating:
                return
            _, lay, var = KEYBOARDS[i]
            # grava direto: _changed ressincronizaria esta mesma lista no meio do sinal e entraria em laço
            for key, value in (("input:kb_layout", lay), ("input:kb_variant", var)):
                self.store.set(key, value)
                self.controls[key][2].set_visible(True)
            self._updating = True
            try:
                self.controls["input:kb_layout"][0](lay)
                self.controls["input:kb_variant"][0](var)
            finally:
                self._updating = False

        row.connect("notify::selected", on_selected)
        return row

    # ------------------------------------------------------------------ estilos e restauração
    def _apply_preset(self, name: str, values: dict) -> None:
        self._updating = True
        try:
            for key in PRESET_KEYS:
                if key in values:
                    self.store.set(key, values[key])
                    set_widget, _default, undo = self.controls[key]
                    set_widget(values[key])
                    undo.set_visible(True)
                elif self.store.get(key) is not None:
                    self.store.unset(key)
        finally:
            self._updating = False
        restored = [k for k in PRESET_KEYS if k not in values]
        if restored:
            # o que voltou ao padrão só é conhecido depois que o Hyprland recarrega
            GLib.timeout_add(1200, self._sync_from_live, restored)
        self.win.toast(f"Estilo {name} aplicado")

    def _reset_keys(self, keys: list[str]) -> None:
        for key in keys:
            self.store.unset(key)
        GLib.timeout_add(1200, self._sync_from_live, keys)

    def _sync_from_live(self, keys: list[str]) -> bool:
        def read() -> dict:
            return {k: core.live_option(k) for k in keys}

        def apply(result) -> None:
            if isinstance(result, Exception):
                return
            self._updating = True
            try:
                for key, value in result.items():
                    if key not in self.controls or self.store.get(key) is not None:
                        continue
                    set_widget, default, undo = self.controls[key]
                    set_widget(default if value is None else value)
                    undo.set_visible(False)
                if "input:kb_layout" in result or "input:kb_variant" in result:
                    self._sync_keyboard_row()
            finally:
                self._updating = False

        bg(read, apply)
        return False

    def _reset_all(self) -> None:
        self.store.reset_options()
        GLib.timeout_add(1200, self._sync_from_live, list(self.controls))
        self.win.toast("Opções do Hyprland restauradas")
