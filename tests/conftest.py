"""Shared fixtures: a fake command runner standing in for core.run/out/have."""
import subprocess

import pytest

from omarchy_settings import core


class FakeCommands:
    """answers maps a command line ("pactl get-default-sink") to its output; codes to its exit code.

    Commands run (not the ones only read with out) are recorded in calls; have lists the commands that "exist"
    (all of them with have_all)."""

    def __init__(self):
        self.answers: dict[str, str] = {}
        self.codes: dict[str, int] = {}
        self.calls: list[list[str]] = []
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
    return fake
