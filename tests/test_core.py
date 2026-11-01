import json

import pytest

from omarchy_settings import core

MAIN = '''dofile("bootstrap.lua")
require("default.hypr.omarchy")
require("hypr.monitors")
require("hypr.autostart")

-- Toggle config flags dynamically.
require("default.hypr.toggles")

o.window(".*", { idle_inhibit = "fullscreen" })
'''


@pytest.fixture
def calls(monkeypatch):
    """Records the commands instead of calling the real hyprctl."""
    recorded = []

    def fake_run(args, timeout=10):
        recorded.append(args)
        return None

    monkeypatch.setattr(core, "run", fake_run)
    return recorded


@pytest.fixture
def store(tmp_path, calls):
    main = tmp_path / "hyprland.lua"
    main.write_text(MAIN)
    s = core.HyprStore(managed=tmp_path / "omarchy-settings.lua", main=main, state=tmp_path / "state.json")
    yield s
    if s._timer:
        s._timer.cancel()


# ------------------------------------------------------------------ conversion to Lua
@pytest.mark.parametrize("value, expected", [
    (True, "true"), (5, "5"), (1.0, "1"), (0.92, "0.92"), (1.333333, "1.333333"), ("br", '"br"'), ('a"b', '"a\\"b"'),
])
def test_lua_literals(value, expected):
    assert core.lua(value) == expected


def test_lua_rejects_control_characters():
    with pytest.raises(ValueError):
        core.lua("a\nb")


@pytest.mark.parametrize("text, expected", [("true", "true"), ("0.3", "0.3"), ("-1", "-1"), ("", '""'), ("br", '"br"')])
def test_option_lua_recovers_types(text, expected):
    assert core.option_lua(text) == expected


def test_config_call_nests_sections_and_maps_hyphens():
    code = core.config_call({"decoration:blur:enabled": "true", "input:touchpad:tap-to-click": "false",
                             "general:gaps_in": "5"})
    assert code == (
        "hl.config({\n"
        "  decoration = {\n    blur = {\n      enabled = true,\n    },\n  },\n"
        "  general = {\n    gaps_in = 5,\n  },\n"
        "  input = {\n    touchpad = {\n      tap_to_click = false,\n    },\n  },\n"
        "})"
    )


def test_monitor_call_keeps_field_order():
    rule = {"scale": 1.25, "output": "DP-1", "vrr": 1, "mode": "2560x1440@164.83", "position": "0x0"}
    assert core.monitor_call(rule) == \
        'hl.monitor({ output = "DP-1", mode = "2560x1440@164.83", position = "0x0", scale = 1.25, vrr = 1 })'


def test_live_rule_from_hyprctl_monitor():
    mon = {"name": "DP-1", "width": 2560, "height": 1440, "refreshRate": 164.83299, "x": 0, "y": 0,
           "scale": 1.0, "transform": 0, "vrr": True, "mirrorOf": "none", "disabled": False}
    assert core.live_rule(mon) == {"output": "DP-1", "mode": "2560x1440@164.83", "position": "0x0",
                                   "scale": 1.0, "transform": 0, "vrr": 1}


def test_live_option_parses_each_hyprctl_field(monkeypatch):
    answers = {
        "a": '{"option": "a", "bool": false, "set": true}',
        "b": '{"option": "b", "css": "5 5 5 5", "set": true}',
        "c": '{"option": "c", "str": "[[EMPTY]]", "set": false}',
        "d": '{"option": "d", "float": 0.4, "set": true}',
        "e": "no such option",
    }
    monkeypatch.setattr(core, "out", lambda args, timeout=10: answers[args[2]])
    assert [core.live_option(k) for k in "abcde"] == [False, "5", "", 0.4, None]


# ------------------------------------------------------------------ HyprStore
def test_require_is_inserted_before_toggles_comment(store):
    store.save()
    text = store.main.read_text()
    assert text.index(core.REQUIRE_LINE) < text.index("-- Toggle config flags") < text.index(core.TOGGLES_LINE)
    assert store.main.with_name("hyprland.lua.omarchy-settings.bak").read_text() == MAIN
    store.save()
    assert store.main.read_text().count(core.REQUIRE_LINE) == 1


def test_require_is_appended_without_toggles(store):
    store.main.write_text('require("default.hypr.omarchy")')
    store.save()
    assert store.main.read_text().rstrip().endswith(core.REQUIRE_LINE)


def test_pending_changes_are_visible_before_flush(store):
    store.set("general:gaps_in", 8)
    assert store.get("general:gaps_in") == "8"
    store.set_monitor({"output": "DP-1", "position": "10x0"})
    assert store.get_monitor("DP-1")["position"] == "10x0"
    store.unset_monitor("DP-1")
    assert store.get_monitor("DP-1") is None


def test_flush_applies_live_and_persists(store, calls):
    store.set("general:gaps_in", 8)
    store.set_monitor({"output": "DP-1", "mode": "preferred", "position": "auto", "scale": 1})
    store.flush()
    evals = [c[2] for c in calls if c[:2] == ["hyprctl", "eval"]]
    assert any("gaps_in = 8" in e for e in evals) and any('output = "DP-1"' in e for e in evals)
    generated = store.managed.read_text()
    assert "gaps_in = 8" in generated and 'hl.monitor({ output = "DP-1"' in generated
    state = json.loads(store.state_file.read_text())
    assert state["hypr"] == {"general:gaps_in": "8"} and "DP-1" in state["monitors"]


def test_unset_reloads_instead_of_eval(store, calls):
    store.set("general:gaps_in", 8)
    store.flush()
    calls.clear()
    store.unset("general:gaps_in")
    store.flush()
    assert calls == [["hyprctl", "reload"]]
    assert "gaps_in" not in store.managed.read_text()


def test_reset_options_keeps_monitors_and_bindings(store):
    store.set("general:gaps_in", 8)
    store.set_monitor({"output": "DP-1", "scale": 1})
    store.flush()
    store.apply_bindings({"overrides": {"SUPER + W": {"desc": "Close"}}, "custom": []})
    store.reset_options()
    store.flush()
    assert store.values == {}
    assert "DP-1" in store.monitors and store.bindings["overrides"]


def test_apply_bindings_writes_and_reloads(store, calls):
    store.apply_bindings({"overrides": {"SUPER + W": {"desc": "Close"}}, "custom": []})
    assert 'pcall(function() hl.unbind("SUPER + W") end)' in store.managed.read_text()
    assert calls[-1] == ["hyprctl", "reload"]
    reloaded = core.HyprStore(managed=store.managed, main=store.main, state=store.state_file)
    assert reloaded.bindings["overrides"] == {"SUPER + W": {"desc": "Close"}}


def test_corrupt_state_starts_empty(tmp_path, calls):
    state = tmp_path / "state.json"
    state.write_text("{not json")
    s = core.HyprStore(managed=tmp_path / "g.lua", main=tmp_path / "none.lua", state=state)
    assert (s.values, s.monitors, s.bindings) == ({}, {}, {"overrides": {}, "custom": []})
