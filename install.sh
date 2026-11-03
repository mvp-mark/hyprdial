#!/usr/bin/env bash
# Installs omarchy-settings for the current user (no pip).
#   ./install.sh          installs the app
#   ./install.sh --deps   first installs missing dependencies (required and optional, except Waybar)
#   ./install.sh --dev    same as --deps, plus development tools (pytest)
#   ./install.sh --waybar also installs Waybar (alternative bar; combines with the other options)
# The dependency list lives in omarchy_settings/deps.py.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$HOME/.local/share/omarchy-settings"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"

deps() {
  PYTHONPATH="$SRC" python3 -m omarchy_settings.deps "$@"
}

usage() {
  cat <<'USAGE'
Usage: ./install.sh [--deps] [--dev] [--waybar]

  (no option)  install the app for the current user
  --deps       first install missing required and optional dependencies (except Waybar)
  --dev        same as --deps, plus development tools (pytest)
  --waybar     also install Waybar, an optional alternative bar (Omarchy itself doesn't use it)
USAGE
}

groups=()
with_waybar=0
for arg in "$@"; do
  case "$arg" in
    --deps) groups+=(required optional) ;;
    --dev) groups+=(required optional dev) ;;
    --waybar) with_waybar=1 ;;
    -h | --help) usage; exit 0 ;;
    *) echo "Unknown option: $arg (see --help)" >&2; exit 1 ;;
  esac
done

if (( ${#groups[@]} || with_waybar )); then
  missing=()
  for group in $(printf '%s\n' "${groups[@]}" | sort -u); do
    mapfile -t -O "${#missing[@]}" missing < <(deps --missing --group "$group" --exclude waybar)
  done
  if (( with_waybar )); then
    mapfile -t -O "${#missing[@]}" missing < <(deps --missing --group optional | grep -x waybar)
  fi
  if (( ${#missing[@]} )); then
    echo "Installing: ${missing[*]}"
    sudo pacman -S --needed "${missing[@]}"
  else
    echo "All dependencies are already installed."
  fi
fi

if ! python3 -c 'import gi; gi.require_version("Adw", "1"); gi.require_version("Gtk", "4.0")' 2>/dev/null; then
  echo "Missing dependencies: $(deps --missing --group required | paste -sd' ')"
  echo "Install them with: ./install.sh --deps"
  exit 1
fi

if pacman -Q omarchy-settings-gui &>/dev/null; then
  echo "Note: the omarchy-settings-gui package is installed too. This copy in $BIN_DIR comes first in PATH, so the"
  echo "launcher will open it instead of the package's. To keep only the package, remove this copy with:"
  echo "  rm -r $APP_DIR $BIN_DIR/omarchy-settings"
fi

mkdir -p "$APP_DIR" "$BIN_DIR" "$DESKTOP_DIR"
rm -rf "$APP_DIR/omarchy_settings"
cp -r "$SRC/omarchy_settings" "$APP_DIR/"
find "$APP_DIR" -name __pycache__ -type d -prune -exec rm -rf {} +

# Translations: po/<lang>.po -> omarchy_settings/locale/<lang>/LC_MESSAGES/omarchy-settings.mo
if command -v msgfmt >/dev/null; then
  for po in "$SRC"/po/*.po; do
    lang=$(basename "$po" .po)
    for dest in "$SRC/omarchy_settings" "$APP_DIR/omarchy_settings"; do
      mkdir -p "$dest/locale/$lang/LC_MESSAGES"
      msgfmt -o "$dest/locale/$lang/LC_MESSAGES/omarchy-settings.mo" "$po"
    done
    # pt_PT and other variants without their own catalog use Brazilian Portuguese
    if [[ $lang == pt_BR ]]; then
      for dest in "$SRC/omarchy_settings" "$APP_DIR/omarchy_settings"; do
        mkdir -p "$dest/locale/pt/LC_MESSAGES"
        cp "$dest/locale/pt_BR/LC_MESSAGES/omarchy-settings.mo" "$dest/locale/pt/LC_MESSAGES/"
      done
    fi
  done
else
  echo "Warning: msgfmt (gettext package) not found; the interface will be English only."
fi

cat > "$BIN_DIR/omarchy-settings" <<EOF
#!/usr/bin/env bash
exec env PYTHONPATH="$APP_DIR" python3 -m omarchy_settings "\$@"
EOF
chmod +x "$BIN_DIR/omarchy-settings"

install -m 644 "$SRC/data/org.omarchy.Settings.desktop" "$DESKTOP_DIR/"
command -v update-desktop-database >/dev/null && update-desktop-database "$DESKTOP_DIR" || true

echo "Installed. Run 'omarchy-settings' or search for 'Omarchy Settings' in the launcher."
echo "Optional dependencies (Wi-Fi/Bluetooth/mixer TUIs, Waybar) can be installed from the app's ☰ → Dependencies."
case ":$PATH:" in *":$BIN_DIR:"*) ;; *) echo "Warning: $BIN_DIR is not in PATH." ;; esac
