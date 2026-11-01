"""Página de ajustes do Hyprland: aparência, entrada e escala do monitor."""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw  # noqa: E402

from .. import core
from ..ui import button_row, combo_row, entry_row, spin_row, switch_row, to_bool, to_float

SCALES = ["1", "1.25", "1.5", "1.75", "2"]


class HyprlandPage(Adw.PreferencesPage):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.store = win.store

        appearance = Adw.PreferencesGroup(title="Aparência")
        appearance.add(self._spin("general:gaps_in", "Espaço entre janelas", "Em pixels", 0, 40, 1, 5))
        appearance.add(self._spin("general:gaps_out", "Espaço até a borda da tela", "Em pixels", 0, 80, 1, 10))
        appearance.add(self._spin("general:border_size", "Largura da borda", "Em pixels", 0, 10, 1, 2))
        appearance.add(self._spin("decoration:rounding", "Arredondamento", "Raio dos cantos das janelas", 0, 30, 1, 0))
        appearance.add(self._switch("decoration:blur:enabled", "Desfoque (blur)", "Mais bonito, usa mais GPU", True))
        appearance.add(self._switch("animations:enabled", "Animações", "Transições de janelas e workspaces", True))
        self.add(appearance)

        inputs = Adw.PreferencesGroup(title="Teclado e mouse")
        inputs.add(self._entry("input:kb_layout", "Layout do teclado (ex.: br, us)", "us"))
        inputs.add(self._entry("input:kb_variant", "Variante (ex.: intl, abnt2)", ""))
        inputs.add(self._entry("input:kb_options", "Opções (ex.: compose:caps)", ""))
        inputs.add(self._spin("input:repeat_rate", "Taxa de repetição", "Caracteres por segundo", 1, 100, 1, 25))
        inputs.add(self._spin("input:repeat_delay", "Atraso da repetição", "Milissegundos", 100, 1000, 50, 600))
        inputs.add(
            self._spin("input:sensitivity", "Sensibilidade do mouse", "-1.0 mais lento, 1.0 mais rápido", -1, 1, 0.1, 0, 1)
        )
        inputs.add(self._switch("input:touchpad:natural_scroll", "Rolagem natural no touchpad", "", False))
        self.add(inputs)

        monitor = Adw.PreferencesGroup(
            title="Monitor",
            description="Aplica a escala aos monitores sem regra própria em monitors.conf.",
        )
        monitor.add(self._monitor_row())
        self.add(monitor)

        reset = Adw.PreferencesGroup()
        reset.add(
            button_row(
                "Restaurar padrões",
                "Remove todos os ajustes feitos por este app (reabra a janela para atualizar os controles)",
                "Restaurar",
                self._reset,
                "destructive-action",
            )
        )
        self.add(reset)

    # -- valores iniciais: estado salvo > Hyprland em execução > padrão
    def _initial(self, key: str, default):
        saved = self.store.get(key)
        if saved is not None:
            return saved
        live = core.live_option(key)
        return default if live is None else live

    def _spin(self, key, title, subtitle, lo, hi, step, default, digits=0):
        value = to_float(self._initial(key, default), default)
        return spin_row(title, subtitle, lo, hi, step, value, lambda v: self.store.set(key, v), digits)

    def _switch(self, key, title, subtitle, default):
        active = to_bool(self._initial(key, default), default)
        return switch_row(title, subtitle, active, lambda v: self.store.set(key, v))

    def _entry(self, key, title, default):
        text = str(self._initial(key, default) or "")
        return entry_row(title, text, lambda v: self.store.set(key, v))

    def _monitor_row(self):
        saved = self.store.get("monitor")
        selected = 0
        if saved:
            scale = saved.split(",")[-1].strip()
            if scale in SCALES:
                selected = SCALES.index(scale)
        return combo_row("Escala", "Fator de escala da interface", SCALES, selected, self._on_scale)

    def _on_scale(self, index: int) -> None:
        self.store.set("monitor", f",preferred,auto,{SCALES[index]}")

    def _reset(self) -> None:
        self.store.reset()
        self.win.toast("Ajustes do Hyprland restaurados")
