"""Página da barra (Waybar) e fontes do sistema."""
from __future__ import annotations

import re
import shutil

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw  # noqa: E402

from .. import core
from ..ui import bg, button_row, combo_row

WAYBAR_DIR = core.CONF_DIR / "waybar"
WAYBAR_CONFIG = WAYBAR_DIR / "config.jsonc"
WAYBAR_STYLE = WAYBAR_DIR / "style.css"
POSITION_RE = re.compile(r'("position"\s*:\s*")(top|bottom)(")')
POSITIONS = ["top", "bottom"]
POSITION_LABELS = ["Topo", "Rodapé"]


def read_position() -> int:
    try:
        m = POSITION_RE.search(WAYBAR_CONFIG.read_text())
    except OSError:
        return 0
    return POSITIONS.index(m.group(2)) if m else 0


def write_position(position: str) -> bool:
    try:
        text = WAYBAR_CONFIG.read_text()
    except OSError:
        return False
    if not POSITION_RE.search(text):
        return False
    backup = WAYBAR_CONFIG.with_name(WAYBAR_CONFIG.name + ".omarchy-settings.bak")
    if not backup.exists():
        shutil.copy2(WAYBAR_CONFIG, backup)
    WAYBAR_CONFIG.write_text(POSITION_RE.sub(rf"\g<1>{position}\g<3>", text, count=1))
    core.restart_waybar()
    return True


class BarPage(Adw.PreferencesPage):
    def __init__(self, win):
        super().__init__()
        self.win = win

        bar = Adw.PreferencesGroup(title="Waybar")
        if WAYBAR_CONFIG.exists():
            bar.add(combo_row("Posição da barra", "Alterada em config.jsonc (backup criado)", POSITION_LABELS,
                              read_position(), self._on_position))
        bar.add(button_row("Mostrar ou ocultar", "Alterna a visibilidade da barra", "Alternar", self._toggle))
        bar.add(button_row("Reiniciar", "Recarrega a barra após editar arquivos", "Reiniciar",
                           lambda: bg(core.restart_waybar, lambda _r: win.toast("Waybar reiniciada"))))
        bar.add(button_row("Editar config.jsonc", "Módulos e layout", "Abrir", lambda: core.open_in_editor(WAYBAR_CONFIG)))
        bar.add(button_row("Editar style.css", "Cores e espaçamentos", "Abrir", lambda: core.open_in_editor(WAYBAR_STYLE)))
        self.add(bar)

        self.font_group = Adw.PreferencesGroup(title="Fonte do sistema", description="Aplicada ao terminal, barra e demais apps do Omarchy.")
        self.add(self.font_group)
        if core.have("omarchy-font-set"):
            bg(lambda: ([f.strip() for f in core.out(["omarchy-font-list"]).splitlines() if f.strip()],
                        core.out(["omarchy-font-current"])), self._populate_fonts)
        else:
            self.font_group.add(Adw.ActionRow(title="omarchy-font-set não encontrado",
                                              subtitle="Atualize o Omarchy para trocar fontes por aqui"))

    def _on_position(self, index: int) -> None:
        ok = write_position(POSITIONS[index])
        self.win.toast("Posição atualizada" if ok else "Não encontrei \"position\" no config.jsonc")

    def _toggle(self) -> None:
        if core.have("omarchy-toggle-waybar"):
            core.spawn(["omarchy-toggle-waybar"])
        else:
            core.run(["pkill", "-SIGUSR1", "waybar"])

    def _populate_fonts(self, result) -> None:
        if isinstance(result, Exception) or not result[0]:
            self.font_group.add(Adw.ActionRow(title="Nenhuma fonte listada", subtitle="omarchy-font-list sem saída"))
            return
        fonts, current = result
        selected = fonts.index(current) if current in fonts else 0
        row = combo_row("Fonte", f"Atual: {current or 'desconhecida'}", fonts, selected, lambda i: self._set_font(fonts[i]))
        self.font_group.add(row)

    def _set_font(self, name: str) -> None:
        self.win.toast(f"Aplicando {name}…")

        def done(res) -> None:
            ok = not isinstance(res, Exception) and res is not None and res.returncode == 0
            self.win.toast(f"Fonte {name} aplicada" if ok else f"Falha ao aplicar {name}")

        bg(lambda: core.run(["omarchy-font-set", name], timeout=60), done)
