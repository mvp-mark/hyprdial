from pathlib import Path

import pytest

from omarchy_settings import keybinds as kb

FIXTURES = Path(__file__).parent / "fixtures" / "bindings"


@pytest.fixture
def sources(monkeypatch, tmp_path):
    monkeypatch.setattr(kb, "DEFAULT_DIR", FIXTURES)
    monkeypatch.setattr(kb, "USER_FILE", tmp_path / "bindings.lua")
    return kb.source_binds()


def by_desc(sources, desc):
    return next(s for s in sources if s.desc == desc)


# ------------------------------------------------------------------ keys
def test_canon_ignores_modifier_order_case_and_aliases():
    assert kb.canon("shift + super + b") == "SUPER + SHIFT + B"
    assert kb.canon("MOD4 + CONTROL + return") == "SUPER + CTRL + RETURN"


def test_from_modmask_builds_canonical_order():
    assert kb.from_modmask(64 | 1 | 8, "B") == "SUPER + SHIFT + ALT + B"
    assert kb.from_modmask(0, "PRINT") == "PRINT"


@pytest.mark.parametrize(
    "key, label",
    [
        ("code:10", "1"),
        ("code:19", "0"),
        ("code:20", "-"),
        ("RETURN", "Enter"),
        ("XF86AudioRaiseVolume", "Volume +"),
        ("b", "B"),
        ("code:99", "Code:99"),
    ],
)
def test_key_label(key, label):
    assert kb.key_label(key) == label


def test_keycaps():
    assert kb.keycaps("SUPER + CTRL + code:11") == ["Super", "Ctrl", "2"]


# ------------------------------------------------------------------ reading the sources
def test_find_binds_skips_comments_and_strings():
    text = '-- o.bind("A", "x", "y")\nlocal s = "o.bind(no)"\no.bind("SUPER + A", "Real", "cmd, with comma")\n'
    assert kb.find_binds(text) == [("o.bind", ['"SUPER + A"', '"Real"', '"cmd, with comma"'])]


def test_parse_source_skips_computed_keys(sources):
    assert all("workspace" not in (s.desc or "") for s in sources)
    assert by_desc(sources, "Expand window left").keys == "SUPER + code:20"


def test_parse_source_handles_multiline_and_spacing(sources):
    gm = by_desc(sources, "Google Messages")
    assert gm.keys == "SUPER + SHIFT + CTRL + G"
    assert gm.action.startswith("{ webapp =") and gm.action.endswith("focus = true }")


def test_bind_toggle_becomes_command(sources):
    assert by_desc(sources, "Toggle nightlight").action == '"omarchy-toggle-" .. "nightlight"'


def test_escaped_quotes_inside_action(sources):
    assert by_desc(sources, "Make webcam overlay smaller").action.endswith('\\"quoted\\""')


@pytest.mark.parametrize(
    "expr, free",
    [
        ('{ omarchy = "terminal" }', set()),
        ("hl.dsp.window.resize({ x = -100, y = 0, relative = true })", set()),
        ('universal_clipboard_shortcut("CTRL", "C")', {"universal_clipboard_shortcut"}),
        ("function() local zoom = hl.get_config('z') or 1 hl.config({ c = zoom + 1 }) end", set()),
        ("function(a, b) return a + b + c end", {"c"}),
        ('"omarchy-toggle-" .. toggle', {"toggle"}),
        ("for _, w in ipairs(list) do end", {"list"}),
    ],
)
def test_free_names(expr, free):
    assert kb.free_names(expr) == free


def test_movable(sources):
    assert by_desc(sources, "Zoom in").movable
    assert by_desc(sources, "Toggle nightlight").movable
    assert not by_desc(sources, "Universal copy").movable


# ------------------------------------------------------------------ page entries
def live(modmask, key, desc, keycode=0):
    return {"modmask": modmask, "key": key, "keycode": keycode, "description": desc, "submap": "", "mouse": False}


def test_build_entries_matches_sources_and_reconstructs_loops(sources):
    entries = kb.build_entries(
        [
            live(64, "RETURN", "Terminal"),
            live(64, "", "Expand window left"),  # code:20, no 'key' from hyprctl
            live(64, "", "Switch to workspace 3"),  # generated in a loop
            live(64, "C", "Universal copy"),
            live(64, "F12", "Something else"),  # only exists live
        ],
        sources,
        kb.empty_state(),
    )
    e = {x.desc: x for x in entries}
    assert e["Terminal"].action == '{ omarchy = "terminal" }' and e["Terminal"].category == "applications"
    assert e["Expand window left"].keys == "SUPER + code:20" and e["Expand window left"].action
    assert e["Switch to workspace 3"].keys == "SUPER + code:12"
    assert e["Switch to workspace 3"].action is None and "loop" in e["Switch to workspace 3"].locked
    assert e["Universal copy"].action is None and "internal" in e["Universal copy"].locked
    assert e["Something else"].category == "other"


def test_build_entries_with_overrides_and_custom(sources):
    state = {
        "overrides": {
            "SUPER + RETURN": {"desc": "Terminal", "keys": "SUPER + T", "action": '{ omarchy = "terminal" }'},
            "SUPER + W": {"desc": "Close window"},
        },
        "custom": [{"keys": "SUPER + G", "desc": "Gimp", "kind": "launch", "command": "gimp"}],
    }
    entries = kb.build_entries([live(64, "T", "Terminal"), live(64, "G", "Gimp")], sources, state)
    e = {x.desc: x for x in entries}
    assert set(e) == {"Terminal", "Close window"}  # the new keys don't show up twice
    assert e["Terminal"].current_keys == "SUPER + T" and e["Terminal"].keys == "SUPER + RETURN"
    assert e["Close window"].current_keys is None


def test_render_unbinds_first_and_wraps_in_pcall():
    state = {
        "overrides": {
            "SUPER + W": {"desc": "Close"},
            "SUPER + RETURN": {"desc": "Term", "keys": "SUPER + T", "action": '{ omarchy = "terminal" }'},
        },
        "custom": [{"keys": "SUPER + G", "desc": 'Gimp "2"', "kind": "tui", "command": "btop"}],
    }
    lines = [line for line in kb.render(state) if line.startswith("pcall")]
    assert lines[:2] == [
        'pcall(function() hl.unbind("SUPER + RETURN") end)',
        'pcall(function() hl.unbind("SUPER + W") end)',
    ]
    assert lines[2] == 'pcall(function() o.bind("SUPER + T", "Term", { omarchy = "terminal" }) end)'
    assert lines[3] == 'pcall(function() o.bind("SUPER + G", "Gimp \\"2\\"", { tui = "btop" }) end)'


def test_render_empty_state_is_empty():
    assert kb.render(kb.empty_state()) == []


@pytest.mark.parametrize(
    "kind, expected",
    [
        ("launch", '{ launch = "gimp" }'),
        ("tui", '{ tui = "gimp" }'),
        ("command", '"gimp"'),
    ],
)
def test_custom_action(kind, expected):
    assert kb.custom_action(kind, "gimp") == expected


# ------------------------------------------------------------------ Omarchy's real files
@pytest.mark.skipif(not kb.DEFAULT_DIR.is_dir(), reason="Omarchy not installed")
def test_real_omarchy_bindings_still_parse():
    """Warns when an Omarchy update changes the format of the shortcut files."""
    sources = [s for s in kb.source_binds() if s.category != "user"]
    assert len(sources) > 50
    assert all(kb.split_keys(s.keys)[1] for s in sources)
    assert sum(s.movable for s in sources) > len(sources) * 0.9
