import subprocess

from hyprdial import core, webapps


def write(directory, name, exec_line, icon="x"):
    (directory / f"{name}.desktop").write_text(
        f"[Desktop Entry]\nName={name}\nExec={exec_line}\nIcon={icon}\nType=Application\n"
    )


def test_lists_only_omarchy_web_apps(tmp_path):
    apps, icons = tmp_path / "apps", tmp_path / "icons"
    apps.mkdir()
    icons.mkdir()
    write(apps, "X", "omarchy-launch-webapp https://x.com/", icon="x")
    write(apps, "Zoom", "omarchy-webapp-handler zoom %u", icon="zoom")
    write(apps, "my site", 'omarchy-launch-webapp "https://example.com/a b"', icon="my-site")
    write(apps, "foot", "foot", icon="foot")
    (icons / "my-site.png").write_bytes(b"png")
    found = webapps.web_apps(apps, icons)
    assert [(a.name, a.url) for a in found] == [
        ("my site", "https://example.com/a b"),
        ("X", "https://x.com/"),
        ("Zoom", ""),
    ]
    assert found[0].icon == str(icons / "my-site.png") and found[1].icon == "x"


def test_check():
    existing = [webapps.WebApp("X", "X", "https://x.com", "x")]
    assert webapps.check("", "x.com", existing) == "name"
    assert webapps.check("a/b", "x.com", existing) == "slash"
    assert webapps.check("X", "x.com", existing) == "exists"
    assert webapps.check("Y", "has space.com", existing) == "url"
    assert webapps.check("Y", "javascript:alert(1)", existing) == "url"
    assert webapps.check("Y", "example.com", existing) is None  # Omarchy adds https://
    assert webapps.check("Y", "HTTPS://example.com", existing) is None


def test_commands(monkeypatch):
    calls = []
    monkeypatch.setattr(
        core,
        "run",
        lambda args, timeout=10: (
            calls.append(args) or subprocess.CompletedProcess(args, 1, "Error: Failed to download icon.\n", "")
        ),
    )
    assert webapps.install("Y", "example.com") == (False, "Error: Failed to download icon.")
    webapps.remove("Y")
    assert calls == [
        ["omarchy-webapp-install", "Y", "example.com", ""],
        ["env", "OMARCHY_REMOVE_NOTIFY=false", "omarchy-webapp-remove", "Y"],
    ]
