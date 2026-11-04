from hyprdial import workspaces as ws


def test_normalize_keeps_workspaces_1_to_10_and_puts_start_workspaces_on_their_display():
    s = ws.normalize(
        {"monitor": {"1": "DP-1", "11": "DP-1", "2": ""}, "default": {"HDMI-A-1": "2"}, "persistent": ["3", "x", "1"]}
    )
    assert s == {"monitor": {"1": "DP-1", "2": "HDMI-A-1"}, "default": {"HDMI-A-1": "2"}, "persistent": ["1", "3"]}
    assert ws.normalize(None) == ws.empty() and ws.is_empty({})


def test_render():
    lines = ws.render_extras(
        {"workspaces": {"monitor": {"1": "DP-1"}, "default": {"DP-1": "1"}, "persistent": ["1", "4"]}}
    )
    assert lines == [
        "",
        "-- Workspaces",
        'pcall(function() hl.workspace_rule({ workspace = "1", monitor = "DP-1", default = true, persistent = true }) end)',
        'pcall(function() hl.workspace_rule({ workspace = "4", persistent = true }) end)',
    ]
    assert ws.render_extras({}) == []
