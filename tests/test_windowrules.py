import json

from hyprdial import windowrules as wr


def test_open_windows_one_per_app(commands):
    commands.answers["hyprctl clients -j"] = json.dumps(
        [
            {"class": "firefox", "title": "Docs"},
            {"class": "foot", "title": "~"},
            {"class": "firefox", "title": "Mail"},
            {"class": "", "initialClass": "", "title": "x"},
        ]
    )
    assert wr.open_windows() == [wr.Window("firefox", "Docs"), wr.Window("foot", "~")]


def test_open_windows_without_hyprland(commands):
    assert wr.open_windows() == []


def test_problem():
    assert wr.problem({"class": "", "float": True}) == "Choose an app or type its class."
    assert wr.problem({"class": "foot"}) == "Choose at least one thing to do."
    assert wr.problem({"class": "foot", "silent": True}) == "Choose at least one thing to do."
    assert "two positive" in wr.problem({"class": "foot", "size": [800, 0]})
    assert "floating" in wr.problem({"class": "foot", "pin": True})
    assert "1 to 99" in wr.problem({"class": "foot", "workspace": "abc"})
    assert "10%" in wr.problem({"class": "foot", "opacity": 0.05})
    assert wr.problem({"class": "foot", "float": True, "pin": True, "size": [800, 600], "opacity": 0.9}) is None


RULE = {
    "class": "org.gnome.Calculator",
    "float": True,
    "center": True,
    "size": [400, 600],
    "workspace": "3",
    "silent": True,
    "opacity": 0.9,
    "idle": True,
}


def test_rule_on_omarchy_uses_o_window():
    assert wr.rule_call(RULE) == (
        'pcall(function() o.window({ class = "^(org\\\\.gnome\\\\.Calculator)$" }, { float = true, center = true, '
        'size = { 400, 600 }, workspace = "3 silent", opacity = "0.9", idle_inhibit = "fullscreen" }) end)'
    )


def test_rule_on_plain_hyprland_uses_hl_window_rule(plain_hyprland):
    line = wr.rule_call({"class": "mpv", "fullscreen": True})
    assert line == 'pcall(function() hl.window_rule({ match = { class = "^(mpv)$" }, fullscreen = true }) end)'


def test_render_skips_invalid_rules():
    assert wr.render_extras({}) == []
    lines = wr.render_extras({"window_rules": [RULE, {"class": "x"}, "junk"]})
    assert lines[:2] == ["", "-- Window rules"] and len(lines) == 3


def test_describe():
    assert wr.describe(RULE) == (
        "Floating, centered, 400×600, workspace 3, opacity 90%, keeps the screen on in fullscreen"
    )


def test_config_rules_read_the_users_files_only(tmp_path):
    (tmp_path / "hyprland.lua").write_text(
        'hl.window_rule({\n  match = { class = "kitty" },\n  opacity = "0.9",\n})\n-- hl.window_rule({ x })\n'
    )
    (tmp_path / "hyprdial.lua").write_text('hl.window_rule({ match = { class = "mine" } })\n')
    (tmp_path / "apps.lua").write_text('o.window("steam", { float = true })\n')
    found = wr.config_rules(tmp_path)
    assert [(r.file, r.text) for r in found] == [
        ("apps.lua", 'o.window("steam", { float = true })'),
        ("hyprland.lua", 'hl.window_rule({ match = { class = "kitty" }, opacity = "0.9", })'),
    ]


def test_match_regex_escapes_only_regex_characters():
    assert wr.match_regex("org.gnome.Calculator") == "^(org\\.gnome\\.Calculator)$"
    assert wr.match_regex("hyprdial-test_app") == "^(hyprdial-test_app)$"
    assert wr.match_regex("a+b(c)") == "^(a\\+b\\(c\\))$"
