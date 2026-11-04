from hyprdial import accessibility as a11y


def test_cursor_size(commands):
    commands.answers["gsettings get org.gnome.desktop.interface cursor-size"] = "32\n"
    commands.answers["gsettings get org.gnome.desktop.interface cursor-theme"] = "'Adwaita'\n"
    assert a11y.cursor_size() == 32
    a11y.set_cursor_size(48)
    assert commands.calls == [
        ["gsettings", "set", "org.gnome.desktop.interface", "cursor-size", "48"],
        ["hyprctl", "setcursor", "Adwaita", "48"],
    ]


def test_cursor_size_defaults_without_gsettings(commands):
    assert a11y.cursor_size() == 24


def test_render_extras():
    assert a11y.render_extras({}) == [] and a11y.render_extras({"cursor_size": 24}) == []
    lines = a11y.render_extras({"cursor_size": 48})
    assert 'pcall(function() hl.env("XCURSOR_SIZE", "48") end)' in lines
