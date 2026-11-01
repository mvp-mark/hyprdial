# omarchy-settings

Interface gráfica de configuração para o [Omarchy](https://omarchy.org), em GTK4 + libadwaita (Python).

## Páginas

| Página | O que faz | Como aplica |
|---|---|---|
| Temas | Escolhe tema e wallpaper (com miniaturas) | `omarchy-theme-set`, `omarchy-theme-bg-next` |
| Hyprland | Gaps, borda, arredondamento, blur, animações, teclado, mouse, touchpad, escala do monitor | `hyprctl keyword` ao vivo + arquivo gerado |
| Barra e fontes | Posição, visibilidade e reinício da Waybar; fonte do sistema | edita `config.jsonc` (com backup), `omarchy-font-set` |
| Conectividade | Wi-Fi, Bluetooth e mixer (impala, bluetui, wiremix); volume e mudo; liga/desliga Bluetooth | `wpctl`, `bluetoothctl` |

## Como as configurações são gravadas

Nada que o Omarchy gerencia é modificado. Os ajustes do Hyprland vão para
`~/.config/hypr/omarchy-settings.conf`, e **uma linha** `source = ...` é acrescentada ao fim de
`~/.config/hypr/hyprland.conf` (backup em `hyprland.conf.omarchy-settings.bak`), para que esses
valores tenham a palavra final. "Restaurar padrões" apaga os ajustes e recarrega o Hyprland.
O backup da Waybar fica em `config.jsonc.omarchy-settings.bak`.

## Instalação

```bash
sudo pacman -S --needed python-gobject gtk4 libadwaita   # requer libadwaita >= 1.4
./install.sh
omarchy-settings
```

Para testar sem instalar: `python3 -m omarchy_settings` dentro da pasta do projeto.

## Estrutura

```
omarchy_settings/
  core.py            execução de comandos e edição das configs (sem GTK, testável)
  ui.py              helpers de widgets
  app.py             janela principal
  pages/             themes, hyprland, bar, connectivity
data/                .desktop
install.sh
```

## Próximos passos sugeridos

Keybindings (editor de `bindings.conf`), regras de janela, tela de bloqueio/idle, página de
atualização do sistema e empacotamento como PKGBUILD/AUR.
