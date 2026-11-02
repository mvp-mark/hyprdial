import json

import pytest

from omarchy_settings import shell


@pytest.fixture
def config(tmp_path, monkeypatch, commands):
    path = tmp_path / "shell.json"
    monkeypatch.setattr(shell, "SHELL_CONFIG", path)
    monkeypatch.setattr(shell, "SHELL_DEFAULTS", tmp_path / "defaults.json")
    layout = {"left": [{"id": "omarchy.menu"}, {"id": "omarchy.spacer"}], "right": [{"id": "omarchy.spacer"}]}
    path.write_text(json.dumps({"version": 1, "bar": {"layout": layout}}))
    return path


def layout(path):
    return json.loads(path.read_text())["bar"]["layout"]


def test_remove_one_copy_only(config, commands):
    assert shell.remove_widget_at("left", 1, "omarchy.spacer")
    assert layout(config) == {"left": [{"id": "omarchy.menu"}], "right": [{"id": "omarchy.spacer"}]}
    assert commands.calls == [["omarchy-shell", "shell", "reloadConfig"]]


def test_remove_refuses_a_layout_that_changed(config):
    assert not shell.remove_widget_at("left", 0, "omarchy.spacer")  # index 0 is the menu
    assert not shell.remove_widget_at("center", 0, "omarchy.spacer")
    assert len(layout(config)["left"]) == 2


def test_add_another_copy(config):
    assert shell.add_widget_copy("omarchy.spacer", "right")
    assert layout(config)["right"] == [{"id": "omarchy.spacer"}, {"id": "omarchy.spacer"}]


def test_write_idle_keeps_the_rest(config):
    assert shell.write_idle("lock", 300)
    data = json.loads(config.read_text())
    assert data["idle"] == {"lock": 300} and "layout" in data["bar"]
