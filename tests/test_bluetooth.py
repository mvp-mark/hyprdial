import subprocess

import pytest

from hyprdial import bluetooth as bt
from hyprdial import core

MOUSE = "AA:BB:CC:DD:EE:01"
PHONE = "AA:BB:CC:DD:EE:02"
ANON = "AA:BB:CC:DD:EE:03"

INFO_MOUSE = """Device AA:BB:CC:DD:EE:01 (random)
\tName: MX Master 3
\tAlias: MX Master 3
\tIcon: input-mouse
\tPaired: yes
\tTrusted: yes
\tConnected: yes
\tBattery Percentage: 0x55 (85)
"""


@pytest.fixture
def btctl(monkeypatch):
    """Fake bluetoothctl: answers from a dict keyed by the joined arguments."""
    answers: dict[str, str] = {}
    calls: list[list[str]] = []

    def fake_run(args, timeout=10):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, answers.get(" ".join(args), ""), "")

    monkeypatch.setattr(core, "out", lambda args, timeout=10: answers.get(" ".join(args), "").strip())
    monkeypatch.setattr(core, "run", fake_run)
    monkeypatch.setattr(core, "have", lambda cmd: True)
    return answers, calls


def test_powered_and_missing_adapter(btctl):
    answers, _calls = btctl
    answers["bluetoothctl show"] = "Controller E0:D4:E8:74:63:FE (public)\n\tPowered: yes\n"
    assert bt.powered() is True
    answers["bluetoothctl show"] = "No default controller available"
    assert bt.powered() is None


def test_parse_info_reads_battery_and_kind():
    d = bt.parse_info(MOUSE, "\x1b[0;94m" + INFO_MOUSE + "\x1b[0m")
    assert (d.name, d.paired, d.connected, d.battery, d.kind) == ("MX Master 3", True, True, 85, "mouse")


@pytest.mark.parametrize(
    "icon, kind",
    [
        ("audio-headset", "audio"),
        ("audio-card", "audio"),
        ("input-keyboard", "keyboard"),
        ("input-gaming", "gamepad"),
        ("phone", "phone"),
        ("", "other"),
    ],
)
def test_kind(icon, kind):
    assert bt.Device("m", "n", icon=icon).kind == kind


def test_devices_sorted_and_scan_skips_paired_and_unnamed(btctl):
    answers, calls = btctl
    answers["bluetoothctl devices"] = (
        f"Device {PHONE} Pixel\nDevice {MOUSE} MX Master 3\nDevice {ANON} AA-BB-CC-DD-EE-03\nnot a device line\n"
    )
    answers[f"bluetoothctl info {MOUSE}"] = INFO_MOUSE
    answers[f"bluetoothctl info {PHONE}"] = f"Device {PHONE}\n\tName: Pixel\n\tIcon: phone\n\tPaired: no\n"
    answers[f"bluetoothctl info {ANON}"] = f"Device {ANON}\n\tName: AA-BB-CC-DD-EE-03\n\tPaired: no\n"
    assert [d.name for d in bt.devices()] == ["MX Master 3", "AA-BB-CC-DD-EE-03", "Pixel"]
    assert [d.mac for d in bt.scan(5)] == [PHONE]
    assert ["bluetoothctl", "--timeout", "5", "scan", "on"] in calls


def test_run_detects_failure_despite_exit_zero(btctl):
    answers, _calls = btctl
    answers[f"bluetoothctl --timeout 20 connect {MOUSE}"] = (
        f"Attempting to connect to {MOUSE}\nFailed to connect: org.bluez.Error.Failed br-connection-page-timeout\n"
    )
    ok, error = bt.run(bt.connect(MOUSE))
    assert not ok and error.startswith("Failed to connect")
    answers[f"bluetoothctl disconnect {MOUSE}"] = "Attempting to disconnect\nSuccessful disconnected\n"
    assert bt.run(bt.disconnect(MOUSE)) == (True, "")


def test_power_goes_through_omarchy(btctl):
    _answers, calls = btctl
    assert bt.set_power(True)
    assert calls == [["omarchy-bluetooth-power", "on"]]


def test_device_action_checks_the_result(btctl):
    answers, calls = btctl
    answers[f"bluetoothctl info {MOUSE}"] = INFO_MOUSE
    assert bt.device_action("connect", MOUSE) == (True, "")
    assert calls[0] == ["omarchy-bluetooth-device", "connect", MOUSE]
    assert bt.device_action("disconnect", MOUSE) == (False, "no-change")  # still connected
    answers[f"bluetoothctl info {MOUSE}"] = f"Device {MOUSE} not available"
    assert bt.device_action("forget", MOUSE) == (True, "")


def feed_all(parser, *chunks):
    events = []
    for chunk in chunks:
        events += parser.feed(chunk)
    return events


def test_pair_parser_just_works_then_connect():
    p = bt.PairParser()
    events = feed_all(
        p,
        "Agent registered\n[\x1b[0;93mCHG\x1b[0m] Device AA Connected: yes\n",
        "Pairing succ",
        "essful\n",
        "Connection successful\n",
    )
    assert events == [("paired",), ("connected",)]


def test_pair_parser_codes_split_across_reads():
    p = bt.PairParser()
    assert feed_all(p, "[agent] Confirm passkey 0", "12345 (yes/no): ") == [("confirm", "012345")]
    assert p.feed("[agent] Passkey: 4321\n") == [("show", "004321")]
    assert p.feed("[agent] PIN code: 0000\n") == [("show", "0000")]
    assert p.feed("[agent] Enter PIN code: ") == [("input",)]


def test_pair_parser_failures():
    p = bt.PairParser()
    assert p.feed("Failed to pair: org.bluez.Error.AuthenticationFailed\n") == [("failed", "rejected")]
    assert bt.PairParser().feed(f"Device {MOUSE} not available\n") == [("failed", "not-found")]
    paired = bt.PairParser()
    assert paired.feed("Pairing successful\nFailed to connect: org.bluez.Error.Failed\n") == [
        ("paired",),
        ("connect-failed",),
    ]
