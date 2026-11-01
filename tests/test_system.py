import subprocess

import pytest

from omarchy_settings import core, system


@pytest.fixture
def fake(monkeypatch):
    answers: dict[str, str] = {}
    calls: list[list[str]] = []
    have: set[str] = set()

    def fake_run(args, timeout=10):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, answers.get(" ".join(args), ""), "")

    monkeypatch.setattr(core, "out", lambda args, timeout=10: answers.get(" ".join(args), "").strip())
    monkeypatch.setattr(core, "run", fake_run)
    monkeypatch.setattr(core, "have", lambda cmd: cmd in have)
    return answers, calls, have


def test_time_settings(fake):
    answers, _calls, _have = fake
    answers["timedatectl show"] = "Timezone=America/Manaus\nLocalRTC=no\nCanNTP=yes\nNTP=yes\nNTPSynchronized=no\n"
    assert system.time_settings() == {"timezone": "America/Manaus", "ntp": True, "can_ntp": True, "synced": False}


def test_locale_settings_skip_c(fake):
    answers, _calls, _have = fake
    answers["localectl status"] = "System Locale: LANG=pt_BR.UTF-8\n                LC_TIME=en_US.UTF-8\n    VC Keymap: br"
    answers["localectl list-locales"] = "C.UTF-8\nen_US.UTF-8\npt_BR.UTF-8\n"
    assert system.locale_settings() == ("pt_BR.UTF-8", ["en_US.UTF-8", "pt_BR.UTF-8"])


def test_set_commands(fake):
    _answers, calls, _have = fake
    assert system.set_timezone("Europe/Lisbon") == (True, "")
    system.set_ntp(False)
    system.set_locale("en_US.UTF-8")
    assert calls == [["timedatectl", "set-timezone", "Europe/Lisbon"], ["timedatectl", "set-ntp", "false"],
                     ["localectl", "set-locale", "LANG=en_US.UTF-8"]]


def test_default_apps_only_installed(fake, tmp_path, monkeypatch):
    answers, _calls, have = fake
    (tmp_path / "firefox.desktop").write_text("")
    (tmp_path / "zen.desktop").write_text("")
    monkeypatch.setattr(system, "APP_DIRS", [tmp_path])
    have.update({"foot", "nvim", "zeditor"})
    answers["omarchy default browser"] = "zen"
    answers["omarchy default terminal"] = "foot"
    answers["omarchy default editor"] = "zeditor"
    apps = system.default_apps()
    assert apps["browser"] == ([("firefox", "Firefox"), ("zen", "Zen")], "zen")
    assert apps["terminal"] == ([("foot", "Foot")], "foot")
    assert apps["editor"] == ([("nvim", "Neovim"), ("zed", "Zed")], "zed")  # the command name maps back


def test_about_drops_empty_values(fake, monkeypatch):
    answers, _calls, _have = fake
    answers["omarchy version"] = "4.0.6-1"
    info = dict(system.about())
    assert info["omarchy"] == "4.0.6-1" and info["kernel"]
    monkeypatch.setattr(system, "read_first", lambda path, prefix: "")
    assert "cpu" not in dict(system.about()) and "memory" not in dict(system.about())
