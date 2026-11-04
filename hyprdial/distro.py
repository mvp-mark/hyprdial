"""Which Linux distribution this is and how it installs packages (no GTK, testable).

Families come from /etc/os-release (ID and ID_LIKE): arch, fedora, suse and debian. Each has a package manager
that checks what is missing and installs with a graphical password prompt (pkexec), or with sudo from install.sh.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from . import core

OS_RELEASE = Path("/etc/os-release")
FAMILY_IDS = {
    "arch": "arch",
    "fedora": "fedora",
    "rhel": "fedora",
    "centos": "fedora",
    "suse": "suse",
    "opensuse": "suse",
    "debian": "debian",
    "ubuntu": "debian",
}

_family: str | None | bool = False  # False: not read yet


def os_release(path: Path = OS_RELEASE) -> dict[str, str]:
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return {}
    fields = {}
    for line in text.splitlines():
        m = re.fullmatch(r"([A-Z_]+)=(.*)", line.strip())
        if m:
            fields[m.group(1)] = m.group(2).strip().strip("\"'")
    return fields


def family_of(fields: dict[str, str]) -> str | None:
    """'arch' for Arch, CachyOS, EndeavourOS…; 'suse' for opensuse-tumbleweed; None when it isn't known."""
    for ident in [fields.get("ID", ""), *fields.get("ID_LIKE", "").split()]:
        ident = ident.lower()
        if ident in FAMILY_IDS:
            return FAMILY_IDS[ident]
        if ident.startswith("opensuse"):
            return "suse"
    return None


def family() -> str | None:
    """This system's family, read once per run."""
    global _family
    if _family is False:
        _family = family_of(os_release())
    return _family


# ------------------------------------------------------------------ package managers
@dataclass(frozen=True)
class Manager:
    name: str
    install: tuple[str, ...]  # without "sudo"/"pkexec" and the packages
    remove: tuple[str, ...]

    def missing(self, packages: list[str]) -> set[str]:
        if not packages:
            return set()
        if self.name == "pacman":  # pacman -T lists only the missing ones
            r = core.run(["pacman", "-T", *packages])
            return set(packages) if r is None else {line.strip() for line in r.stdout.splitlines() if line.strip()}
        if self.name == "apt-get":
            r = core.run(["dpkg-query", "-W", "-f=${Package} ${Status}\\n", *packages])
            out = r.stdout if r else ""
            installed = {line.split()[0] for line in out.splitlines() if line.endswith(" installed")}
            return set(packages) - installed
        # rpm: capabilities too (python3-gobject is provided by python3.13-gobject…)
        r = core.run(["rpm", "-q", "--whatprovides", *packages])
        if r is None:
            return set(packages)
        return set(re.findall(r"^no package provides (\S+)$", r.stdout + r.stderr, re.MULTILINE)) & set(packages)

    def installed(self, package: str) -> bool:
        return not self.missing([package])

    def install_command(self, packages: list[str]) -> list[str]:
        """With a graphical password prompt (polkit), for the window."""
        return ["pkexec", *self.install, *packages]


MANAGERS = {
    "arch": Manager("pacman", ("pacman", "-S", "--needed", "--noconfirm"), ("pacman", "-R")),
    "fedora": Manager("dnf", ("dnf", "install", "-y"), ("dnf", "remove")),
    "suse": Manager("zypper", ("zypper", "--non-interactive", "install"), ("zypper", "remove")),
    "debian": Manager("apt-get", ("apt-get", "install", "-y"), ("apt-get", "remove")),
}


def manager(fam: str | None = None) -> Manager | None:
    """The package manager of this system (or of fam), when it is known and installed."""
    m = MANAGERS.get(fam if fam is not None else family() or "")
    return m if m and core.have(m.install[0]) else None
