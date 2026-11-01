import subprocess

import pytest

from omarchy_settings import core
from omarchy_settings import network as net


@pytest.fixture
def nmcli(monkeypatch, tmp_path):
    """Fake nmcli: answers from a dict keyed by the joined arguments; fake /sys/class/net in tmp_path."""
    answers: dict[str, str] = {}
    calls: list[list[str]] = []

    def fake_out(args, timeout=10):
        return answers.get(" ".join(args), "")

    def fake_run(args, timeout=10):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(core, "out", fake_out)
    monkeypatch.setattr(core, "run", fake_run)
    monkeypatch.setattr(net, "SYS_NET", tmp_path)
    return answers, calls, tmp_path


def sys_link(root, device, carrier="1", speed="1000"):
    (root / device).mkdir()
    (root / device / "carrier").write_text(carrier + "\n")
    (root / device / "speed").write_text(speed + "\n")


def test_split_terse_unescapes_colons():
    assert net.split_terse(r"enp6s0:ethernet:connected:Wired connection 1") == \
        ["enp6s0", "ethernet", "connected", "Wired connection 1"]
    assert net.split_terse(r"AA\:BB\:CC:x") == ["AA:BB:CC", "x"]


def test_parse_fields_lists_and_empty_values():
    fields = net.parse_fields("IP4.ADDRESS[1]:10.0.0.2/24\nIP4.DNS[1]:1.1.1.1\nIP4.DNS[2]:8.8.8.8\nIP4.GATEWAY:\n")
    assert fields == {"IP4.ADDRESS": ["10.0.0.2/24"], "IP4.DNS": ["1.1.1.1", "8.8.8.8"], "IP4.GATEWAY": []}


def test_wired_devices_reads_nmcli_and_sysfs(nmcli):
    answers, _calls, root = nmcli
    answers["nmcli -t -f DEVICE,TYPE,STATE,CONNECTION device status"] = (
        "wlan0:wifi:connected:Home\nenp6s0:ethernet:connecting (getting IP configuration):Wired connection 1\n")
    answers["nmcli -t -f GENERAL.HWADDR,IP4.ADDRESS,IP4.GATEWAY,IP4.DNS device show enp6s0"] = (
        "GENERAL.HWADDR:18:C0:4D:08:9A:8C\nIP4.GATEWAY:\n")
    sys_link(root, "enp6s0", speed="10")
    (w,) = net.wired_devices()
    assert (w.device, w.carrier, w.speed, w.mac) == ("enp6s0", True, 10, "18:C0:4D:08:9A:8C")
    assert w.connecting and not w.connected and w.connection == "Wired connection 1"


def test_unknown_speed_is_none(nmcli):
    answers, _calls, root = nmcli
    answers["nmcli -t -f DEVICE,TYPE,STATE,CONNECTION device status"] = "eth0:ethernet:unavailable:\n"
    sys_link(root, "eth0", carrier="0", speed="-1")
    (w,) = net.wired_devices()
    assert w.speed is None and not w.carrier


@pytest.mark.parametrize("w, code", [
    (net.Wired("e", "unavailable", carrier=False), "no-cable"),
    (net.Wired("e", "connecting (getting IP configuration)", carrier=True, speed=10), "slow-link"),
    (net.Wired("e", "connected", carrier=True, speed=10), "slow-link"),
    (net.Wired("e", "connecting (getting IP configuration)", carrier=True, speed=1000), "no-address"),
    (net.Wired("e", "disconnected", carrier=True, speed=1000), "no-address"),
    (net.Wired("e", "connected", carrier=True, speed=1000), ""),
])
def test_diagnosis(w, code):
    assert net.diagnosis(w) == code


def test_profile_for_prefers_active_then_bound_then_unbound(nmcli):
    answers, _calls, _root = nmcli
    answers["nmcli -t -f UUID,TYPE,DEVICE connection show"] = (
        "u-wifi:802-11-wireless:wlan0\nu-free:802-3-ethernet:\nu-bound:802-3-ethernet:\n")
    answers["nmcli -t -f connection.interface-name connection show uuid u-free"] = "connection.interface-name:\n"
    answers["nmcli -t -f connection.interface-name connection show uuid u-bound"] = "connection.interface-name:enp6s0\n"
    for uuid in ("u-free", "u-bound"):
        answers["nmcli -t -f connection.uuid,connection.id,connection.autoconnect,ipv4.method,ipv4.addresses,"
                f"ipv4.gateway,ipv4.dns connection show uuid {uuid}"] = (
            f"connection.uuid:{uuid}\nconnection.id:{uuid}\nconnection.autoconnect:yes\nipv4.method:manual\n"
            "ipv4.addresses:10.0.0.5/24\nipv4.gateway:10.0.0.1\nipv4.dns:1.1.1.1,9.9.9.9\n")
    p = net.profile_for("enp6s0")
    assert p.uuid == "u-bound" and p.dns == ["1.1.1.1", "9.9.9.9"] and p.method == "manual"
    assert net.profile_for("eth9").uuid == "u-free"  # an unbound profile works for any port


def test_profile_for_without_profiles(nmcli):
    assert net.profile_for("enp6s0") is None


def test_normalize_auto_and_dns():
    assert net.normalize("auto", "ignored", "ignored", "1.1.1.1; 8.8.8.8 9.9.9.9") == \
        {"method": "auto", "address": "", "gateway": "", "dns": ["1.1.1.1", "8.8.8.8", "9.9.9.9"]}


def test_normalize_manual_adds_prefix():
    assert net.normalize("manual", "192.168.1.50", "192.168.1.1", "") == \
        {"method": "manual", "address": "192.168.1.50/24", "gateway": "192.168.1.1", "dns": []}


@pytest.mark.parametrize("address, gateway, dns, field_name", [
    ("192.168.1.300/24", "", "", "address"),
    ("192.168.1.0/24", "", "", "address"),      # network address, not a host
    ("192.168.1.50/24", "10.0.0.1", "", "gateway"),  # outside the network
    ("192.168.1.50/24", "192.168.1.50", "", "gateway"),  # same as the address
    ("192.168.1.50/24", "192.168.1.1", "dns.google", "dns"),
])
def test_normalize_rejects(address, gateway, dns, field_name):
    with pytest.raises(net.InvalidSettings) as err:
        net.normalize("manual", address, gateway, dns)
    assert err.value.field == field_name


def test_save_commands_modify_existing_profile():
    p = net.Profile(uuid="u1", name="Wired connection 1")
    modify, up = net.save_commands("enp6s0", p, net.normalize("auto", "", "", ""), True)
    assert modify[:5] == ["nmcli", "connection", "modify", "uuid", "u1"]
    assert modify[modify.index("ipv4.ignore-auto-dns") + 1] == "no"
    assert up == ["nmcli", "--wait", "20", "connection", "up", "uuid", "u1", "ifname", "enp6s0"]


def test_save_commands_create_profile_with_custom_dns():
    add, up = net.save_commands("enp6s0", None, net.normalize("manual", "10.0.0.5/8", "10.0.0.1", "1.1.1.1"), False)
    assert add[:9] == ["nmcli", "connection", "add", "type", "ethernet", "ifname", "enp6s0", "con-name",
                       "Wired connection (enp6s0)"]
    args = dict(zip(add[9::2], add[10::2]))
    assert args == {"connection.autoconnect": "no", "ipv4.method": "manual", "ipv4.addresses": "10.0.0.5/8",
                    "ipv4.gateway": "10.0.0.1", "ipv4.dns": "1.1.1.1", "ipv4.ignore-auto-dns": "yes"}
    assert up[-3:] == ["Wired connection (enp6s0)", "ifname", "enp6s0"]


def test_run_all_stops_at_first_failure(monkeypatch):
    results = iter([subprocess.CompletedProcess([], 0, "", ""),
                    subprocess.CompletedProcess([], 4, "", "Error: Connection activation failed: IP configuration\n")])
    ran = []
    monkeypatch.setattr(core, "run", lambda args, timeout=10: ran.append(args) or next(results))
    ok, error, index = net.run_all([["a"], ["b"], ["c"]])
    assert (ok, index) == (False, 1) and "activation failed" in error and ran == [["a"], ["b"]]
