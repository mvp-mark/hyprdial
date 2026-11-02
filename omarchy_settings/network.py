"""Wired (Ethernet) connections through NetworkManager's nmcli (no GTK, testable).

Device state comes from `nmcli device`, link speed and carrier from /sys/class/net. Settings are stored in the
NetworkManager profile the device uses (or would use); a profile is created only when the device has none.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field
from pathlib import Path

from . import core

SYS_NET = Path("/sys/class/net")
CONNECT_TIMEOUT = 20  # seconds nmcli waits for an activation


@dataclass
class Wired:
    device: str
    state: str  # nmcli state text, e.g. "connected", "disconnected", "unavailable"
    connection: str = ""
    carrier: bool = False
    speed: int | None = None  # Mb/s
    mac: str = ""
    addresses: list[str] = field(default_factory=list)
    gateway: str = ""
    dns: list[str] = field(default_factory=list)

    @property
    def connected(self) -> bool:
        return self.state.startswith("connected")

    @property
    def connecting(self) -> bool:
        return self.state.startswith("connecting")


@dataclass
class Profile:
    uuid: str
    name: str
    method: str = "auto"  # "auto" (DHCP) or "manual"
    addresses: list[str] = field(default_factory=list)
    gateway: str = ""
    dns: list[str] = field(default_factory=list)
    autoconnect: bool = True


# ------------------------------------------------------------------ reading nmcli
def split_terse(line: str) -> list[str]:
    """Splits an `nmcli -t` line on unescaped ':' and removes the escapes (MACs come as AA\\:BB...)."""
    fields, current, i = [], [], 0
    while i < len(line):
        c = line[i]
        if c == "\\" and i + 1 < len(line):
            current.append(line[i + 1])
            i += 2
            continue
        if c == ":":
            fields.append("".join(current))
            current = []
        else:
            current.append(c)
        i += 1
    fields.append("".join(current))
    return fields


def parse_fields(text: str) -> dict[str, list[str]]:
    """`nmcli -t -f ... show` output ("KEY:value" per line, KEY[n] for lists) -> {KEY: [values]}."""
    result: dict[str, list[str]] = {}
    for line in text.splitlines():
        key, sep, value = line.partition(":")
        if not sep:
            continue
        key = key.split("[", 1)[0]
        if value:
            result.setdefault(key, []).append(value.replace("\\:", ":"))
        else:
            result.setdefault(key, [])
    return result


def _first(fields: dict, key: str) -> str:
    values = fields.get(key) or [""]
    return values[0]


def _split_list(values: list[str]) -> list[str]:
    return [v.strip() for value in values for v in value.split(",") if v.strip()]


def _read_sys(device: str, name: str) -> str:
    try:
        return (SYS_NET / device / name).read_text().strip()
    except OSError:
        return ""


def wired_devices() -> list[Wired]:
    devices = []
    for line in core.out(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device", "status"]).splitlines():
        parts = split_terse(line)
        if len(parts) < 4 or parts[1] != "ethernet":
            continue
        name = parts[0]
        info = parse_fields(
            core.out(["nmcli", "-t", "-f", "GENERAL.HWADDR,IP4.ADDRESS,IP4.GATEWAY,IP4.DNS", "device", "show", name])
        )
        speed = _read_sys(name, "speed")
        devices.append(
            Wired(
                device=name,
                state=parts[2],
                connection=parts[3],
                carrier=_read_sys(name, "carrier") == "1",
                speed=int(speed) if speed.lstrip("-").isdigit() and int(speed) > 0 else None,
                mac=_first(info, "GENERAL.HWADDR"),
                addresses=info.get("IP4.ADDRESS", []),
                gateway=_first(info, "IP4.GATEWAY"),
                dns=info.get("IP4.DNS", []),
            )
        )
    return devices


def read_profile(uuid: str) -> Profile | None:
    fields = parse_fields(
        core.out(
            [
                "nmcli",
                "-t",
                "-f",
                "connection.uuid,connection.id,connection.autoconnect,ipv4.method,ipv4.addresses,ipv4.gateway,ipv4.dns",
                "connection",
                "show",
                "uuid",
                uuid,
            ]
        )
    )
    if not _first(fields, "connection.uuid"):
        return None
    return Profile(
        uuid=_first(fields, "connection.uuid"),
        name=_first(fields, "connection.id"),
        method=_first(fields, "ipv4.method") or "auto",
        addresses=_split_list(fields.get("ipv4.addresses", [])),
        gateway=_first(fields, "ipv4.gateway"),
        dns=_split_list(fields.get("ipv4.dns", [])),
        autoconnect=_first(fields, "connection.autoconnect") != "no",
    )


def profile_for(device: str) -> Profile | None:
    """The profile in use on the device, else an Ethernet profile bound to it, else one bound to no device."""
    candidates = []
    for line in core.out(["nmcli", "-t", "-f", "UUID,TYPE,DEVICE", "connection", "show"]).splitlines():
        parts = split_terse(line)
        if len(parts) >= 3 and parts[1] == "802-3-ethernet":
            if parts[2] == device:
                return read_profile(parts[0])
            candidates.append(parts[0])
    unbound = None
    for uuid in candidates:
        bound = _first(
            parse_fields(
                core.out(["nmcli", "-t", "-f", "connection.interface-name", "connection", "show", "uuid", uuid])
            ),
            "connection.interface-name",
        )
        if bound == device:
            return read_profile(uuid)
        if not bound and unbound is None:
            unbound = uuid
    return read_profile(unbound) if unbound else None


# ------------------------------------------------------------------ settings
class InvalidSettings(ValueError):
    """field is "address", "gateway" or "dns"."""

    def __init__(self, field_name: str, value: str):
        super().__init__(f"{field_name}: {value}")
        self.field = field_name
        self.value = value


def normalize(method: str, address: str, gateway: str, dns: str) -> dict:
    """Validates the form and returns {"method", "address", "gateway", "dns": [..]} ready for nmcli."""
    dns_list = [d.strip() for d in dns.replace(";", ",").replace(" ", ",").split(",") if d.strip()]
    for d in dns_list:
        try:
            ipaddress.ip_address(d)
        except ValueError:
            raise InvalidSettings("dns", d) from None
    if method == "auto":
        return {"method": "auto", "address": "", "gateway": "", "dns": dns_list}

    address = address.strip()
    if "/" not in address:
        address += "/24"  # the most common home network size when no prefix is given
    try:
        iface = ipaddress.IPv4Interface(address)
    except ValueError:
        raise InvalidSettings("address", address) from None
    if iface.ip == iface.network.network_address and iface.network.prefixlen < 31:
        raise InvalidSettings("address", address)
    gateway = gateway.strip()
    if gateway:
        try:
            gw = ipaddress.IPv4Address(gateway)
        except ValueError:
            raise InvalidSettings("gateway", gateway) from None
        if gw not in iface.network or gw == iface.ip:
            raise InvalidSettings("gateway", gateway)
    return {"method": "manual", "address": str(iface), "gateway": gateway, "dns": dns_list}


def settings_args(settings: dict, autoconnect: bool) -> list[str]:
    args = [
        "connection.autoconnect",
        "yes" if autoconnect else "no",
        "ipv4.method",
        settings["method"],
        "ipv4.addresses",
        settings["address"],
        "ipv4.gateway",
        settings["gateway"],
        "ipv4.dns",
        ",".join(settings["dns"]),
    ]
    # custom DNS replaces the one from DHCP; without custom DNS, use the network's
    args += ["ipv4.ignore-auto-dns", "yes" if settings["dns"] else "no"]
    return args


def save_commands(device: str, profile: Profile | None, settings: dict, autoconnect: bool) -> list[list[str]]:
    """Commands that store the settings and bring the connection up with them."""
    if profile is None:
        name = f"Wired connection ({device})"
        return [
            [
                "nmcli",
                "connection",
                "add",
                "type",
                "ethernet",
                "ifname",
                device,
                "con-name",
                name,
                *settings_args(settings, autoconnect),
            ],
            ["nmcli", "--wait", str(CONNECT_TIMEOUT), "connection", "up", "id", name, "ifname", device],
        ]
    return [
        ["nmcli", "connection", "modify", "uuid", profile.uuid, *settings_args(settings, autoconnect)],
        ["nmcli", "--wait", str(CONNECT_TIMEOUT), "connection", "up", "uuid", profile.uuid, "ifname", device],
    ]


def run_all(commands: list[list[str]]) -> tuple[bool, str, int]:
    """Runs the commands in order; stops at the first failure. Returns (ok, error, index of the failure)."""
    for index, cmd in enumerate(commands):
        r = core.run(cmd, timeout=CONNECT_TIMEOUT + 10)
        if r is None:
            return False, "nmcli not found", index
        if r.returncode != 0:
            text = (r.stderr or r.stdout).strip().splitlines()
            return False, text[-1] if text else str(r.returncode), index
    return True, "", -1


def connect(device: str) -> tuple[bool, str, int]:
    return run_all([["nmcli", "--wait", str(CONNECT_TIMEOUT), "device", "connect", device]])


def disconnect(device: str) -> tuple[bool, str, int]:
    return run_all([["nmcli", "device", "disconnect", device]])


# ------------------------------------------------------------------ diagnosis
def diagnosis(w: Wired) -> str:
    """What is wrong, or "": no-cable, slow-link (a gigabit port stuck at 10 Mb/s: usually a bad cable or port)
    or no-address (cable present, but no address yet; it keeps retrying, so 'connecting' counts too)."""
    if not w.carrier:
        return "no-cable"
    if w.speed is not None and w.speed <= 10:
        return "slow-link"
    if not w.connected:
        return "no-address"
    return ""
