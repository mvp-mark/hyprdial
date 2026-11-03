"""Builds the main window with every page against fake commands, visits each page, and exits 1 on any Python
error raised in a GTK callback (those are printed, not raised, so a page can break without a test noticing).

    python tests/smoke_pages.py missing|empty

missing: no command is installed; empty: every command exists and prints nothing.
tests/test_pages_smoke.py runs it under a headless Broadway display, with HOME pointing at an empty folder.
"""

import subprocess
import sys
import threading
import traceback

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib  # noqa: E402

from omarchy_settings import core  # noqa: E402

mode = sys.argv[1]
errors: list[str] = []


def fake_run(args, timeout=10):
    return subprocess.CompletedProcess(args, 1 if mode == "missing" else 0, "", "")


def no_process(*_args, **_kwargs):
    raise OSError("no processes in the smoke test")


core.run = fake_run
core.out = lambda args, timeout=10: ""
core.have = lambda cmd: mode == "empty"
core.spawn = lambda args: False

from omarchy_settings.app import PAGES, Window  # noqa: E402

shown: list[str] = []


def collect_errors() -> None:
    """From here on, errors in GTK callbacks are collected instead of only printed (an import error still stops
    the script with its traceback)."""
    sys.excepthook = lambda kind, value, tb: errors.append("".join(traceback.format_exception(kind, value, tb)))
    threading.excepthook = lambda a: errors.append(
        "".join(traceback.format_exception(a.exc_type, a.exc_value, a.exc_traceback))
    )


def activate(app: Adw.Application) -> None:
    collect_errors()
    subprocess.Popen = no_process  # long-lived watchers (pactl subscribe, bluetoothctl)
    win = Window(app)
    win.store.save = lambda: errors.append("a page saved settings while only being shown")
    win.present()
    names = [name for _section, name, _title, _icon, _page in PAGES]

    def step() -> bool:
        if names:
            shown.append(names[0])
            win.show_page(names.pop(0))
            return True
        app.quit()
        return False

    def start() -> bool:  # after the pages' first background loads
        GLib.timeout_add(250, step)
        return False

    GLib.timeout_add(1000, start)


app = Adw.Application(application_id="org.omarchy.SettingsSmoke", flags=Gio.ApplicationFlags.NON_UNIQUE)
app.connect("activate", activate)
status = app.run([])
if len(shown) != len(PAGES):
    errors.append(f"only {len(shown)} of {len(PAGES)} pages were shown (exit status {status})")
if errors:
    print("\n".join(errors), file=sys.stderr)
    sys.exit(1)
print(f"{len(PAGES)} pages, no errors ({mode})")
