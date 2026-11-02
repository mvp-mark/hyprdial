import subprocess

import pytest

from omarchy_settings import core, wifi


@pytest.fixture
def nmcli(monkeypatch):
    answers: dict[str, str] = {}
    monkeypatch.setattr(core, "out", lambda args, timeout=10: answers.get(" ".join(args), ""))
    return answers


SCAN = "nmcli -t -f IN-USE,SSID,SIGNAL,SECURITY,FREQ device wifi list --rescan no"


@pytest.mark.parametrize(
    "security, kind",
    [
        ("", "open"),
        ("--", "open"),
        ("WPA2", "psk"),
        ("WPA1 WPA2", "psk"),
        ("WPA2 WPA3", "psk"),
        ("WPA3", "sae"),
        ("WPA2 802.1X", "enterprise"),
        ("OWE", "owe"),
        ("WEP", "psk"),
    ],
)
def test_security_kind(security, kind):
    assert wifi.security_kind(security) == kind


def test_signal_icon_levels():
    assert [wifi.signal_icon(s).split("-")[3] for s in (90, 60, 30, 5)] == ["excellent", "good", "ok", "weak"]


def test_scan_keeps_strongest_per_ssid_and_skips_hidden(nmcli):
    nmcli[SCAN] = "\n".join(
        [
            " :Neighbor:40:WPA2:2437 MHz",
            " :Neighbor:70:WPA2:5180 MHz",  # same SSID, stronger access point
            "*:Home\\:5G:50:WPA2:5200 MHz",  # in use; ':' escaped in the SSID
            " ::90:WPA2:2412 MHz",  # hidden network (no SSID)
            " :Cafe:80:--:2462 MHz",
        ]
    )
    nets = wifi.scan()
    assert [n.ssid for n in nets] == ["Home:5G", "Cafe", "Neighbor"]
    assert nets[0].in_use and nets[2].signal == 70 and nets[1].kind == "open"


def test_in_use_access_point_wins_even_if_weaker(nmcli):
    nmcli[SCAN] = " :Home:90:WPA2:5180 MHz\n*:Home:30:WPA2:2437 MHz"
    (home,) = wifi.scan()
    assert home.in_use and home.signal == 30


def test_saved_reads_ssid_of_each_profile(nmcli):
    nmcli["nmcli -t -f UUID,NAME,TYPE,AUTOCONNECT,DEVICE connection show"] = "\n".join(
        ["u1:Home 1:802-11-wireless:yes:wlan0", "u2:Office:802-11-wireless:no:", "u3:Wired:802-3-ethernet:yes:enp6s0"]
    )
    nmcli["nmcli -t -f 802-11-wireless.ssid connection show uuid u1"] = "802-11-wireless.ssid:Home"
    nmcli["nmcli -t -f 802-11-wireless.ssid connection show uuid u2"] = "802-11-wireless.ssid:Office"
    saved = wifi.saved()
    assert [(s.uuid, s.ssid, s.autoconnect, s.active) for s in saved] == [
        ("u1", "Home", True, True),
        ("u2", "Office", False, False),
    ]


def test_device_and_radio(nmcli):
    nmcli["nmcli -t -f DEVICE,TYPE,STATE device status"] = "enp6s0:ethernet:connected\nwlan0:wifi:unavailable"
    nmcli["nmcli radio wifi"] = "disabled"
    assert wifi.device() == ("wlan0", "unavailable") and not wifi.radio_enabled()


def test_commands():
    assert wifi.connect_saved("u1", "wlan0") == [
        "nmcli",
        "--wait",
        "25",
        "connection",
        "up",
        "uuid",
        "u1",
        "ifname",
        "wlan0",
    ]
    assert wifi.connect_open("Cafe", "wlan0")[-4:] == ["connect", "Cafe", "ifname", "wlan0"]
    assert wifi.forget("u1") == ["nmcli", "connection", "delete", "uuid", "u1"]


def test_set_radio(monkeypatch):
    calls = []
    monkeypatch.setattr(
        core, "run", lambda args, timeout=10: calls.append(args) or subprocess.CompletedProcess(args, 0, "", "")
    )
    assert wifi.set_radio(True) and calls == [["nmcli", "radio", "wifi", "on"]]


@pytest.mark.parametrize(
    "error, reason",
    [
        ("Error: Connection activation failed: Secrets were required, but not provided.", "wrong-password"),
        ("Error: No network with SSID 'X' found.", "not-found"),
        ("Error: Connection activation failed: IP configuration could not be reserved.", ""),
        ("Error: Connection 'X' is not available on device wlan0 because device is not available", "unavailable"),
    ],
)
def test_failure_reason(error, reason):
    assert wifi.failure_reason(error) == reason
