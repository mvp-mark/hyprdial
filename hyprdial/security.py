"""Security setups (no GTK, testable): fingerprint, FIDO2 key and SSH server, as Omarchy's Setup and Remove menus
offer them, with the same conditions. Every setup runs in a visible terminal, since they ask for the password."""

from __future__ import annotations

from dataclasses import dataclass

from . import core
from .power import TERMINAL

ITEMS = ("fingerprint", "fido2", "sshd")


def ok(args: list[str]) -> bool:
    r = core.run(args)
    return bool(r and r.returncode == 0)


@dataclass
class State:
    key: str
    configured: bool
    detail: str = ""  # sshd: "active"/"inactive"


def states() -> list[State]:
    """The setups this computer can use, as Omarchy's menu decides it."""
    found = []
    if ok(["omarchy-hw-fingerprint"]):  # a fingerprint reader is present
        found.append(State("fingerprint", ok(["omarchy-pkg-present", "fprintd"])))
    found.append(State("fido2", ok(["omarchy-pkg-present", "pam-u2f"])))
    found.append(
        State("sshd", ok(["systemctl", "is-enabled", "--quiet", "sshd"]), core.out(["systemctl", "is-active", "sshd"]))
    )
    return found


def command(key: str, remove: bool = False) -> list[str]:
    script = f"omarchy-remove-security-{key}" if remove else f"omarchy-setup-security-{key}"
    return [TERMINAL, script]
