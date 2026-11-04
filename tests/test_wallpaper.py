from hyprdial import wallpaper as wp


def test_settings():
    assert wp.settings({}) == {"path": "", "fit": "cover", "monitors": {}}
    assert wp.settings({"wallpaper": {"path": "/a.jpg", "fit": "weird", "monitors": {"DP-1": "/b.png", "X": ""}}}) == {
        "path": "/a.jpg",
        "fit": "cover",
        "monitors": {"DP-1": "/b.png"},
    }


def test_problem(tmp_path):
    img = tmp_path / "a.png"
    img.write_bytes(b"x")
    assert wp.problem(str(img)) is None
    assert wp.problem("relative.png") == "path"
    assert wp.problem(str(tmp_path / "a,b.png")) == "path"
    assert wp.problem(str(tmp_path / "missing.png")) == "image"
    (tmp_path / "a.txt").write_text("")
    assert wp.problem(str(tmp_path / "a.txt")) == "image"


def test_render_conf():
    text = wp.render_conf({"path": "/a.jpg", "fit": "contain", "monitors": {"DP-1": "/b.png"}})
    assert "wallpaper {\n    monitor = \n    path = /a.jpg\n    fit_mode = contain\n}" in text
    assert "monitor = DP-1\n    path = /b.png" in text


def test_apply_live_or_start(commands, tmp_path):
    conf = tmp_path / "hyprdial-paper.conf"
    values = {"path": "/a.jpg", "fit": "cover", "monitors": {"DP-1": "/b.png"}}
    assert wp.apply(values, ["DP-1", "HDMI-A-1"], conf)
    assert commands.spawned == [["hyprpaper", "-c", str(conf)]] and commands.calls == []
    commands.answers["pgrep -a -x hyprpaper"] = f"7 hyprpaper -c {conf}"
    assert wp.apply(values, ["DP-1", "HDMI-A-1"], conf)
    assert commands.calls == [
        ["hyprctl", "hyprpaper", "wallpaper", "DP-1, /b.png, cover"],
        ["hyprctl", "hyprpaper", "wallpaper", "HDMI-A-1, /a.jpg, cover"],
    ]


def test_render_extras(commands, plain_hyprland, monkeypatch, tmp_path):
    monkeypatch.setattr(wp, "USER_CONF", tmp_path / "none")
    commands.have = {"hyprpaper"}
    assert wp.render_extras({}) == []
    assert wp.render_extras({"wallpaper": {"path": "/a.jpg"}})[-1].endswith(
        f'hl.exec_cmd("hyprpaper -c {wp.CONF}") end) end)'
    )
    commands.answers["pgrep -a -x hyprpaper"] = "9 hyprpaper"  # someone else's
    assert wp.render_extras({"wallpaper": {"path": "/a.jpg"}}) == []
