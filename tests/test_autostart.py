from omarchy_settings import autostart, core


def desktop(directory, name, body):
    directory.mkdir(exist_ok=True)
    (directory / name).write_text("[Desktop Entry]\n" + body)


def test_entries_filter_and_override(tmp_path):
    system, user = tmp_path / "system", tmp_path / "user"
    desktop(system, "a.desktop", "Name=Applet\nComment=Tray\n")
    desktop(system, "gnome.desktop", "Name=GNOME only\nOnlyShowIn=GNOME;\n")
    desktop(system, "kde-not.desktop", "Name=Not in Hyprland\nNotShowIn=Hyprland;\n")
    desktop(system, "off.desktop", "Name=Off by GNOME key\nX-GNOME-Autostart-enabled=false\n")
    desktop(user, "a.desktop", "Hidden=true\n")
    desktop(user, "mine.desktop", "Name=Mine\nExec=mine\n")
    found = autostart.entries(user, [system], {"Hyprland"})
    assert [(e.id, e.name, e.enabled, e.system) for e in found] == [
        ("a.desktop", "Applet", False, True),
        ("mine.desktop", "Mine", True, False),
        ("off.desktop", "Off by GNOME key", False, True),
    ]


def test_toggle_system_entry_uses_a_bare_override(tmp_path):
    system, user = tmp_path / "system", tmp_path / "user"
    desktop(system, "a.desktop", "Name=Applet\n")
    entry = autostart.entries(user, [system], {"Hyprland"})[0]
    autostart.set_enabled(entry, False, user)
    assert (user / "a.desktop").read_text() == autostart.OVERRIDE
    autostart.set_enabled(entry, True, user)
    assert not (user / "a.desktop").exists()


def test_toggle_user_entry_keeps_its_content(tmp_path):
    user = tmp_path / "user"
    desktop(user, "mine.desktop", "Name=Mine\nExec=mine\n\n[Desktop Action x]\nName=X\n")
    entry = autostart.entries(user, [], {"Hyprland"})[0]
    autostart.set_enabled(entry, False, user)
    text = (user / "mine.desktop").read_text()
    assert "Hidden=true\n\n[Desktop Action x]" in text and "Exec=mine" in text
    autostart.set_enabled(entry, True, user)
    assert "Hidden" not in (user / "mine.desktop").read_text()


def test_set_key_replaces_once_and_removes():
    text = "[Desktop Entry]\nName=A\nHidden=false\nHidden=false\n[Other]\nHidden=keep\n"
    assert autostart.set_key(text, "Hidden", "true") == "[Desktop Entry]\nName=A\nHidden=true\n[Other]\nHidden=keep\n"
    assert autostart.set_key(text, "Hidden", None) == "[Desktop Entry]\nName=A\n[Other]\nHidden=keep\n"


def test_lua_commands(tmp_path):
    lua = tmp_path / "autostart.lua"
    lua.write_text(
        '-- o.launch_on_start("commented")\no.launch_on_start("syncthing")\no.exec_on_start(\'foo --bar\') -- note\n'
    )
    assert autostart.lua_commands(lua) == ["syncthing", "foo --bar"]
    assert autostart.lua_commands(tmp_path / "missing.lua") == []


def test_own_commands_go_to_the_generated_file(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "run", lambda args, timeout=10: None)
    store = core.HyprStore(
        managed=tmp_path / "omarchy-settings.lua", main=tmp_path / "hyprland.lua", state=tmp_path / "state.json"
    )
    store.set_extra("autostart", ["discord --start-minimized", 'say "hi"'], reload=False)
    text = (tmp_path / "omarchy-settings.lua").read_text()
    assert 'pcall(function() o.launch_on_start("discord --start-minimized") end)' in text
    assert 'o.launch_on_start("say \\"hi\\"")' in text
    assert autostart.valid_command("  ") is None and autostart.valid_command("a\nb") is None
