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


def test_dnd(fake):
    answers, calls, _have = fake
    assert system.dnd() is None  # shell not answering
    answers["omarchy-shell notifications isDnd"] = "off"
    assert system.dnd() is False
    answers["omarchy-shell notifications setDnd on"] = "on"
    assert system.set_dnd(True)
    assert ["omarchy-shell", "-q", "omarchy.indicators", "refresh"] in calls


def test_about_drops_empty_values(fake, monkeypatch):
    answers, _calls, _have = fake
    answers["omarchy version"] = "4.0.6-1"
    info = dict(system.about())
    assert info["omarchy"] == "4.0.6-1" and info["kernel"]
    monkeypatch.setattr(system, "read_first", lambda path, prefix: "")
    assert "cpu" not in dict(system.about()) and "memory" not in dict(system.about())


@pytest.mark.parametrize("code, stdout, expected", [
    (0, "omarchy 4.0.6-1 -> 4.0.7-1\n", ("available", "omarchy 4.0.6-1 -> 4.0.7-1")),
    (1, "Omarchy is up to date\n", ("current", "")),
    (1, "", (None, "")),  # failed some other way
])
def test_update_status(monkeypatch, code, stdout, expected):
    monkeypatch.setattr(core, "run", lambda args, timeout=10: subprocess.CompletedProcess(args, code, stdout, ""))
    assert system.update_status() == expected


def test_update_status_without_the_command(monkeypatch):
    monkeypatch.setattr(core, "run", lambda args, timeout=10: None)
    assert system.update_status() == (None, "")


def test_snapshot_needs_snapper(fake):
    _answers, _calls, have = fake
    have.add("omarchy-snapshot")
    assert not system.can_snapshot()
    have.add("snapper")
    assert system.can_snapshot()
    assert system.SNAPSHOT_COMMAND[-2:] == ["omarchy-snapshot", "create"]
