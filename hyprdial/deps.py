"""App dependencies (no GTK): single list used by the dependencies dialog and by install.sh.

Names are Arch's; other families have their own in `names` (None: not packaged there, so not listed).
Command line: python3 -m hyprdial.deps [--missing] [--group required|optional|dev] [--exclude PKG]...
              python3 -m hyprdial.deps --install-command   (e.g. "pacman -S --needed"; empty if unknown)
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field

from . import core, distro, host
from .i18n import _

GROUPS = ("required", "optional", "dev")


@dataclass(frozen=True)
class Dep:
    package: str
    group: str
    purpose: str
    default: bool = True  # preselected for installation when missing
    names: dict[str, str | None] = field(default_factory=dict)  # family -> package name there
    omarchy_only: bool = False

    def on(self, family: str | None) -> Dep | None:
        """This dependency with the package name of a family, or None when it isn't packaged there."""
        name = self.names.get(family, self.package) if family else self.package
        return None if name is None else Dep(name, self.group, self.purpose, self.default)


ARCH_ONLY = {"fedora": None, "suse": None, "debian": None}


def all_dependencies() -> list[Dep]:
    return [
        Dep(
            "python-gobject",
            "required",
            _("Python bindings for GTK"),
            names={"fedora": "python3-gobject", "suse": "python3-gobject", "debian": "python3-gi"},
        ),
        Dep(
            "gtk4",
            "required",
            _("Interface toolkit"),
            names={"suse": "typelib-1_0-Gtk-4_0", "debian": "gir1.2-gtk-4.0"},
        ),
        Dep(
            "libadwaita",
            "required",
            _("GNOME widgets and styles (1.5 or newer)"),
            names={"suse": "typelib-1_0-Adw-1", "debian": "gir1.2-adw-1"},
        ),
        Dep("gettext", "required", _("Compiles the interface translations"), names={"suse": "gettext-tools"}),
        Dep(
            "libnm",
            "optional",
            _("Saves Wi-Fi passwords from the Connectivity page"),
            names={"fedora": "NetworkManager-libnm", "suse": "typelib-1_0-NM-1_0", "debian": "gir1.2-nm-1.0"},
        ),
        Dep("impala", "optional", _("Wi-Fi manager opened by the Connectivity page"), names=ARCH_ONLY),
        Dep("bluetui", "optional", _("Bluetooth manager opened by the Connectivity page"), names=ARCH_ONLY),
        Dep("wiremix", "optional", _("Audio mixer opened by the Sound page"), names=ARCH_ONLY),
        Dep(
            "waybar",
            "optional",
            _(
                "Alternative bar. Omarchy uses the Omarchy shell bar; installing Waybar "
                "doesn't start it or replace the current bar"
            ),
            default=False,
            omarchy_only=True,
        ),
        Dep(
            "python-pytest",
            "dev",
            _("Runs the project's tests"),
            default=False,
            names={"fedora": "python3-pytest", "suse": "python3-pytest", "debian": "python3-pytest"},
        ),
    ]


def dependencies(family: str | None = None) -> list[Dep]:
    """The dependencies with this system's package names (or those of family)."""
    family = distro.family() if family is None else family
    deps = [d.on(family) for d in all_dependencies() if host.is_omarchy() or not d.omarchy_only]
    return [d for d in deps if d is not None]


def group_title(group: str) -> str:
    return {"required": _("Required"), "optional": _("Optional"), "dev": _("Development")}[group]


def can_install() -> bool:
    """The dialog can install: the package manager is known and pkexec asks for the password."""
    return distro.manager() is not None and core.have("pkexec")


def missing(packages: list[str]) -> set[str]:
    """Packages that aren't installed; all of them when the package manager isn't known."""
    m = distro.manager()
    return m.missing(packages) if m else set(packages)


def install(packages: list[str]):
    """Installs with a graphical password prompt; can take minutes."""
    return core.run(install_command(packages), timeout=900)


def install_command(packages: list[str]) -> list[str]:
    """Installation with a graphical password prompt (polkit), for the UI."""
    m = distro.manager()
    if m is None:
        raise ValueError("unknown package manager")
    return m.install_command(packages)


def main(argv: list[str]) -> int:
    if "--install-command" in argv:  # for install.sh, which adds sudo and the packages
        m = distro.manager()
        print(" ".join(a for a in m.install if a not in ("-y", "--noconfirm", "--non-interactive")) if m else "")
        return 0
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
