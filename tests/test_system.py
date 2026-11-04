import subprocess

import pytest

from hyprdial import core, distro, system


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
    assert cmd[0] == "omarchy-launch-floating-terminal-with-presentation"
    assert cmd[1] == r"sudo sed -i 's/^#\s\?\(pt_BR\.UTF-8 UTF-8\)/\1/' /etc/locale.gen && sudo locale-gen"
    with pytest.raises(ValueError):
        system.install_locale_command("pt_BR'; rm -rf ~")


def test_locale_description(tmp_path):
    (tmp_path / "pt_BR").write_text('LC_IDENTIFICATION\nlanguage   "Brazilian Portuguese"\nterritory  "Brazil"\n')
    assert system.locale_description("pt_BR.UTF-8", tmp_path) == "Brazilian Portuguese (Brazil)"
    assert system.locale_description("xx_YY.UTF-8", tmp_path) == ""


def test_app_location(monkeypatch, tmp_path):
    monkeypatch.setattr(system, "LOCAL_DIR", tmp_path / "local")
    assert system.app_location(system.PACKAGE_DIR / "hyprdial") == "package"
    assert system.app_location(tmp_path / "local" / "hyprdial") == "local"
    assert system.app_location(tmp_path / "checkout" / "hyprdial") == "source"


def test_other_copies(commands, monkeypatch, tmp_path):
    monkeypatch.setattr(system, "LOCAL_DIR", tmp_path)
    monkeypatch.setattr(system, "OLD_LOCAL_DIR", tmp_path / "old")
    commands.have = {"pacman"}
    commands.answers["pacman -T hyprdial"] = "hyprdial"  # pacman -T: not installed
    assert system.other_copies("local") == []
    commands.answers["pacman -T hyprdial"] = ""
    (tmp_path / "hyprdial").mkdir()
    assert system.other_copies("local") == ["package"]
    assert system.other_copies("package") == ["local"]
    assert system.other_copies("source") == ["package", "local"]
    (tmp_path / "old" / "omarchy_settings").mkdir(parents=True)  # install.sh before the rename
    assert system.other_copies("package") == ["local", "old"]


def test_latest_release(commands):
    assert system.latest_release() == ""  # offline
    commands.answers[f"curl -fsS --max-time 5 {system.LATEST_API}"] = '{"tag_name": "v0.6.0", "name": "x"}'
    assert system.latest_release() == "0.6.0"


def test_is_newer():
    assert system.is_newer("0.10.0", "0.9.1")
    assert not system.is_newer("0.5.3", "0.5.3")
    assert not system.is_newer("", "0.5.3")


def test_keyboard_layout(commands):
    assert system.keyboard_layout() == ""
    commands.answers["hyprctl getoption input:kb_layout -j"] = '{"option": "input:kb_layout", "str": "br,us"}'
    assert system.keyboard_layout() == "br"


@pytest.mark.parametrize(
    ("layout", "expected"),
    [("br", "pt_BR.UTF-8"), ("de", "de_DE.UTF-8"), ("us", ""), ("zz", ""), ("", ""), ("../x", "")],
)
def test_suggest_locale(layout, expected):
    names = ["de_DE.UTF-8", "hrx_BR.UTF-8", "pt_BR.UTF-8", "es_US.UTF-8"]
    assert system.suggest_locale(layout, names) == expected


def test_install_locale_command_on_plain_hyprland(commands, plain_hyprland):
    commands.have = {"kitty"}
    cmd = system.install_locale_command("pt_BR.UTF-8")
    assert cmd[:3] == ["kitty", "bash", "-c"]
    assert cmd[3].startswith("sudo sed -i") and cmd[3].endswith('read -rp "Press Enter to close"')


def test_package_removal(commands, monkeypatch):
    commands.have = {"dnf"}
    monkeypatch.setattr(distro, "_family", "fedora")
    assert system.package_removal() == "sudo dnf remove hyprdial"


def test_language_method(commands, monkeypatch, tmp_path):
    gen = tmp_path / "locale.gen"
    monkeypatch.setattr(system, "LOCALE_GEN", gen)
    commands.have = {"locale-gen", "dnf"}
    assert system.language_method() is None  # Arch without locale.gen: nothing to do
    gen.write_text("#pt_BR.UTF-8 UTF-8\n")
    assert system.language_method() == "locale-gen"
    gen.unlink()
    monkeypatch.setattr(distro, "_family", "fedora")
    assert system.language_method() == "langpack"
    commands.have = set()
    assert system.language_method() is None


@pytest.fixture
def fedora(commands, monkeypatch, tmp_path):
    monkeypatch.setattr(system, "LOCALE_GEN", tmp_path / "none")
    monkeypatch.setattr(distro, "_family", "fedora")
    commands.have = {"dnf", "kitty"}
    commands.answers["dnf repoquery --qf %{name}\n glibc-langpack-*"] = (
        "glibc-langpack-de\nglibc-langpack-en\nglibc-langpack-pt\nglibc-langpack-ast\nglibc-all-langpacks\n"
    )
    return commands


def test_fedora_offers_langpacks_not_installed(fedora):
    assert system.installable(["en_US.utf8", "en_GB.utf8", "C.utf8"]) == ["ast", "de", "pt"]


def test_fedora_suggests_the_layouts_language(fedora):
    assert system.suggest_install("br", ["de", "pt"]) == "pt"
    assert system.suggest_install("de", ["de", "pt"]) == "de"
    assert system.suggest_install("us", ["de", "pt"]) == ""


def test_fedora_install_command(fedora, plain_hyprland):
    assert system.install_command("pt")[3].startswith("sudo dnf install -y glibc-langpack-pt;")
    with pytest.raises(ValueError):
        system.install_command("pt; rm -rf ~")


def test_installed_locale_after_installing():
    available = ["en_US.utf8", "pt_BR.utf8", "pt_PT.utf8"]
    assert system.installed_locale("pt_BR.UTF-8", available) == "pt_BR.utf8"
    assert system.installed_locale("de_DE.UTF-8", available) is None
    assert system.installed_locale("pt", available, "br") == "pt_BR.utf8"
    assert system.installed_locale("pt", available, "pt") == "pt_PT.utf8"
    assert system.installed_locale("pt", available) == "pt_BR.utf8"
    assert system.installed_locale("de", available) is None


def test_language_name(tmp_path):
    iso = tmp_path / "iso.json"
    iso.write_text(
        '{"639-3": [{"alpha_3": "por", "alpha_2": "pt", "name": "Portuguese"}, {"alpha_3": "ast", "name": "Asturian"}]}'
    )
    assert system.language_name("pt", iso) == "Portuguese"
    assert system.language_name("ast", iso) == "Asturian"
    assert system.language_name("xx", iso) == "" and system.language_name("pt", tmp_path / "none") == ""
