import json

import pytest

from omarchy_settings import host


def test_omarchy_needs_its_command_and_lua_helpers(tmp_path, commands):
    helpers = tmp_path / "helpers.lua"
    commands.have = {"omarchy"}
    assert host.detect({}, helpers) == "hyprland"  # no helpers.lua
    helpers.write_text("o = o or {}\n")
    assert host.detect({}, helpers) == "omarchy"
    commands.have = set()
    assert host.detect({}, helpers) == "hyprland"


def test_platform_can_be_forced(tmp_path, commands):
    assert host.detect({"HYPRDIAL_PLATFORM": "omarchy"}, tmp_path / "none") == "omarchy"
    commands.have_all = True
    (tmp_path / "helpers.lua").write_text("")
    assert host.detect({"HYPRDIAL_PLATFORM": "hyprland"}, tmp_path / "helpers.lua") == "hyprland"
    assert host.detect({"HYPRDIAL_PLATFORM": "other"}, tmp_path / "helpers.lua") == "omarchy"


@pytest.mark.parametrize(
    "answer, expected",
    [
        ({"tag": "v0.56.2", "version": "0.56.2"}, (0, 56, 2)),
        ({"tag": "v0.57.0-12-gabc"}, (0, 57, 0)),
        ({"version": "0.56"}, (0, 56)),
        ({"tag": "unknown"}, None),
        ([], None),
    ],
)
def test_hyprland_version(commands, answer, expected):
    commands.answers["hyprctl version -j"] = json.dumps(answer)
    assert host.hyprland_version() == expected


def test_hyprland_version_when_not_running(commands):
    assert host.hyprland_version() is None


def test_config_problem(tmp_path):
    main, legacy = tmp_path / "hyprland.lua", tmp_path / "hyprland.conf"
    assert "isn't running" in host.config_problem(None, main, legacy)
    assert "0.54.3 is too old" in host.config_problem((0, 54, 3), main, legacy)
    assert host.config_problem((0, 56, 2), main, legacy) is None  # no config at all: one is created
    legacy.write_text("")
    assert "hyprland.conf" in host.config_problem((0, 57), main, legacy)
    main.write_text("")
    assert host.config_problem((0, 57), main, legacy) is None


def test_terminal_command_on_omarchy():
    assert host.terminal_command("sudo x") == ["omarchy-launch-floating-terminal-with-presentation", "sudo x"]


def test_terminal_command_elsewhere(commands, plain_hyprland):
    commands.have = {"alacritty", "foot"}
    assert host.terminal_command("sudo x")[:4] == [
        "foot",
        "bash",
        "-c",
        'sudo x; echo; read -rp "Press Enter to close"',
    ]
    commands.have = {"alacritty"}
    assert host.terminal_command("sudo x")[:3] == ["alacritty", "-e", "bash"]
    commands.have = set()
    assert host.terminal_command("sudo x")[:2] == ["xterm", "-e"]


def test_launch_and_tui(commands):
    assert host.launch("gimp") == "gimp"
    commands.have = {"uwsm-app", "xdg-terminal-exec"}
    assert host.launch("gimp") == "uwsm-app -- gimp"
    assert host.tui_command("btop") == "xdg-terminal-exec btop"
