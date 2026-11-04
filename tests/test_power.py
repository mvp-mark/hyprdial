import pytest

from omarchy_settings import core, power

PROFILES_OUT = """* performance:
    CpuDriver:\tamd_pstate
    Degraded:   no

  balanced:
    CpuDriver:\tamd_pstate

  power-saver:
    CpuDriver:\tamd_pstate
"""


@pytest.fixture
def commands(commands):
    commands.have_all = True
    return commands


def test_profiles_in_fixed_order_with_active(commands):
    commands.answers["powerprofilesctl list"] = PROFILES_OUT
    assert power.profiles() == (["power-saver", "balanced", "performance"], "performance")


def test_set_profile_goes_through_omarchy(commands):
    assert power.set_profile("balanced")
    assert commands.calls == [["omarchy-powerprofiles-set", "autodetect", "balanced"]]


def test_temperature_and_nightlight_state(commands):
    assert power.temperature() is None  # hyprsunset not running
    commands.answers["hyprctl hyprsunset temperature"] = "4000"
    assert power.temperature() == 4000 and power.nightlight_on(4000)
    assert not power.nightlight_on(6500) and not power.nightlight_on(None)


def test_schedule_round_trip():
    text = power.render_schedule("20:30", "06:45", 3500)
    assert power.parse_schedule(text) == ("20:30", "06:45", 3500)


def test_omarchy_default_file_has_no_schedule():
    default = (
        "profile {\n    time = 07:00\n    identity = true\n}\n\n"
        "# profile {\n#     time = 20:00\n#     temperature = 4000\n# }\n"
    )
    assert power.parse_schedule(default) is None


@pytest.mark.parametrize(
    "text, expected", [("7:05", "07:05"), (" 20:00 ", "20:00"), ("24:00", None), ("12:60", None), ("8h", None)]
)
def test_valid_time(text, expected):
    assert power.valid_time(text) == expected


def test_write_schedule_backs_up_once_and_restores(tmp_path):
    conf = tmp_path / "hyprsunset.conf"
    conf.write_text("original\n")
    power.write_schedule("20:00", "07:00", 4000, conf)
    power.write_schedule("21:00", "07:00", 3000, conf)
    assert power.parse_schedule(conf.read_text()) == ("21:00", "07:00", 3000)
    assert power.restore_schedule(conf) and conf.read_text() == "original\n"


def test_render_extras():
    assert power.render_extras({}) == []
    assert power.render_extras({"power_button": "menu"}) == []
    lines = power.render_extras({"power_button": "suspend", "nightlight_schedule": True})
    assert 'pcall(function() hl.unbind("XF86PowerOff") end)' in lines
    assert any('"systemctl suspend", { locked = true }' in line for line in lines)
    assert 'pcall(function() o.launch_on_start("hyprsunset") end)' in lines
    nothing = power.render_extras({"power_button": "nothing"})
    assert not any("o.bind" in line for line in nothing) and any("hl.unbind" in line for line in nothing)


def test_store_persists_extras(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "run", lambda args, timeout=10: None)
    paths = dict(
        managed=tmp_path / "omarchy-settings.lua", main=tmp_path / "hyprland.lua", state=tmp_path / "state.json"
    )
    store = core.HyprStore(**paths)
    store.set_extra("power_button", "lock")
    assert 'o.bind("XF86PowerOff", "Power button", "omarchy-system-lock"' in paths["managed"].read_text()
    assert core.HyprStore(**paths).extras == {"power_button": "lock"}
    store.set_extra("power_button", None)
    assert "XF86PowerOff" not in paths["managed"].read_text()


def test_suspend_in_menu_follows_omarchys_flag(commands):
    commands.codes["omarchy-toggle-enabled suspend-off"] = 1  # flag off: Suspend is in the menu
    assert power.suspend_in_menu()
    commands.codes["omarchy-toggle-enabled suspend-off"] = 0
    assert not power.suspend_in_menu()
    commands.calls.clear()
    power.set_suspend_in_menu(True)
    assert commands.calls == [["omarchy-toggle", "suspend-off", "off"]]


def test_hibernation(commands, tmp_path):
    commands.codes["omarchy-hibernation-available"] = 1
    assert not power.hibernation_ready()
    assert power.hibernation_command(False)[-1] == "omarchy-hibernation-setup"
    assert power.hibernation_command(True)[-1] == "omarchy-hibernation-remove"
    assert not power.hibernation_supported(tmp_path / "image_size")


def test_plain_hyprland_has_no_power_button_and_starts_hyprsunset_natively(commands, plain_hyprland):
    commands.have_all = False
    lines = power.render_extras({"power_button": "lock", "nightlight_schedule": True})
    assert not any("XF86PowerOff" in line for line in lines)
    assert 'pcall(function() hl.on("hyprland.start", function() hl.exec_cmd("hyprsunset") end) end)' in lines


def test_restart_hyprsunset_without_omarchy(commands):
    commands.have_all = False
    power.restart_hyprsunset()
    assert commands.calls == [["pkill", "-x", "hyprsunset"]] and commands.spawned == [["hyprsunset"]]
