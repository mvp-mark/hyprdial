"""Every page builds and shows without Python errors (tests/smoke_pages.py), on a headless Broadway display."""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent


def gtk_available() -> bool:
    probe = "import gi; gi.require_version('Gtk', '4.0'); gi.require_version('Adw', '1')"
    return subprocess.run([sys.executable, "-c", probe], capture_output=True).returncode == 0


pytestmark = pytest.mark.skipif(
    not shutil.which("gtk4-broadwayd") or not gtk_available(), reason="needs gtk4-broadwayd and libadwaita"
)


@pytest.fixture(scope="module")
def display(tmp_path_factory):
    runtime = tmp_path_factory.mktemp("runtime")
    runtime.chmod(0o700)
    env = {"XDG_RUNTIME_DIR": str(runtime), "PATH": os.environ.get("PATH", "")}
    server = subprocess.Popen(["gtk4-broadwayd", ":42"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)
    yield {**env, "GDK_BACKEND": "broadway", "BROADWAY_DISPLAY": ":42"}
    server.terminate()
    server.wait()


@pytest.mark.parametrize("mode", ["missing", "empty"])
def test_every_page_shows_without_errors(display, tmp_path, mode):
    env = {
        **display,
        "HOME": str(tmp_path),  # no real configuration is read or written
        "PYTHONPATH": str(ROOT),
        "LANG": "C.UTF-8",
        "GSETTINGS_BACKEND": "memory",
        "NO_AT_BRIDGE": "1",
    }
    r = subprocess.run(
        [sys.executable, str(ROOT / "tests" / "smoke_pages.py"), mode],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert r.returncode == 0, r.stderr[-4000:]
