"""Shared fixtures: a fake command runner standing in for core.run/out/have."""

import subprocess

import pytest

from omarchy_settings import core, distro, host


class FakeCommands:
    """answers maps a command line ("pactl get-default-sink") to its output; codes to its exit code.

    Commands run (not the ones only read with out) are recorded in calls, and the ones started with spawn in
    spawned; have lists the commands that "exist" (all of them with have_all)."""

    def __init__(self):
        self.answers: dict[str, str] = {}
        self.codes: dict[str, int] = {}
        self.calls: list[list[str]] = []
        self.spawned: list[list[str]] = []
        self.have: set[str] = set()
        self.have_all = False

    def run(self, args, timeout=10):
        self.calls.append(args)
        key = " ".join(args)
        return subprocess.CompletedProcess(args, self.codes.get(key, 0), self.answers.get(key, ""), "")

    def out(self, args, timeout=10):
        key = " ".join(args)
        return self.answers.get(key, "").strip() if self.codes.get(key, 0) == 0 else ""


@pytest.fixture
def commands(monkeypatch):
    fake = FakeCommands()
    monkeypatch.setattr(core, "run", fake.run)
    monkeypatch.setattr(core, "out", fake.out)
    monkeypatch.setattr(core, "have", lambda cmd: fake.have_all or cmd in fake.have)
    monkeypatch.setattr(core, "spawn", lambda args: fake.spawned.append(args) or True)
    return fake


@pytest.fixture(autouse=True)
def on_omarchy(monkeypatch):
    """Tests run as on Omarchy (an Arch system) unless they ask for plain Hyprland (the `plain_hyprland` fixture)
    or set distro._family."""
    monkeypatch.setattr(host, "_detected", "omarchy")
    monkeypatch.setattr(distro, "_family", "arch")


@pytest.fixture
def plain_hyprland(monkeypatch):
    monkeypatch.setattr(host, "_detected", "hyprland")
