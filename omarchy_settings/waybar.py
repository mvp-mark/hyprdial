"""Waybar como barra alternativa à do Omarchy shell (sem GTK, testável).

O Omarchy atual não gerencia a Waybar. Este módulo cria uma configuração inicial em ~/.config/waybar,
faz o estilo seguir o tema do Omarchy e liga a Waybar no lugar da barra do shell:

- cores: um template do usuário (~/.config/omarchy/themed/waybar.css.tpl) que o próprio Omarchy renderiza
  em ~/.local/state/omarchy/current/theme/waybar.css a cada troca de tema; o style.css o importa;
- hooks do Omarchy: theme-set.d recarrega a Waybar após trocar o tema e post-boot.d a inicia no login.
"""
from __future__ import annotations

import re
import shutil
import tomllib
from pathlib import Path

from . import core

CONFIG_DIR = core.CONF_DIR / "waybar"
CONFIG = CONFIG_DIR / "config.jsonc"
STYLE = CONFIG_DIR / "style.css"
THEME_DIR = core.HOME / ".local/state/omarchy/current/theme"
TEMPLATE = core.CONF_DIR / "omarchy" / "themed" / "waybar.css.tpl"
RENDERED = THEME_DIR / "waybar.css"
HOOKS_DIR = core.CONF_DIR / "omarchy" / "hooks"
HOOK_NAME = "omarchy-settings-waybar"
THEME_HOOK = HOOKS_DIR / "theme-set.d" / HOOK_NAME
BOOT_HOOK = HOOKS_DIR / "post-boot.d" / HOOK_NAME
BAR_OFF_FLAG = core.HOME / ".local/state/omarchy/toggles/bar-off"

POSITIONS = ("top", "bottom", "left", "right")
POSITION_RE = re.compile(r'("position"\s*:\s*")(top|bottom|left|right)(")')

TEMPLATE_CSS = """/* Gerado pelo omarchy-settings: cores do tema atual para a Waybar. */
@define-color background {{ background }};
@define-color foreground {{ foreground }};
@define-color accent {{ accent }};
@define-color muted {{ muted }};
@define-color red {{ red }};
@define-color yellow {{ yellow }};
@define-color green {{ green }};
"""

# Ícones Material Design das Nerd Fonts (plano suplementar), escritos como escapes para não se perderem.
ICONS = {
    "logo": "\U000F08C7", "bt": "\U000F00AF", "bt_on": "\U000F00B1", "bt_off": "\U000F00B2",
    "wifi": "\U000F05A9", "eth": "\U000F0200", "offline": "\U000F092E", "mute": "\U000F0581",
    "vol_low": "\U000F057F", "vol_mid": "\U000F0580", "vol_high": "\U000F057E", "cpu": "\U000F061A",
    "bat_20": "\U000F007B", "bat_40": "\U000F007D", "bat_60": "\U000F007F", "bat_80": "\U000F0081",
    "bat_full": "\U000F0079",
}

STARTER_CONFIG_TEMPLATE = """// Configuração inicial criada pelo omarchy-settings. Pode editar à vontade.
// Documentação: https://github.com/Alexays/Waybar/wiki
{
  "layer": "top",
  "position": "top",
  "height": 28,
  "spacing": 4,
  "modules-left": ["custom/omarchy", "hyprland/workspaces"],
  "modules-center": ["clock"],
  "modules-right": ["tray", "bluetooth", "network", "pulseaudio", "cpu", "battery"],

  "custom/omarchy": {
    "format": "@logo@",
    "tooltip": false,
    "on-click": "omarchy-menu"
  },
  "hyprland/workspaces": {
    "on-click": "activate",
    "format": "{name}"
  },
  "clock": {
    "format": "{:%A %H:%M}",
    "tooltip-format": "<tt>{calendar}</tt>"
  },
  "tray": { "spacing": 8 },
  "bluetooth": {
    "format": "@bt@",
    "format-disabled": "@bt_off@",
    "format-connected": "@bt_on@",
    "tooltip-format": "{device_alias}",
    "on-click": "omarchy-launch-or-focus-tui bluetui"
  },
  "network": {
    "format-wifi": "@wifi@ {essid}",
    "format-ethernet": "@eth@",
    "format-disconnected": "@offline@",
    "tooltip-format": "{ifname} {ipaddr}",
    "on-click": "omarchy-launch-or-focus-tui impala"
  },
  "pulseaudio": {
    "format": "{icon} {volume}%",
    "format-muted": "@mute@",
    "format-icons": { "default": ["@vol_low@", "@vol_mid@", "@vol_high@"] },
    "on-click": "omarchy-launch-or-focus-tui wiremix"
  },
  "cpu": { "format": "@cpu@ {usage}%", "interval": 5 },
  "battery": {
    "format": "{icon} {capacity}%",
    "format-icons": ["@bat_20@", "@bat_40@", "@bat_60@", "@bat_80@", "@bat_full@"],
    "states": { "warning": 20, "critical": 10 }
  }
}
"""
STARTER_CONFIG = re.sub(r"@(\w+)@", lambda m: ICONS[m.group(1)], STARTER_CONFIG_TEMPLATE)


def starter_style() -> str:
    # o caminho absoluto evita depender de onde a Waybar resolve imports relativos
    return f"""/* Estilo inicial criado pelo omarchy-settings. As cores vêm do tema do Omarchy. */
@import "{RENDERED}";

* {{
  font-family: monospace;
  font-size: 13px;
  border: none;
  border-radius: 0;
  min-height: 0;
}}

window#waybar {{
  background: alpha(@background, 0.92);
  color: @foreground;
}}

#workspaces button {{
  color: @muted;
  padding: 0 6px;
}}

#workspaces button.active {{
  color: @accent;
}}

#custom-omarchy, #clock, #tray, #bluetooth, #network, #pulseaudio, #cpu, #battery {{
  padding: 0 8px;
}}

#custom-omarchy {{
  color: @accent;
}}

#battery.warning {{
  color: @yellow;
}}

#battery.critical, #pulseaudio.muted, #network.disconnected {{
  color: @red;
}}
"""


THEME_HOOK_SCRIPT = """#!/bin/bash
# Gerado pelo omarchy-settings: recarrega a Waybar para aplicar as cores do novo tema.
pkill -SIGUSR2 -x waybar || true
"""

BOOT_HOOK_SCRIPT = """#!/bin/bash
# Gerado pelo omarchy-settings: inicia a Waybar no lugar da barra do Omarchy.
pgrep -x waybar >/dev/null || setsid uwsm-app -- waybar >/dev/null 2>&1 &
"""


# ------------------------------------------------------------------ estado
def installed() -> bool:
    return core.have("waybar")


def running() -> bool:
    r = core.run(["pgrep", "-x", "waybar"])
    return bool(r and r.returncode == 0)


def enabled() -> bool:
    """A Waybar foi escolhida no lugar da barra do Omarchy (inicia no login)."""
    return BOOT_HOOK.exists()


def has_config() -> bool:
    return CONFIG.exists()


# ------------------------------------------------------------------ cores do tema
def render(template: str, colors: dict) -> str:
    return re.sub(r"\{\{\s*(\w+)\s*\}\}", lambda m: str(colors.get(m.group(1), m.group(0))), template)


def render_theme_css() -> bool:
    """Gera o waybar.css do tema atual agora; nas próximas trocas de tema o Omarchy faz isso sozinho."""
    try:
        colors = tomllib.loads((THEME_DIR / "colors.toml").read_text())
        RENDERED.write_text(render(TEMPLATE.read_text(), colors))
        return True
    except (OSError, tomllib.TOMLDecodeError):
        return False


# ------------------------------------------------------------------ arquivos
def _write_hook(path: Path, script: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(script)
    path.chmod(0o755)


def ensure_config() -> None:
    """Cria config, estilo, template de cores e hook de tema, sem sobrescrever o que já existe."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG.exists():
        CONFIG.write_text(STARTER_CONFIG)
    if not STYLE.exists():
        STYLE.write_text(starter_style())
    if not TEMPLATE.exists():
        TEMPLATE.parent.mkdir(parents=True, exist_ok=True)
        TEMPLATE.write_text(TEMPLATE_CSS)
    _write_hook(THEME_HOOK, THEME_HOOK_SCRIPT)
    render_theme_css()


def reset_config() -> None:
    """Volta config e estilo ao inicial, guardando os atuais com a extensão .omarchy-settings.bak."""
    for path in (CONFIG, STYLE):
        if path.exists():
            shutil.copy2(path, path.with_name(path.name + ".omarchy-settings.bak"))
            path.unlink()
    ensure_config()


def read_position() -> str:
    try:
        m = POSITION_RE.search(CONFIG.read_text())
    except OSError:
        return "top"
    return m.group(2) if m else "top"


def write_position(position: str) -> bool:
    if position not in POSITIONS:
        raise ValueError(position)
    try:
        text = CONFIG.read_text()
    except OSError:
        return False
    if not POSITION_RE.search(text):
        return False
    CONFIG.write_text(POSITION_RE.sub(rf"\g<1>{position}\g<3>", text, count=1))
    return True


# ------------------------------------------------------------------ processo
def start() -> bool:
    if running():
        return True
    prefix = ["uwsm-app", "--"] if core.have("uwsm-app") else []
    return core.spawn(prefix + ["waybar"])


def stop() -> None:
    core.run(["pkill", "-x", "waybar"])


def reload() -> None:
    """A Waybar relê config e estilo com SIGUSR2."""
    core.run(["pkill", "-SIGUSR2", "-x", "waybar"])


def set_enabled(on: bool) -> None:
    """Liga a Waybar no lugar da barra do Omarchy (e no login), ou volta para a barra do Omarchy."""
    if on:
        ensure_config()
        _write_hook(BOOT_HOOK, BOOT_HOOK_SCRIPT)
        start()
        core.run(["omarchy-toggle-bar", "on"])  # liga a flag bar-off: esconde a barra do shell
    else:
        BOOT_HOOK.unlink(missing_ok=True)
        stop()
        core.run(["omarchy-toggle-bar", "off"])  # mostra a barra do shell de novo
