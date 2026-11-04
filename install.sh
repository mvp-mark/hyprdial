#!/usr/bin/env bash
# Installs Hyprdial for the current user (no pip).
#   ./install.sh          installs the app
#   ./install.sh --deps   first installs missing dependencies (required and optional, except Waybar)
#   ./install.sh --dev    same as --deps, plus development tools (pytest)
#   ./install.sh --waybar also installs Waybar (alternative bar; combines with the other options)
# The dependency list lives in hyprdial/deps.py.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$HOME/.local/share/hyprdial"
OLD_APP_DIR="$HOME/.local/share/omarchy-settings"  # the app's old name
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"

deps() {
  PYTHONPATH="$SRC" python3 -m hyprdial.deps "$@"
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
    read -ra installer < <(deps --install-command) || true
    if (( ${#installer[@]} )); then
      echo "Installing: ${missing[*]}"
      sudo "${installer[@]}" "${missing[@]}"
    else
      echo "Unknown package manager; install these yourself (Arch names): ${missing[*]}" >&2
      exit 1
    fi
  else
    echo "All dependencies are already installed."
  fi
fi

if ! python3 -c 'import gi; gi.require_version("Adw", "1"); gi.require_version("Gtk", "4.0")' 2>/dev/null; then
  echo "Missing dependencies: $(deps --missing --group required | paste -sd' ')"
  echo "Install them with: ./install.sh --deps"
  exit 1
fi

for package in hyprdial omarchy-settings-gui; do
  if command -v pacman >/dev/null && pacman -Q "$package" &>/dev/null; then
    echo "Note: the $package package is installed too. This copy in $BIN_DIR comes first in PATH, so the"
    echo "launcher will open it instead of the package's. To keep only the package, remove this copy with:"
    echo "  rm -r $APP_DIR $BIN_DIR/hyprdial $BIN_DIR/omarchy-settings"
  fi
done

# A copy installed before the rename (its settings move by themselves when the app starts)
if [[ -d $OLD_APP_DIR ]]; then
  echo "Removing the copy installed under the old name (omarchy-settings)."
  rm -rf "$OLD_APP_DIR" "$DESKTOP_DIR/org.omarchy.Settings.desktop"
fi

mkdir -p "$APP_DIR" "$BIN_DIR" "$DESKTOP_DIR"
rm -rf "$APP_DIR/hyprdial"
cp -r "$SRC/hyprdial" "$APP_DIR/"
find "$APP_DIR" -name __pycache__ -type d -prune -exec rm -rf {} +

# Translations: po/<lang>.po -> hyprdial/locale/<lang>/LC_MESSAGES/hyprdial.mo
if command -v msgfmt >/dev/null; then
  for po in "$SRC"/po/*.po; do
    lang=$(basename "$po" .po)
    for dest in "$SRC/hyprdial" "$APP_DIR/hyprdial"; do
      mkdir -p "$dest/locale/$lang/LC_MESSAGES"
      msgfmt -o "$dest/locale/$lang/LC_MESSAGES/hyprdial.mo" "$po"
    done
    # pt_PT and other variants without their own catalog use Brazilian Portuguese
    if [[ $lang == pt_BR ]]; then
      for dest in "$SRC/hyprdial" "$APP_DIR/hyprdial"; do
        mkdir -p "$dest/locale/pt/LC_MESSAGES"
        cp "$dest/locale/pt_BR/LC_MESSAGES/hyprdial.mo" "$dest/locale/pt/LC_MESSAGES/"
      done
    fi
  done
else
  echo "Warning: msgfmt (gettext package) not found; the interface will be English only."
fi

cat > "$BIN_DIR/hyprdial" <<EOF
#!/usr/bin/env bash
exec env PYTHONPATH="$APP_DIR" python3 -m hyprdial "\$@"
EOF
chmod +x "$BIN_DIR/hyprdial"
ln -sf hyprdial "$BIN_DIR/omarchy-settings"  # the old command keeps working

install -m 644 "$SRC/data/io.github.mvp_mark.Hyprdial.desktop" "$DESKTOP_DIR/"
command -v update-desktop-database >/dev/null && update-desktop-database "$DESKTOP_DIR" || true

echo "Installed. Run 'hyprdial' or search for 'Hyprdial' in the launcher."
echo "Optional dependencies (Wi-Fi/Bluetooth/mixer TUIs, Waybar) can be installed from the app's ☰ → Dependencies."
case ":$PATH:" in *":$BIN_DIR:"*) ;; *) echo "Warning: $BIN_DIR is not in PATH." ;; esac
