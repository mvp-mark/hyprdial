"""Núcleo sem dependência de GTK: execução de comandos e edição das configs do Hyprland.

Estratégia: nada do que o Omarchy gerencia é alterado. Os ajustes do usuário ficam em
~/.config/hypr/omarchy-settings.conf (gerado) e uma única linha `source = ...` é
acrescentada ao final de hyprland.conf para que esses valores tenham a palavra final.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from pathlib import Path

HOME = Path.home()
CONF_DIR = HOME / ".config"
HYPR_MAIN = CONF_DIR / "hypr" / "hyprland.conf"
HYPR_MANAGED = CONF_DIR / "hypr" / "omarchy-settings.conf"
STATE_FILE = CONF_DIR / "omarchy-settings" / "state.json"
SOURCE_LINE = "source = ~/.config/hypr/omarchy-settings.conf"
HEADER = (
    "# Gerado por omarchy-settings. Edições manuais serão sobrescritas.\n"
    "# Para voltar ao padrão do Omarchy, apague este arquivo ou use 'Restaurar padrões'.\n"
)


# --------------------------------------------------------------------------- processos
def have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def run(args: list[str], timeout: float = 10) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None


def out(args: list[str], timeout: float = 10) -> str:
    r = run(args, timeout)
    return r.stdout.strip() if r and r.returncode == 0 else ""


def spawn(args: list[str]) -> bool:
    """Inicia um processo desacoplado da janela."""
    try:
        subprocess.Popen(
            args,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return True
    except OSError:
        return False


def launch_tui(cmd: str) -> bool:
    if have("omarchy-launch-tui"):
        return spawn(["omarchy-launch-tui", cmd])
    if have("xdg-terminal-exec"):
        return spawn(["xdg-terminal-exec", cmd])
    return spawn(["alacritty", "-e", cmd])


def open_in_editor(path: Path) -> bool:
    if have("omarchy-launch-editor"):
        return spawn(["omarchy-launch-editor", str(path)])
    return spawn(["xdg-open", str(path)])


def restart_waybar() -> None:
    if have("omarchy-restart-waybar"):
        run(["omarchy-restart-waybar"], timeout=15)
    else:
        run(["pkill", "-SIGUSR2", "waybar"])


# --------------------------------------------------------------------------- Hyprland
def live_option(key: str):
    """Valor atual de uma opção no Hyprland em execução (ou None)."""
    raw = out(["hyprctl", "getoption", key, "-j"])
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    for field in ("int", "float", "str"):
        if field in data:
            return data[field]
    custom = data.get("custom")  # ex.: gaps_in => "5 5 5 5"
    if isinstance(custom, str) and custom.split():
        return custom.split()[0]
    return None


def fmt(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.2f}".rstrip("0").rstrip(".") if value % 1 else str(int(value))
    return str(value)


def render(values: dict[str, str]) -> str:
    """Converte {'decoration:blur:enabled': 'true', ...} em blocos do Hyprland."""
    tree: dict = {}
    for key in sorted(values):
        *path, leaf = key.split(":")
        node = tree
        for part in path:
            node = node.setdefault(part, {})
        node[leaf] = values[key]

    lines = [HEADER]

    def emit(node: dict, depth: int) -> None:
        pad = "    " * depth
        for k, v in node.items():
            if not isinstance(v, dict):
                lines.append(f"{pad}{k} = {v}")
        for k, v in node.items():
            if isinstance(v, dict):
                lines.append(f"{pad}{k} {{")
                emit(v, depth + 1)
                lines.append(f"{pad}}}")

    emit(tree, 0)
    return "\n".join(lines) + "\n"


class HyprStore:
    """Guarda ajustes do Hyprland, aplica ao vivo (hyprctl keyword) e persiste em arquivo."""

    DEBOUNCE = 0.25

    def __init__(self, managed: Path = HYPR_MANAGED, main: Path = HYPR_MAIN, state: Path = STATE_FILE):
        self.managed, self.main, self.state_file = managed, main, state
        self.values: dict[str, str] = self._load()
        self._pending: dict[str, str | None] = {}
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None

    # -- estado
    def _load(self) -> dict[str, str]:
        try:
            data = json.loads(self.state_file.read_text())
            return {str(k): str(v) for k, v in data.get("hypr", {}).items()}
        except (OSError, ValueError, AttributeError):
            return {}

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def set(self, key: str, value) -> None:
        self._queue(key, fmt(value))

    def unset(self, key: str) -> None:
        self._queue(key, None)

    def reset(self) -> None:
        for key in list(self.values):
            self._queue(key, None)

    def _queue(self, key: str, value: str | None) -> None:
        with self._lock:
            self._pending[key] = value
            if self._timer:
                self._timer.cancel()
            self._timer = threading.Timer(self.DEBOUNCE, self.flush)
            self._timer.daemon = True
            self._timer.start()

    # -- aplicação
    def flush(self) -> None:
        with self._lock:
            pending, self._pending = self._pending, {}
        if not pending:
            return
        needs_reload = False
        for key, value in pending.items():
            if value is None:
                self.values.pop(key, None)
                needs_reload = True  # não existe 'unset' ao vivo: recarrega a config
            else:
                self.values[key] = value
                run(["hyprctl", "keyword", key, value])
        self.save()
        if needs_reload:
            run(["hyprctl", "reload"])

    def save(self) -> None:
        self.managed.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.managed.with_suffix(".tmp")
        tmp.write_text(render(self.values))
        os.replace(tmp, self.managed)
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps({"hypr": self.values}, indent=2))
        self.ensure_sourced()

    def ensure_sourced(self) -> None:
        if not self.main.exists():
            return
        text = self.main.read_text()
        if "omarchy-settings.conf" in text:
            return
        backup = self.main.with_name(self.main.name + ".omarchy-settings.bak")
        if not backup.exists():
            shutil.copy2(self.main, backup)
        sep = "" if text.endswith("\n") else "\n"
        self.main.write_text(f"{text}{sep}\n# Adicionado por omarchy-settings\n{SOURCE_LINE}\n")
