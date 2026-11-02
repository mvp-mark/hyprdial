# Architecture

How omarchy-settings is put together, and the rules new code follows.

## Layers

```
pages/*.py     GTK only: builds rows, reacts to the user, shows results
ui.py          widgets and behaviors shared by the pages
<topic>.py     no GTK: reads state, validates input, runs commands, edits files
core.py        running commands (run/out/have/spawn) and the generated Hyprland file
```

- **Pages never run commands or touch files.** They call a topic module (`sound.py`, `power.py`, …), usually off
  the UI thread through `ui.bg(work, done)`, and show what comes back.
- **Topic modules have no GTK imports**, so they can be tested with a fake command runner. They return plain data
  (dataclasses, tuples, `(ok, message)`) instead of raising for expected failures.
- **Every command goes through `core.run`/`core.out`/`core.spawn`**, never `subprocess` directly, except for
  long-lived interactive processes (`bluetooth.PairSession`, `sound.Watcher`), which live in their topic module
  and report from a reader thread through a `dispatch` callback; pages pass `ui.on_ui_thread`.
- **Opening another app** (an editor, the browser, a terminal) is fine from a page, through `core.spawn`,
  `core.open_in_editor` or `ui.launch_tui`; reading or changing system state is not.
- `nm.py` saves Wi-Fi passwords through libnm. It needs PyGObject's NM bindings but no GTK, so it sits outside the
  unit tests, which run without PyGObject.

## Changing the system: Omarchy first

1. **An `omarchy …` command exists** (`omarchy theme set`, `omarchy toggle touchpad`, `omarchy default browser`,
   `omarchy webapp install`, …): use it. Omarchy keeps its own state, notifications and migrations consistent.
2. **No command, but a user config file**: edit it under `~/.config` (or `~/.local/state` where Omarchy keeps
   state), with a backup the first time when the file isn't ours.
3. **Hyprland settings** go to the generated `~/.config/hypr/omarchy-settings.lua` only, never into Omarchy's
   files. State lives in `~/.config/omarchy-settings/state.json`.
4. **Never edit `/usr/share/omarchy`.** Reading it to learn defaults and formats is fine.
5. **Anything that needs sudo runs in a visible terminal** (`omarchy-launch-floating-terminal-with-presentation`),
   so the password prompt is the system's own. polkit prompts (`timedatectl`, `localectl`, `pkexec pacman`) are
   fine from the window.
6. **Secrets never go on a command line** (Wi-Fi passwords go through libnm over D-Bus).

## Interface conventions

- **Apply right away** when a change is cheap and easy to undo (switches, sliders, choices). Sliders wait until
  the user stops moving (`ui.Debouncer`).
- **An Apply button** when a change is slow, needs a password or logging out (time zone, language).
- **Confirm first** (`ui.confirm`) when something is removed or hard to undo; offer **Undo** in the toast when
  undoing is possible.
- **Toasts** for results; errors say what failed in plain words.
- **Missing tools** show a row saying what to install (`ui.missing_row`), never a broken control.
- **Live state** (devices, networks, streams) refreshes only while the page is on screen (`ui.refresh_while_mapped`).
- Follow libadwaita's patterns (boxed lists, `Adw.PreferencesGroup`, `Adw.*Row`), with the current Omarchy theme's
  accent color.

## Translations

Source strings are English and marked with `_()`, `ngettext()` for plurals. `tests/test_i18n.py` fails when a
string has no Brazilian Portuguese translation or the placeholders don't match.

## Tests

- `tests/conftest.py` provides `commands`, a fake `core.run`/`out`/`have`: set `commands.answers["cmd args"]` to
  the output, `commands.codes[...]` to an exit code, `commands.have` to the commands that exist; check
  `commands.calls` for what ran.
- Pages are not unit tested; their logic belongs in topic modules, which are.
- Changes to the real system are tried by hand only when they are reversible, and undone right after.

## Tooling

- `ruff check` and `ruff format --check` (settings in `pyproject.toml`) and `pytest` run in CI on Arch Linux.

## Adding a page

1. A topic module with the logic and its tests.
2. A page in `pages/`, registered in `app.py` under its sidebar section.
3. Strings translated in `po/pt_BR.po`.
4. A row in the README's page table.
