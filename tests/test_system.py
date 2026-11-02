import subprocess

import pytest

from omarchy_settings import core, system


def test_time_settings(commands):
    commands.answers["timedatectl show"] = (
        "Timezone=America/Manaus\nLocalRTC=no\nCanNTP=yes\nNTP=yes\nNTPSynchronized=no\n"
    )
    assert system.time_settings() == {"timezone": "America/Manaus", "ntp": True, "can_ntp": True, "synced": False}


def test_locale_settings_skip_c(commands):
    commands.answers["localectl status"] = (
        "System Locale: LANG=pt_BR.UTF-8\n                LC_TIME=en_US.UTF-8\n    VC Keymap: br"
    )
    commands.answers["localectl list-locales"] = "C.UTF-8\nen_US.UTF-8\npt_BR.UTF-8\n"
    assert system.locale_settings() == ("pt_BR.UTF-8", ["en_US.UTF-8", "pt_BR.UTF-8"])


def test_set_commands(commands):
    assert system.set_timezone("Europe/Lisbon") == (True, "")
    system.set_ntp(False)
    system.set_locale("en_US.UTF-8")
    assert commands.calls == [
        ["timedatectl", "set-timezone", "Europe/Lisbon"],
        ["timedatectl", "set-ntp", "false"],
        ["localectl", "set-locale", "LANG=en_US.UTF-8"],
    ]


def test_dnd(commands):
    assert system.dnd() is None  # shell not answering
    commands.answers["omarchy-shell notifications isDnd"] = "off"
    assert system.dnd() is False
    commands.answers["omarchy-shell notifications setDnd on"] = "on"
    assert system.set_dnd(True)
    assert ["omarchy-shell", "-q", "omarchy.indicators", "refresh"] in commands.calls


def test_about_drops_empty_values(commands, monkeypatch):
    commands.answers["omarchy version"] = "4.0.6-1"
    info = dict(system.about())
    assert info["omarchy"] == "4.0.6-1" and info["kernel"]
    monkeypatch.setattr(system, "read_first", lambda path, prefix: "")
    assert "cpu" not in dict(system.about()) and "memory" not in dict(system.about())


@pytest.mark.parametrize(
    "code, stdout, expected",
    [
        (0, "omarchy 4.0.6-1 -> 4.0.7-1\n", ("available", "omarchy 4.0.6-1 -> 4.0.7-1")),
        (1, "Omarchy is up to date\n", ("current", "")),
        (1, "", (None, "")),  # failed some other way
    ],
)
def test_update_status(monkeypatch, code, stdout, expected):
    monkeypatch.setattr(core, "run", lambda args, timeout=10: subprocess.CompletedProcess(args, code, stdout, ""))
    assert system.update_status() == expected


def test_update_status_without_the_command(monkeypatch):
    monkeypatch.setattr(core, "run", lambda args, timeout=10: None)
    assert system.update_status() == (None, "")


def test_snapshot_needs_snapper(commands):
    commands.have.add("omarchy-snapshot")
    assert not system.can_snapshot()
    commands.have.add("snapper")
    assert system.can_snapshot()
    assert system.SNAPSHOT_COMMAND[-2:] == ["omarchy-snapshot", "create"]


def test_installable_locales(tmp_path):
    gen = tmp_path / "locale.gen"
    gen.write_text(
        "en_US.UTF-8 UTF-8  \n#en_US ISO-8859-1  \n#pt_BR.UTF-8 UTF-8  \n#be_BY@latin UTF-8\n#ja_JP.UTF-8 UTF-8\n"
    )
    assert system.installable_locales(["en_US.utf8", "ja_JP.UTF-8"], gen) == ["be_BY@latin", "pt_BR.UTF-8"]
    assert system.installable_locales([], tmp_path / "missing") == []


def test_install_locale_command():
    cmd = system.install_locale_command("pt_BR.UTF-8")
    assert cmd[0] == system.TERMINAL
    assert cmd[1] == r"sudo sed -i 's/^#\s\?\(pt_BR\.UTF-8 UTF-8\)/\1/' /etc/locale.gen && sudo locale-gen"
    with pytest.raises(ValueError):
        system.install_locale_command("pt_BR'; rm -rf ~")


def test_locale_description(tmp_path):
    (tmp_path / "pt_BR").write_text('LC_IDENTIFICATION\nlanguage   "Brazilian Portuguese"\nterritory  "Brazil"\n')
    assert system.locale_description("pt_BR.UTF-8", tmp_path) == "Brazilian Portuguese (Brazil)"
    assert system.locale_description("xx_YY.UTF-8", tmp_path) == ""
