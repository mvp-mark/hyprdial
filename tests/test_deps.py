import subprocess

import pytest

from omarchy_settings import core, deps


@pytest.fixture
def pacman(monkeypatch):
    """Fakes `pacman -T`: prints only the packages in the `absent` list."""
    state = {"absent": set(), "calls": []}

    def fake_run(args, timeout=10):
        state["calls"].append(args)
        out = "\n".join(p for p in args[2:] if p in state["absent"])
        return subprocess.CompletedProcess(args, 127 if out else 0, out + "\n" if out else "", "")

    monkeypatch.setattr(core, "run", fake_run)
    return state


def test_every_dependency_has_a_known_group_and_purpose():
    for d in deps.dependencies():
        assert d.group in deps.GROUPS and d.purpose
        assert deps.group_title(d.group)


def test_required_dependencies_cover_what_the_app_imports():
    required = {d.package for d in deps.dependencies() if d.group == "required"}
    assert {"python-gobject", "gtk4", "libadwaita", "gettext"} <= required


def test_waybar_is_optional_and_not_preselected():
    waybar = next(d for d in deps.dependencies() if d.package == "waybar")
    assert waybar.group == "optional" and not waybar.default


def test_missing_uses_pacman_t(pacman):
    pacman["absent"] = {"waybar", "impala"}
    assert deps.missing(["gtk4", "waybar", "impala"]) == {"waybar", "impala"}
    assert pacman["calls"] == [["pacman", "-T", "gtk4", "waybar", "impala"]]


def test_missing_without_pacman_treats_all_as_absent(monkeypatch):
    monkeypatch.setattr(core, "run", lambda args, timeout=10: None)
    assert deps.missing(["gtk4"]) == {"gtk4"}


def test_missing_empty_list_does_not_run_pacman(pacman):
    assert deps.missing([]) == set() and pacman["calls"] == []


def test_install_command_uses_polkit_and_needed():
    assert deps.install_command(["waybar"]) == ["pkexec", "pacman", "-S", "--needed", "--noconfirm", "waybar"]


def test_cli_lists_groups_and_missing(pacman, capsys):
    deps.main(["--group", "required"])
    assert capsys.readouterr().out.split() == ["python-gobject", "gtk4", "libadwaita", "gettext"]
    pacman["absent"] = {"waybar"}
    deps.main(["--missing", "--group", "optional"])
    assert capsys.readouterr().out.split() == ["waybar"]
    deps.main(["--missing"])
    assert capsys.readouterr().out.split() == ["waybar"]


def test_cli_exclude_keeps_waybar_out_of_deps(pacman, capsys):
    pacman["absent"] = {"waybar", "impala"}
    deps.main(["--missing", "--group", "optional", "--exclude", "waybar"])
    assert capsys.readouterr().out.split() == ["impala"]
