"""Bluetooth through BlueZ's bluetoothctl (no GTK, testable).

Reading and simple commands run bluetoothctl once per call. Pairing needs an agent that can show or confirm a
code, so it runs one interactive bluetoothctl fed through stdin; PairParser turns its output into events.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import core

SCAN_SECONDS = 10
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|\x01|\x02")
MAC = re.compile(r"(?:[0-9A-F]{2}:){5}[0-9A-F]{2}", re.I)


@dataclass
class Device:
    mac: str
    name: str
    icon: str = ""  # BlueZ icon name, e.g. "audio-headset", "input-mouse"
    paired: bool = False
    trusted: bool = False
    connected: bool = False
    battery: int | None = None

    @property
    def kind(self) -> str:
        """audio, mouse, keyboard, gamepad, phone, computer or other."""
        icon = self.icon
        if icon.startswith("audio"):
            return "audio"
        return {
            "input-mouse": "mouse",
            "input-tablet": "mouse",
            "input-keyboard": "keyboard",
            "input-gaming": "gamepad",
            "phone": "phone",
            "computer": "computer",
        }.get(icon, "other")


KIND_ICONS = {
    "audio": "audio-headphones-symbolic",
    "mouse": "input-mouse-symbolic",
    "keyboard": "input-keyboard-symbolic",
    "gamepad": "input-gaming-symbolic",
    "phone": "phone-symbolic",
    "computer": "computer-symbolic",
    "other": "bluetooth-symbolic",
}


def clean(text: str) -> str:
    return ANSI.sub("", text)


# ------------------------------------------------------------------ reading
def powered() -> bool | None:
    """True/False, or None when there is no adapter (or no bluetoothctl)."""
    if not core.have("bluetoothctl"):
        return None
    text = clean(core.out(["bluetoothctl", "show"]))
    if "Controller" not in text:
        return None
    return "Powered: yes" in text


def set_power(on: bool) -> bool:
    r = core.run(["bluetoothctl", "power", "on" if on else "off"])
    return bool(r and r.returncode == 0)


def parse_info(mac: str, text: str) -> Device:
    fields: dict[str, str] = {}
    for line in clean(text).splitlines():
        key, sep, value = line.strip().partition(": ")
        if sep and key not in fields:
            fields[key] = value.strip()
    battery = re.search(r"\((\d+)\)", fields.get("Battery Percentage", ""))
    return Device(
        mac=mac,
        name=fields.get("Alias") or fields.get("Name") or mac,
        icon=fields.get("Icon", ""),
        paired=fields.get("Paired") == "yes",
        trusted=fields.get("Trusted") == "yes",
        connected=fields.get("Connected") == "yes",
        battery=int(battery.group(1)) if battery else None,
    )


def listed() -> list[tuple[str, str]]:
    """(mac, name) of every device BlueZ knows: paired ones and those seen by a recent scan."""
    result = []
    for line in clean(core.out(["bluetoothctl", "devices"])).splitlines():
        parts = line.strip().split(" ", 2)
        if len(parts) >= 2 and parts[0] == "Device" and MAC.fullmatch(parts[1]):
            result.append((parts[1], parts[2] if len(parts) > 2 else parts[1]))
    return result


def devices() -> list[Device]:
    """Every known device with its details; connected first, then paired, then by name."""
    found = [parse_info(mac, core.out(["bluetoothctl", "info", mac])) for mac, _name in listed()]
    return sorted(found, key=lambda d: (not d.connected, not d.paired, d.name.lower()))


def unnamed(d: Device) -> bool:
    """Devices that only advertise their address (BlueZ then names them like AA-BB-CC-...)."""
    return d.name == d.mac or d.name.replace("-", ":").upper() == d.mac.upper()


def scan(seconds: int = SCAN_SECONDS) -> list[Device]:
    """Searches for nearby devices; returns the unpaired ones that have a name."""
    core.run(["bluetoothctl", "--timeout", str(seconds), "scan", "on"], timeout=seconds + 5)
    return [d for d in devices() if not d.paired and not unnamed(d)]


# ------------------------------------------------------------------ commands
def connect(mac: str) -> list[str]:
    return ["bluetoothctl", "--timeout", "20", "connect", mac]


def disconnect(mac: str) -> list[str]:
    return ["bluetoothctl", "disconnect", mac]


def forget(mac: str) -> list[str]:
    return ["bluetoothctl", "remove", mac]


def run(args: list[str]) -> tuple[bool, str]:
    """(ok, error). bluetoothctl exits 0 on some failures, so its output is checked too."""
    r = core.run(args, timeout=30)
    if r is None:
        return False, "bluetoothctl"
    text = clean(r.stdout + r.stderr)
    failed = r.returncode != 0 or re.search(r"Failed to|not available|Error\.", text)
    return (False, failure_line(text)) if failed else (True, "")


def failure_line(text: str) -> str:
    for line in clean(text).splitlines():
        if "Failed" in line or "Error" in line or "not available" in line:
            return line.strip()
    return text.strip().splitlines()[-1] if text.strip() else ""


# ------------------------------------------------------------------ pairing
PAIR_START = "agent KeyboardDisplay\ndefault-agent\npair {mac}\n"
AFTER_PAIR = "trust {mac}\nconnect {mac}\n"


class PairParser:
    """Turns an interactive bluetoothctl's output into pairing events.

    feed() returns a list of events: ("show", code) a code to type on the device, ("confirm", code) a code to
    compare and confirm, ("input",) the device wants a PIN typed here (not supported: use bluetui),
    ("paired",), ("connected",), ("connect-failed",) paired but not connected, ("failed", reason).
    """

    def __init__(self):
        self.buffer = ""
        self.paired = False

    def feed(self, chunk: str) -> list[tuple]:
        self.buffer += clean(chunk)
        events = []
        while True:
            event, end = self._next()
            if event is None:
                break
            self.buffer = self.buffer[end:]
            events.append(event)
        return events

    PATTERNS = [
        ("confirm", re.compile(r"Confirm passkey (\d+)(?=\D)")),
        ("show", re.compile(r"Passkey: (\d+)(?=\D)")),
        ("show-pin", re.compile(r"PIN code: (\w+)(?=\W)")),
        ("input", re.compile(r"Enter (?:PIN code|passkey)")),
        ("paired", re.compile(r"Pairing successful")),
        ("connected", re.compile(r"Connection successful")),
        ("failed", re.compile(r"Failed to pair: (\S+)|Failed to connect: (\S+)|Device \S+ not available")),
    ]

    # codes must be followed by something else, so one split across two reads isn't cut short
    def _next(self) -> tuple[tuple | None, int]:
        best = None
        for name, pattern in self.PATTERNS:
            m = pattern.search(self.buffer)
            if m and (best is None or m.start() < best[1].start()):
                best = (name, m)
        if best is None:
            return None, 0
        name, m = best
        if name in ("confirm", "show"):
            return (name, m.group(1).zfill(6)), m.end()  # passkeys are always shown with 6 digits
        if name == "show-pin":
            return ("show", m.group(1)), m.end()
        if name == "failed":
            if self.paired and "connect" in m.group(0):
                return ("connect-failed",), m.end()
            return ("failed", failure_reason(m.group(0))), m.end()
        if name == "paired":
            self.paired = True
        return (name,), m.end()


def failure_reason(text: str) -> str:
    """not-found, rejected, timeout, already or "" (anything else)."""
    if "not available" in text or "DoesNotExist" in text:
        return "not-found"
    if "AuthenticationFailed" in text or "AuthenticationRejected" in text or "AuthenticationCanceled" in text:
        return "rejected"
    if "Timeout" in text or "AuthenticationTimeout" in text:
        return "timeout"
    if "AlreadyExists" in text:
        return "already"
    return ""
