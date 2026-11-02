import json
import re

import pytest

from omarchy_settings import core, waybar


@pytest.fixture
def wb(tmp_path, monkeypatch):
    """Every Waybar path inside tmp_path; commands recorded instead of run."""
    theme = tmp_path / "state" / "theme"
    theme.mkdir(parents=True)
    (theme / "colors.toml").write_text('background = "#000000"\nforeground = "#ffffff"\naccent = "#ff0000"\n')
    paths = {
        "CONFIG_DIR": tmp_path / "waybar",
        "CONFIG": tmp_path / "waybar" / "config.jsonc",
        "STYLE": tmp_path / "waybar" / "style.css",
        "THEME_DIR": theme,
        "TEMPLATE": tmp_path / "themed" / "waybar.css.tpl",
        "RENDERED": theme / "waybar.css",
        "THEME_HOOK": tmp_path / "hooks" / "theme-set.d" / "x",
        "BOOT_HOOK": tmp_path / "hooks" / "post-boot.d" / "x",
    }
    for name, value in paths.items():
        monkeypatch.setattr(waybar, name, value)
    calls = []
    monkeypatch.setattr(core, "run", lambda args, timeout=10: calls.append(args))
    monkeypatch.setattr(core, "spawn", lambda args: calls.append(["spawn", *args]) or True)
    monkeypatch.setattr(core, "have", lambda cmd: True)
    waybar.calls = calls
    return waybar


def jsonc(text: str) -> dict:
    return json.loads("\n".join(line for line in text.splitlines() if not line.lstrip().startswith("//")))


def test_starter_config_is_valid_json_with_icons():
    cfg = jsonc(waybar.STARTER_CONFIG)
    assert cfg["position"] == "top" and "hyprland/workspaces" in cfg["modules-left"]
    assert not re.search(r"@\w+@", waybar.STARTER_CONFIG)
    assert all(ord(c) >= 0xF0000 for c in cfg["custom/omarchy"]["format"])  # the icon wasn't lost


def test_render_replaces_known_keys_only():
    assert waybar.render("{{ a }} {{b}} {{ c }}", {"a": "#1", "b": "#2"}) == "#1 #2 {{ c }}"


def test_ensure_config_creates_everything_without_overwriting(wb):
    wb.CONFIG_DIR.mkdir()
    wb.CONFIG.write_text("// my config\n")
    wb.ensure_config()
    assert wb.CONFIG.read_text() == "// my config\n"  # the user's file stays untouched
    assert f'@import "{wb.RENDERED}";' in wb.STYLE.read_text()
    assert "@define-color accent #ff0000;" in wb.RENDERED.read_text()
    assert wb.THEME_HOOK.stat().st_mode & 0o111 and "SIGUSR2" in wb.THEME_HOOK.read_text()


def test_position_roundtrip(wb):
    wb.ensure_config()
    assert wb.read_position() == "top"
    assert wb.write_position("left") and wb.read_position() == "left"
    with pytest.raises(ValueError):
        wb.write_position("middle")


def test_reset_keeps_backup(wb):
    wb.ensure_config()
    wb.CONFIG.write_text('{ "position": "bottom" }')
    wb.reset_config()
    assert wb.CONFIG.with_name("config.jsonc.omarchy-settings.bak").read_text() == '{ "position": "bottom" }'
    assert wb.read_position() == "top"


def test_enable_and_disable(wb, monkeypatch):
    monkeypatch.setattr(waybar, "running", lambda: False)
    wb.set_enabled(True)
    assert wb.enabled() and wb.has_config()
    assert ["spawn", "uwsm-app", "--", "waybar"] in wb.calls
    assert ["omarchy-toggle-bar", "on"] in wb.calls  # hides the shell bar
    wb.calls.clear()
    wb.set_enabled(False)
    assert not wb.enabled()
    assert wb.calls == [["pkill", "-x", "waybar"], ["omarchy-toggle-bar", "off"]]
