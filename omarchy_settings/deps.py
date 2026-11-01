"""Dependências do app (sem GTK): lista única usada pela janela de dependências e pelo install.sh.

Uso no terminal: python3 -m omarchy_settings.deps [--missing] [--group required|optional|dev] [--exclude PKG]...
"""
from __future__ import annotations

import sys
from dataclasses import dataclass

from . import core
from .i18n import _

GROUPS = ("required", "optional", "dev")


@dataclass(frozen=True)
class Dep:
    package: str
    group: str
    purpose: str
    default: bool = True  # pré-selecionado para instalar quando estiver faltando


def dependencies() -> list[Dep]:
    return [
        Dep("python-gobject", "required", _("Python bindings for GTK")),
        Dep("gtk4", "required", _("Interface toolkit")),
        Dep("libadwaita", "required", _("GNOME widgets and styles (1.5 or newer)")),
        Dep("gettext", "required", _("Compiles the interface translations")),
        Dep("impala", "optional", _("Wi-Fi manager opened by the Connectivity page")),
        Dep("bluetui", "optional", _("Bluetooth manager opened by the Connectivity page")),
        Dep("wiremix", "optional", _("Audio mixer opened by the Connectivity page")),
        Dep("waybar", "optional", _("Alternative bar. Omarchy uses the Omarchy shell bar; installing Waybar "
                                    "doesn't start it or replace the current bar"), default=False),
        Dep("python-pytest", "dev", _("Runs the project's tests"), default=False),
    ]


def group_title(group: str) -> str:
    return {"required": _("Required"), "optional": _("Optional"), "dev": _("Development")}[group]


def missing(packages: list[str]) -> set[str]:
    """Pacotes não instalados, segundo `pacman -T` (lista só os que faltam)."""
    if not packages:
        return set()
    r = core.run(["pacman", "-T", *packages])
    if r is None:
        return set(packages)  # sem pacman: trata tudo como ausente
    return {line.strip() for line in r.stdout.splitlines() if line.strip()}


def install_command(packages: list[str]) -> list[str]:
    """Instalação com senha gráfica (polkit), para ser chamada pela interface."""
    return ["pkexec", "pacman", "-S", "--needed", "--noconfirm", *packages]


def main(argv: list[str]) -> int:
    only_missing = "--missing" in argv
    group = argv[argv.index("--group") + 1] if "--group" in argv[:-1] else None
    excluded = {argv[i + 1] for i, arg in enumerate(argv[:-1]) if arg == "--exclude"}
    deps = [d for d in dependencies() if (group is None or d.group == group) and d.package not in excluded]
    absent = missing([d.package for d in deps]) if only_missing else set()
    for d in deps:
        if not only_missing or d.package in absent:
            print(d.package)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
