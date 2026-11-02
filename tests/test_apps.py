import subprocess

import pytest

from omarchy_settings import apps, core


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


def test_default_apps_only_installed(fake, tmp_path, monkeypatch):
    answers, _calls, have = fake
    (tmp_path / "firefox.desktop").write_text("")
    (tmp_path / "zen.desktop").write_text("")
    monkeypatch.setattr(apps, "APP_DIRS", [tmp_path])
    have.update({"foot", "nvim", "zeditor"})
    answers["omarchy default browser"] = "zen"
    answers["omarchy default terminal"] = "foot"
    answers["omarchy default editor"] = "zeditor"
    found = apps.default_apps()
    assert found["browser"] == ([("firefox", "Firefox"), ("zen", "Zen")], "zen")
    assert found["terminal"] == ([("foot", "Foot")], "foot")
    assert found["editor"] == ([("nvim", "Neovim"), ("zed", "Zed")], "zed")  # the command name maps back


DESKTOP = """[Desktop Entry]
Name={name}
MimeType={mime}
{extra}
[Desktop Action new]
Name=Ignored
"""


def write(directory, file, name, mime, extra=""):
    directory.mkdir(exist_ok=True)
    (directory / file).write_text(DESKTOP.format(name=name, mime=mime, extra=extra))


def test_mime_choices(fake, tmp_path):
    answers, _calls, _have = fake
    system, user = tmp_path / "system", tmp_path / "user"
    write(system, "org.gnome.Evince.desktop", "Document Viewer", "application/pdf;image/tiff;")
    write(system, "org.gnome.Papers.desktop", "Document Viewer", "application/pdf;")
    write(system, "helper.desktop", "Helper", "application/pdf;", "NoDisplay=true")
    write(system, "imv.desktop", "imv", "image/png;", "NoDisplay=true")
    write(user, "imv.desktop", "Image Viewer", "image/png;")  # the user's copy wins
    desktop = apps.desktop_apps([system, user])
    answers["xdg-mime query default application/pdf"] = "org.gnome.Evince.desktop"
    assert apps.mime_choices("pdf", desktop) == (
        [("org.gnome.Evince.desktop", "Document Viewer (Evince)"),
         ("org.gnome.Papers.desktop", "Document Viewer (Papers)")], "org.gnome.Evince.desktop")
    answers["xdg-mime query default application/pdf"] = "helper.desktop"  # hidden, but in use: listed
    assert ("helper.desktop", "Helper") in apps.mime_choices("pdf", desktop)[0]
    assert apps.mime_choices("images", desktop)[0] == [("imv.desktop", "Image Viewer")]


def test_set_mime_default_sets_every_type(fake):
    _answers, calls, _have = fake
    apps.set_mime_default("images", "imv.desktop")
    assert calls == [["xdg-mime", "default", "imv.desktop", "image/png", "image/jpeg", "image/webp", "image/gif"]]
