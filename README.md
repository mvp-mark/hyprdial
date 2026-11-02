# omarchy-settings

[![tests](https://github.com/mvp-mark/omarchy-settings/actions/workflows/tests.yml/badge.svg)](https://github.com/mvp-mark/omarchy-settings/actions/workflows/tests.yml)

Graphical settings app for [Omarchy](https://omarchy.org), built with GTK4 + libadwaita (Python).

**Requires Omarchy with the Lua-based Hyprland configuration** (`~/.config/hypr/hyprland.lua`, Hyprland 0.5x)
and the Omarchy shell. Older installs that use `hyprland.conf` and Waybar are not supported.

## Pages

| Page | What it does | How it applies changes |
|---|---|---|
| Themes | Theme gallery with previews and color swatches, search and dark/light filter, current theme highlighted; all wallpapers of the current theme (yours included) with the one in use marked | `omarchy-theme-set`, `omarchy-theme-bg-set`, `omarchy-theme-bg-next` |
| Hyprland | Quick styles (Compact, Omarchy, Comfortable, Elegant); window layout, gaps, border, corners, opacity, dimming, blur, shadow, animations; keyboard layout and key repeat; mouse speed, acceleration, scrolling and focus; touchpad; pointer and workspace behavior. A ↶ button per option returns it to Omarchy's default | `hyprctl eval` live + generated file |
| Displays | Drag-and-drop arrangement (snaps to edges); per display: enable/disable, resolution and refresh rate, scale, rotation, position, VRR, mirroring, 10-bit color, brightness (DDC/CI); text size | `hyprctl eval` live + generated file (asks for confirmation and reverts after 15 s), `omarchy-brightness-display`, `omarchy-display-text-size` |
| Sound | Output and input device (the default one), their volume and mute, volume above 100% (optional), a test sound; volume and mute of each app playing and of each app using the microphone; updates live; full mixer (wiremix) for profiles and moving an app to another device | `pactl` (PipeWire), `pactl subscribe` for live updates, `pw-play` |
| Power | Power profile (power saver, balanced, performance; only those the machine offers); night light on/off, warmth and a daily schedule; what the power button does (system menu, lock, suspend, shut down, nothing); screensaver, lock and "stay awake" | `omarchy-powerprofiles-set` (remembered like the bar does), `hyprctl hyprsunset`, `~/.config/hypr/hyprsunset.conf` profiles (backup at `hyprsunset.conf.omarchy-settings.bak`), `XF86PowerOff` shortcut in the generated file, `idle` in `~/.config/omarchy/shell.json`, `omarchy-toggle-idle` |
| Shortcuts | Every active shortcut, by category, searchable by name or key; change the key of an Omarchy shortcut (by recording the combination), disable it, restore it with ↶; your own shortcuts to open apps, run commands or open in the terminal; conflict warnings | `hyprctl binds` + parsing `default/hypr/bindings/*.lua`; `hl.unbind`/`o.bind` in the generated file, with reload and verification |
| Bar and fonts | Omarchy shell bar: show/hide, position, transparency, clock format; widgets per section (reorder, move between sections, remove, add); optional Waybar (see below); system font | `omarchy-bar`, `omarchy-plugin-enable/disable`, `omarchy-toggle-bar`, `omarchy-font-set` |
| Connectivity | Wired (Ethernet): status, link speed, address, gateway and DNS, plain-language diagnosis (no cable, 10 Mb/s link, no DHCP address), connect/disconnect, IPv4 automatic (DHCP) or manual, custom DNS, auto-connect; Wi-Fi: radio on/off, available networks with signal and security, connect (password asked in a dialog, hidden networks too), saved networks with IPv4/DNS settings and forget, impala for advanced cases; Bluetooth: on/off, paired devices with battery level, connect/disconnect, forget, search and pair (pairing codes shown or confirmed in a dialog), bluetui for advanced cases | `nmcli` (NetworkManager), libnm for saving Wi-Fi passwords (never on a command line), `/sys/class/net`, `bluetoothctl` (pairing through an interactive session with a KeyboardDisplay agent) |
| System | Time zone (searchable) and automatic time (NTP); system language (among those generated); default browser, terminal and editor (installed ones only); notifications: do not disturb and recent notifications; about this computer (Omarchy version, kernel, processor, memory) and "Update Omarchy" | `timedatectl`, `localectl` (both ask for the password through polkit), `omarchy default`, `omarchy-shell notifications`, `omarchy-update` in a floating terminal |

Press **Ctrl+F** (or the search button) to find any setting by name on every page: accents and case don't
matter, and choosing a result opens its page, expands what is around it and highlights it.

## How settings are stored

Nothing managed by Omarchy is modified. Hyprland, display, shortcut and power button settings go to
`~/.config/hypr/omarchy-settings.lua`, and **a single line** `require("hypr.omarchy-settings")` is inserted into
`~/.config/hypr/hyprland.lua` right before Omarchy's toggles (backup at `hyprland.lua.omarchy-settings.bak`), so
these values take priority over `monitors.lua`, `input.lua` and `looknfeel.lua`. Each page restores only its own
settings: "Restore defaults" on the Hyprland page, "Restore this display" and "Restore all shortcuts".
**☰ → Restore app defaults** empties the generated file at once (a copy is kept as
`omarchy-settings.lua.<date>.bak`, and the toast offers Undo). Shortcuts
are wrapped in `pcall`, so a broken shortcut can't take down the rest of the file.
The bar is changed through Omarchy's own commands, which talk to the running shell.

## Waybar (optional)

Omarchy now uses the Omarchy shell bar and no longer manages Waybar. The **Bar and fonts** page can still run
Waybar instead of it:

- **Use Waybar instead of the Omarchy bar** starts Waybar, hides the Omarchy bar and starts Waybar at login (an
  Omarchy `post-boot` hook). Turning it off stops Waybar and shows the Omarchy bar again.
- A starter `~/.config/waybar/config.jsonc` and `style.css` are created if they don't exist (existing files are
  never overwritten; "Restore Waybar files" recreates them and keeps the old ones as `.omarchy-settings.bak`).
- Colors follow the Omarchy theme: a user template (`~/.config/omarchy/themed/waybar.css.tpl`) is rendered by Omarchy
  on every theme change, `style.css` imports it, and a `theme-set` hook reloads Waybar.
- Position, restart and shortcuts to edit both files.

## Installation

```bash
./install.sh --deps   # installs missing dependencies (asks for your sudo password), then the app
omarchy-settings
```

| Option | What it does |
|---|---|
| `./install.sh` | Installs the app only (fails with a hint if a required dependency is missing) |
| `./install.sh --deps` | Installs missing required and optional dependencies first (except Waybar) |
| `./install.sh --dev` | Same as `--deps`, plus development tools (pytest) |
| `./install.sh --waybar` | Also installs Waybar; can be combined with the options above |

Dependencies, listed in `omarchy_settings/deps.py`:

| Group | Packages |
|---|---|
| Required | `python-gobject`, `gtk4`, `libadwaita` (>= 1.5), `gettext` |
| Optional | `impala`, `bluetui`, `wiremix` (TUIs opened by the Connectivity and Sound pages), `waybar` |
| Development | `python-pytest` |

Waybar is offered as an optional alternative bar only: Omarchy uses the Omarchy shell bar, and installing Waybar
doesn't start it or replace the current bar.

Dependencies can also be installed from inside the app: **☰ → Dependencies** shows what's installed and installs
the selected packages, asking for your password through polkit.

To try it without installing: `python3 -m omarchy_settings` from the project folder.

## Language

The interface follows the system language (`LANGUAGE`, `LC_ALL`, `LC_MESSAGES`, `LANG`). Source strings are in
English, which is also the fallback when there is no translation; a Brazilian Portuguese translation is included
(`po/pt_BR.po`) and is also used for other Portuguese variants. Dates follow the system's regional format
(`LC_TIME`). To try another language without changing the system: `LANGUAGE=pt_BR omarchy-settings`.

`install.sh` compiles the catalogs with `msgfmt` (`gettext` package). To update or add a language:

```bash
xgettext --language=Python --keyword=_ --keyword=ngettext:1,2 --from-code=UTF-8 \
  -o po/omarchy-settings.pot $(find omarchy_settings -name '*.py')
msgmerge -U po/pt_BR.po po/omarchy-settings.pot       # update an existing translation
msginit -i po/omarchy-settings.pot -l de -o po/de.po  # or create a new one
./install.sh
```

Omarchy's shortcut names are shown as Omarchy itself writes them (in English).

## Tests

```bash
./install.sh --dev    # or: sudo pacman -S --needed python-pytest
python3 -m pytest
```

They cover the non-UI parts (`core.py`, `layout.py`, `keybinds.py`, `deps.py`, `themes_data.py`, `waybar.py`, `network.py`, `wifi.py`, `bluetooth.py`, `sound.py`, `power.py`, `system.py`, `search.py`) without touching the running Hyprland, and
the translations: every marked string has a translation, no translation is left unused, and the placeholders
(`{name}`…) match between English and the translation.
`tests/fixtures/` holds trimmed copies of Omarchy's shortcut files; an extra test reads the real files (skipped if
Omarchy isn't installed) and fails if an update changes their format.

## Layout

```
omarchy_settings/
  core.py            running commands and editing the configs (no GTK, testable)
  deps.py            dependency list and check (no GTK; also used by install.sh)
  themes_data.py     themes, previews, colors and wallpapers (no GTK)
  waybar.py          optional Waybar: starter files, theme colors, hooks, start/stop (no GTK)
  keybinds.py        shortcuts: parsing the Lua sources, matching and generation (no GTK)
  layout.py          display arrangement geometry: snapping and overlap (no GTK)
  network.py         wired connections through nmcli: state, profiles, validation, commands (no GTK)
  wifi.py            Wi-Fi through nmcli: radio, scan, saved networks, commands (no GTK)
  bluetooth.py       Bluetooth through bluetoothctl: devices, scan, commands, pairing output parser (no GTK)
  sound.py           output/input devices and app streams through pactl (no GTK)
  power.py           power profile, night light and its schedule, power button (no GTK)
  system.py          date and time, language, default apps, notifications, system info (no GTK)
  search.py          settings search: accent-insensitive matching and ranking (no GTK)
  i18n.py            translation (gettext) in the system language
  ui.py              widget helpers
  app.py             main window
  pages/             themes, hyprland, monitors, sound, power, shortcuts, bar, connectivity, system, search
data/                .desktop
po/                  template (.pot) and translations (.po)
tests/               pytest + fixtures
install.sh
```

## Next steps

- More **default apps** (file manager; apps for PDFs and images).
- Changing the key of shortcuts Omarchy generates in loops (workspaces 1–0, group windows, bar panels); today
  they can only be disabled.
- Removing a single Spacer from the bar (today removal applies to all of them).
- Packaging (PKGBUILD/AUR) and more languages.
