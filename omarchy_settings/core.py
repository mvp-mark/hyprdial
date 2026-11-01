"""Núcleo sem dependência de GTK: execução de comandos e edição das configs do Hyprland.

Estratégia: nada do que o Omarchy gerencia é alterado. Os ajustes do usuário ficam em
~/.config/hypr/omarchy-settings.lua (gerado) e uma única linha `require(...)` é
inserida em hyprland.lua, depois dos arquivos do usuário, para que esses valores
tenham a palavra final.
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
HYPR_MAIN = CONF_DIR / "hypr" / "hyprland.lua"
HYPR_MANAGED = CONF_DIR / "hypr" / "omarchy-settings.lua"
STATE_FILE = CONF_DIR / "omarchy-settings" / "state.json"
REQUIRE_LINE = 'require("hypr.omarchy-settings")'
TOGGLES_LINE = 'require("default.hypr.toggles")'
HEADER = (
    "-- Gerado por omarchy-settings. Edições manuais serão sobrescritas.\n"
    "-- Para voltar ao padrão do Omarchy, apague este arquivo ou use 'Restaurar padrões'.\n"
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
    for field in ("bool", "int", "float"):
        if field in data:
            return data[field]
    if "str" in data:
        return "" if data["str"] == "[[EMPTY]]" else data["str"]
    for field in ("css", "custom"):  # ex.: gaps_in => "5 5 5 5"
        value = data.get(field)
        if isinstance(value, str) and value.split():
            return value.split()[0]
    return None


def fmt(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.6f}".rstrip("0").rstrip(".") if value % 1 else str(int(value))
    return str(value)


def lua(value) -> str:
    """Literal Lua para um valor Python já tipado (bool, número ou string)."""
    if isinstance(value, (bool, int, float)):
        return fmt(value)
    text = str(value)
    if any(ord(c) < 32 for c in text):
        raise ValueError(f"valor inválido: {text!r}")
    return json.dumps(text, ensure_ascii=False)


def option_lua(text: str) -> str:
    """Opções são guardadas como texto; recupera bool/número antes de virar Lua."""
    if text in ("true", "false"):
        return text
    try:
        float(text)
        return text
    except ValueError:
        return lua(text)


def lua_key(name: str) -> str:
    """Na API Lua, opções com hífen (ex.: 'tap-to-click' do hyprctl) usam sublinhado."""
    return name.replace("-", "_")


def config_call(values: dict[str, str]) -> str:
    """Converte {'decoration:blur:enabled': 'true', ...} em hl.config({ ... })."""
    tree: dict = {}
    for key in sorted(values):
        *path, leaf = key.split(":")
        node = tree
        for part in path:
            node = node.setdefault(part, {})
        node[leaf] = values[key]

    lines = ["hl.config({"]

    def emit(node: dict, depth: int) -> None:
        pad = "  " * depth
        for k, v in node.items():
            if isinstance(v, dict):
                lines.append(f"{pad}{lua_key(k)} = {{")
                emit(v, depth + 1)
                lines.append(f"{pad}}},")
            else:
                lines.append(f"{pad}{lua_key(k)} = {option_lua(v)},")

    emit(tree, 1)
    lines.append("})")
    return "\n".join(lines)


MONITOR_FIELDS = ("output", "disabled", "mode", "position", "scale", "transform", "vrr", "mirror", "bitdepth")


def monitor_call(rule: dict) -> str:
    fields = ", ".join(f"{k} = {lua(rule[k])}" for k in MONITOR_FIELDS if k in rule)
    return f"hl.monitor({{ {fields} }})"


def render(values: dict[str, str], monitors: dict[str, dict], bindings: dict | None = None) -> str:
    from . import keybinds  # importado aqui: keybinds depende deste módulo

    parts = [HEADER]
    if values:
        parts.append(config_call(values))
    parts.extend(monitor_call(monitors[name]) for name in sorted(monitors))
    parts.extend(keybinds.render(bindings or {}))
    return "\n".join(parts) + "\n"


def list_monitors() -> list[dict]:
    """Monitores conectados (inclusive desativados) segundo o Hyprland em execução."""
    try:
        data = json.loads(out(["hyprctl", "monitors", "all", "-j"]))
    except (ValueError, TypeError):
        return []
    return data if isinstance(data, list) else []


def live_rule(mon: dict) -> dict:
    """Regra hl.monitor equivalente ao estado atual de um monitor."""
    rule = {
        "output": mon["name"],
        "mode": f"{mon['width']}x{mon['height']}@{mon['refreshRate']:.2f}",
        "position": f"{mon['x']}x{mon['y']}",
        "scale": mon["scale"],
        "transform": mon.get("transform", 0),
    }
    if mon.get("vrr"):
        rule["vrr"] = 1
    if mon.get("mirrorOf") not in (None, "", "none"):
        rule["mirror"] = mon["mirrorOf"]
    if mon.get("disabled"):
        rule["disabled"] = True
    return rule


class HyprStore:
    """Guarda ajustes do Hyprland, aplica ao vivo (hyprctl eval) e persiste em arquivo."""

    DEBOUNCE = 0.25

    def __init__(self, managed: Path = HYPR_MANAGED, main: Path = HYPR_MAIN, state: Path = STATE_FILE):
        self.managed, self.main, self.state_file = managed, main, state
        self.values, self.monitors, self.bindings = self._load()
        self._pending: dict[str, str | None] = {}
        self._pending_monitors: dict[str, dict | None] = {}
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None

    # -- estado
    def _load(self) -> tuple[dict[str, str], dict[str, dict], dict]:
        empty = {"overrides": {}, "custom": []}
        try:
            data = json.loads(self.state_file.read_text())
            values = {str(k): str(v) for k, v in data.get("hypr", {}).items()}
            monitors = {str(k): dict(v) for k, v in data.get("monitors", {}).items()}
            bindings = data.get("bindings") if isinstance(data.get("bindings"), dict) else empty
            return values, monitors, {**empty, **bindings}
        except (OSError, ValueError, AttributeError, TypeError):
            return {}, {}, empty

    # leituras consideram o que ainda está na fila, para mudanças seguidas não se sobrescreverem
    def get(self, key: str) -> str | None:
        with self._lock:
            if key in self._pending:
                return self._pending[key]
        return self.values.get(key)

    def set(self, key: str, value) -> None:
        self._queue(self._pending, key, fmt(value))

    def unset(self, key: str) -> None:
        self._queue(self._pending, key, None)

    def get_monitor(self, output: str) -> dict | None:
        with self._lock:
            rule = self._pending_monitors.get(output, self.monitors.get(output))
        return dict(rule) if rule else None

    def set_monitor(self, rule: dict) -> None:
        self._queue(self._pending_monitors, rule["output"], dict(rule))

    def unset_monitor(self, output: str) -> None:
        self._queue(self._pending_monitors, output, None)

    def reset_options(self) -> None:
        """Remove só as opções do Hyprland; monitores e atalhos têm restauração própria."""
        for key in list(self.values):
            self.unset(key)

    def apply_bindings(self, bindings: dict) -> None:
        """Grava os atalhos e recarrega o Hyprland na hora (chamar fora da thread da interface)."""
        self.flush()
        with self._lock:
            self.bindings = bindings
        self.save()
        run(["hyprctl", "reload"])

    def _queue(self, pending: dict, key: str, value) -> None:
        with self._lock:
            pending[key] = value
        self._schedule()

    def _schedule(self) -> None:
        with self._lock:
            if self._timer:
                self._timer.cancel()
            self._timer = threading.Timer(self.DEBOUNCE, self.flush)
            self._timer.daemon = True
            self._timer.start()

    # -- aplicação
    def flush(self) -> None:
        with self._lock:
            pending, self._pending = self._pending, {}
            monitors, self._pending_monitors = self._pending_monitors, {}
        if not pending and not monitors:
            return
        needs_reload = False
        changed: dict[str, str] = {}
        for key, value in pending.items():
            if value is None:
                self.values.pop(key, None)
                needs_reload = True  # não existe 'unset' ao vivo: recarrega a config
            else:
                self.values[key] = changed[key] = value
        live = [config_call(changed)] if changed else []
        for output, rule in monitors.items():
            if rule is None:
                self.monitors.pop(output, None)
                needs_reload = True
            else:
                self.monitors[output] = rule
                live.append(monitor_call(rule))
        self.save()
        if needs_reload:
            run(["hyprctl", "reload"])
        else:
            for code in live:
                run(["hyprctl", "eval", code])

    def save(self) -> None:
        self.managed.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.managed.with_suffix(".tmp")
        tmp.write_text(render(self.values, self.monitors, self.bindings))
        os.replace(tmp, self.managed)
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps({"hypr": self.values, "monitors": self.monitors,
                                               "bindings": self.bindings}, indent=2, ensure_ascii=False))
        self.ensure_required()

    def ensure_required(self) -> None:
        """Carrega o arquivo gerado depois dos do usuário, mas antes dos toggles do Omarchy."""
        if not self.main.exists():
            return
        text = self.main.read_text()
        if REQUIRE_LINE in text:
            return
        backup = self.main.with_name(self.main.name + ".omarchy-settings.bak")
        if not backup.exists():
            shutil.copy2(self.main, backup)
        block = f"-- Adicionado por omarchy-settings\n{REQUIRE_LINE}\n"
        lines = text.splitlines(keepends=True)
        for i, line in enumerate(lines):
            if line.strip() == TOGGLES_LINE:
                while i > 0 and lines[i - 1].lstrip().startswith("--"):
                    i -= 1  # mantém o comentário junto da linha que ele descreve
                lines.insert(i, block + "\n")
                break
        else:
            sep = "" if text.endswith("\n") else "\n"
            lines.append(f"{sep}\n{block}")
        self.main.write_text("".join(lines))
