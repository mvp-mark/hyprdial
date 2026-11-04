from hyprdial import input as inp


def test_devices_only_lists_what_exists(commands, tmp_path):
    commands.have.update({"omarchy-hw-touchpad", "omarchy-hw-touchscreen"})
    commands.answers["omarchy-hw-touchpad"] = "elan-touchpad\n"
    assert inp.devices(tmp_path) == {"touchpad": True}
    (tmp_path / "touchpad-disabled-name").write_text("elan-touchpad")
    assert inp.devices(tmp_path) == {"touchpad": False}


def test_set_enabled(commands):
    assert inp.set_enabled("touchscreen", False)
    assert commands.calls == [["omarchy-toggle-input-device", "touchscreen", "off"]]
