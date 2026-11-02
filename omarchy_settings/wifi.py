"""Wi-Fi through NetworkManager's nmcli (no GTK, testable).

Listing, scanning, connecting to saved or open networks and forgetting go through nmcli. A new network with
a password is saved by the page through libnm instead, so the password never shows up in a command line;
nmcli then brings it up and reports why it failed (e.g. a wrong password).
"""

from __future__ import annotations

from dataclasses import dataclass

from . import core
from .network import parse_fields, split_terse

CONNECT_TIMEOUT = 25


@dataclass
class Network:
    ssid: str
    signal: int  # 0-100
    security: str  # nmcli text, e.g. "WPA2", "WPA1 WPA2", "WPA3", "" for open
    in_use: bool = False
    frequency: str = ""

    @property
    def kind(self) -> str:
        return security_kind(self.security)


@dataclass
class Saved:
    uuid: str
    name: str
    ssid: str
    autoconnect: bool = True
    active: bool = False


def security_kind(security: str) -> str:
    """open, psk (WPA/WPA2 personal), sae (WPA3 personal), enterprise (802.1X) or owe (enhanced open)."""
    s = security.upper()
    if "802.1X" in s:
        return "enterprise"
    if "WPA3" in s and "WPA2" not in s and "WPA1" not in s:
        return "sae"  # WPA3-only; mixed WPA2/WPA3 networks also accept WPA2
    if "WPA" in s or "WEP" in s:
        return "psk"
    if "OWE" in s:
        return "owe"
    return "open"


def signal_icon(signal: int) -> str:
    level = "excellent" if signal >= 75 else "good" if signal >= 50 else "ok" if signal >= 25 else "weak"
    return f"network-wireless-signal-{level}-symbolic"


# ------------------------------------------------------------------ reading
def radio_enabled() -> bool:
    return core.out(["nmcli", "radio", "wifi"]) == "enabled"


def set_radio(on: bool) -> bool:
    r = core.run(["nmcli", "radio", "wifi", "on" if on else "off"])
    return bool(r and r.returncode == 0)


def device() -> tuple[str, str] | None:
    """(name, state) of the first Wi-Fi device."""
    for line in core.out(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE", "device", "status"]).splitlines():
        parts = split_terse(line)
        if len(parts) >= 3 and parts[1] == "wifi":
            return parts[0], parts[2]
    return None


def scan(rescan: bool = False) -> list[Network]:
    """Visible networks, one per SSID (the strongest access point), hidden ones left out; in use first."""
    out = core.out(
        [
            "nmcli",
            "-t",
            "-f",
            "IN-USE,SSID,SIGNAL,SECURITY,FREQ",
            "device",
            "wifi",
            "list",
            "--rescan",
            "yes" if rescan else "no",
        ],
        timeout=30,
    )
    best: dict[str, Network] = {}
    for line in out.splitlines():
        parts = split_terse(line)
        if len(parts) < 5 or not parts[1]:
            continue
        net = Network(
            ssid=parts[1],
            signal=int(parts[2]) if parts[2].isdigit() else 0,
            security="" if parts[3] in ("", "--") else parts[3],
            in_use=parts[0] == "*",
            frequency=parts[4],
        )
        old = best.get(net.ssid)
        if old is None or net.in_use or (not old.in_use and net.signal > old.signal):
            best[net.ssid] = net
    return sorted(best.values(), key=lambda n: (not n.in_use, -n.signal, n.ssid.lower()))


def saved() -> list[Saved]:
    result = []
    for line in core.out(["nmcli", "-t", "-f", "UUID,NAME,TYPE,AUTOCONNECT,DEVICE", "connection", "show"]).splitlines():
        parts = split_terse(line)
        if len(parts) < 5 or parts[2] != "802-11-wireless":
            continue
        fields = parse_fields(
            core.out(["nmcli", "-t", "-f", "802-11-wireless.ssid", "connection", "show", "uuid", parts[0]])
        )
        ssid = (fields.get("802-11-wireless.ssid") or [parts[1]])[0]
        result.append(Saved(parts[0], parts[1], ssid, parts[3] == "yes", bool(parts[4])))
    return sorted(result, key=lambda s: (not s.active, s.ssid.lower()))


# ------------------------------------------------------------------ commands
def connect_saved(uuid: str, iface: str) -> list[str]:
    return ["nmcli", "--wait", str(CONNECT_TIMEOUT), "connection", "up", "uuid", uuid, "ifname", iface]


def connect_open(ssid: str, iface: str) -> list[str]:
    return ["nmcli", "--wait", str(CONNECT_TIMEOUT), "device", "wifi", "connect", ssid, "ifname", iface]


def forget(uuid: str) -> list[str]:
    return ["nmcli", "connection", "delete", "uuid", uuid]


def failure_reason(error: str) -> str:
    """wrong-password, not-found, unavailable or "" (anything else), from nmcli's error text."""
    e = error.lower()
    if "device is not available" in e or "radio" in e:
        return "unavailable"
    if "secrets were required" in e or "802-1x supplicant" in e or "psk" in e or "password" in e:
        return "wrong-password"
    if "no network with ssid" in e or "not found" in e:
        return "not-found"
    return ""


def connection_info(iface: str) -> dict[str, list[str]]:
    """nmcli fields of the device: GENERAL.CONNECTION and IP4.ADDRESS."""
    return parse_fields(core.out(["nmcli", "-t", "-f", "GENERAL.CONNECTION,IP4.ADDRESS", "device", "show", iface]))


def run(args: list[str]):
    return core.run(args, timeout=30)
