import subprocess

import pytest

from hyprdial import core, deps, distro


@pytest.fixture
def pacman(monkeypatch):
    """Fakes `pacman -T`: prints only the packages in the `absent` list."""
    state = {"absent": set(), "calls": []}

    def fake_run(args, timeout=10):
        state["calls"].append(args)
        out = "\n".join(p for p in args[2:] if p in state["absent"])
        return subprocess.CompletedProcess(args, 127 if out else 0, out + "\n" if out else "", "")

    monkeypatch.setattr(core, "run", fake_run)
    monkeypatch.setattr(core, "have", lambda cmd: True)
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
    monkeypatch.setattr(core, "have", lambda cmd: False)
    assert deps.missing(["gtk4"]) == {"gtk4"}
    assert not deps.can_install()


def test_missing_empty_list_does_not_run_pacman(pacman):
    assert deps.missing([]) == set() and pacman["calls"] == []


def test_install_command_uses_polkit_and_needed(pacman):
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


def names(family):
    return {d.package for d in deps.dependencies(family)}


def test_other_families_have_their_own_names_and_skip_arch_only_packages():
    assert {"python3-gi", "gir1.2-gtk-4.0", "gir1.2-adw-1", "gir1.2-nm-1.0", "gettext"} <= names("debian")
    assert {"python3-gobject", "gtk4", "libadwaita", "NetworkManager-libnm"} <= names("fedora")
    assert {"typelib-1_0-Gtk-4_0", "typelib-1_0-Adw-1", "gettext-tools"} <= names("suse")
    for family in ("debian", "fedora", "suse"):
        assert not names(family) & {"impala", "bluetui", "wiremix", "python-gobject"}
    assert names(None) == names("arch")  # unknown: Arch's names, for the user to translate


def test_waybar_is_listed_only_on_omarchy(plain_hyprland):
    assert "waybar" not in names("arch")


def test_fedora_and_suse_check_capabilities_with_rpm(commands, monkeypatch):
    monkeypatch.setattr(distro, "_family", "fedora")
    commands.have = {"dnf", "pkexec"}
    commands.answers["rpm -q --whatprovides gtk4 libadwaita"] = (
        "gtk4-4.18-1.fc43.x86_64\nno package provides libadwaita\n"
    )
    commands.codes["rpm -q --whatprovides gtk4 libadwaita"] = 1
    assert deps.missing(["gtk4", "libadwaita"]) == {"libadwaita"}
    assert deps.install_command(["libadwaita"]) == ["pkexec", "dnf", "install", "-y", "libadwaita"]
    assert deps.can_install()


def test_debian_checks_with_dpkg_query(commands, monkeypatch):
    monkeypatch.setattr(distro, "_family", "debian")
    commands.have = {"apt-get"}
    key = "dpkg-query -W -f=${Package} ${Status}\\n python3-gi gir1.2-adw-1 gettext"
    commands.answers[key] = "python3-gi install ok installed\ngettext deinstall ok config-files\n"
    assert deps.missing(["python3-gi", "gir1.2-adw-1", "gettext"]) == {"gir1.2-adw-1", "gettext"}
    assert not deps.can_install()  # no pkexec


def test_cli_install_command(commands, monkeypatch, capsys):
    commands.have = {"zypper"}
    monkeypatch.setattr(distro, "_family", "suse")
    deps.main(["--install-command"])
    assert capsys.readouterr().out.strip() == "zypper install"
    monkeypatch.setattr(distro, "_family", None)
    deps.main(["--install-command"])
    assert capsys.readouterr().out.strip() == ""
