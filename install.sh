#!/usr/bin/env bash
# Instala o omarchy-settings para o usuário atual (sem sudo, sem pip).
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$HOME/.local/share/omarchy-settings"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"

if ! python3 -c 'import gi; gi.require_version("Adw", "1"); gi.require_version("Gtk", "4.0")' 2>/dev/null; then
  echo "Dependências ausentes. Instale com:"
  echo "  sudo pacman -S --needed python-gobject gtk4 libadwaita"
  exit 1
fi

mkdir -p "$APP_DIR" "$BIN_DIR" "$DESKTOP_DIR"
rm -rf "$APP_DIR/omarchy_settings"
cp -r "$SRC/omarchy_settings" "$APP_DIR/"
find "$APP_DIR" -name __pycache__ -type d -prune -exec rm -rf {} +

# Traduções: po/<idioma>.po -> omarchy_settings/locale/<idioma>/LC_MESSAGES/omarchy-settings.mo
if command -v msgfmt >/dev/null; then
  for po in "$SRC"/po/*.po; do
    lang=$(basename "$po" .po)
    for dest in "$SRC/omarchy_settings" "$APP_DIR/omarchy_settings"; do
      mkdir -p "$dest/locale/$lang/LC_MESSAGES"
      msgfmt -o "$dest/locale/$lang/LC_MESSAGES/omarchy-settings.mo" "$po"
    done
    # pt_PT e outras variantes sem catálogo próprio usam o português do Brasil
    if [[ $lang == pt_BR ]]; then
      for dest in "$SRC/omarchy_settings" "$APP_DIR/omarchy_settings"; do
        mkdir -p "$dest/locale/pt/LC_MESSAGES"
        cp "$dest/locale/pt_BR/LC_MESSAGES/omarchy-settings.mo" "$dest/locale/pt/LC_MESSAGES/"
      done
    fi
  done
else
  echo "Aviso: msgfmt (pacote gettext) não encontrado; a interface ficará só em inglês."
fi

cat > "$BIN_DIR/omarchy-settings" <<EOF
#!/usr/bin/env bash
exec env PYTHONPATH="$APP_DIR" python3 -m omarchy_settings "\$@"
EOF
chmod +x "$BIN_DIR/omarchy-settings"

install -m 644 "$SRC/data/org.omarchy.Settings.desktop" "$DESKTOP_DIR/"
command -v update-desktop-database >/dev/null && update-desktop-database "$DESKTOP_DIR" || true

echo "Instalado. Rode 'omarchy-settings' ou procure por 'Omarchy Settings' no launcher."
case ":$PATH:" in *":$BIN_DIR:"*) ;; *) echo "Aviso: $BIN_DIR não está no PATH." ;; esac
