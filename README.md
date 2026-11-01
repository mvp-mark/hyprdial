# omarchy-settings

Interface gráfica de configuração para o [Omarchy](https://omarchy.org), em GTK4 + libadwaita (Python).

**Requer o Omarchy com a configuração do Hyprland em Lua** (`~/.config/hypr/hyprland.lua`, Hyprland 0.5x)
e o Omarchy shell. Instalações antigas, com `hyprland.conf` e Waybar, não são suportadas.

## Páginas

| Página | O que faz | Como aplica |
|---|---|---|
| Temas | Escolhe tema e wallpaper (com miniaturas) | `omarchy-theme-set`, `omarchy-theme-bg-next` |
| Hyprland | Estilos rápidos (Compacto, Omarchy, Confortável, Elegante); organização das janelas, espaços, borda, cantos, opacidade, escurecimento, desfoque, sombra, animações; layout e repetição do teclado; velocidade, aceleração, rolagem e foco do mouse; touchpad; comportamento do cursor e workspaces. Botão ↶ por opção volta ao padrão do Omarchy | `hyprctl eval` ao vivo + arquivo gerado |
| Monitores | Disposição arrastável com o mouse (encaixe pelas bordas); por monitor: ativar/desativar, resolução e taxa, escala, rotação, posição, VRR, espelhamento, cor de 10 bits, brilho (DDC/CI); luz noturna e tamanho do texto | `hyprctl eval` ao vivo + arquivo gerado (pede confirmação e reverte em 15 s), `omarchy-brightness-display`, `omarchy-toggle-nightlight`, `omarchy-display-text-size` |
| Atalhos | Todos os atalhos ativos, por categoria, com busca por nome ou tecla; mudar a tecla de um atalho do Omarchy (gravando a combinação), desativar, restaurar com ↶; atalhos próprios para abrir apps, rodar comandos ou abrir no terminal; aviso de conflito | `hyprctl binds` + leitura de `default/hypr/bindings/*.lua`; `hl.unbind`/`o.bind` no arquivo gerado, com recarga e verificação |
| Barra e fontes | Barra do Omarchy shell: mostrar/ocultar, posição, transparência, formato do relógio; widgets por seção (reordenar, mover entre seções, remover, adicionar); proteção de tela, bloqueio e "manter acordado"; fonte do sistema | `omarchy-bar`, `omarchy-plugin-enable/disable`, `omarchy-toggle-bar`, `omarchy-toggle-idle`, `idle` em `~/.config/omarchy/shell.json`, `omarchy-font-set` |
| Conectividade | Wi-Fi, Bluetooth e mixer (impala, bluetui, wiremix); volume e mudo; liga/desliga Bluetooth | `wpctl`, `bluetoothctl` |

## Como as configurações são gravadas

Nada que o Omarchy gerencia é modificado. Os ajustes do Hyprland, dos monitores e dos atalhos vão para
`~/.config/hypr/omarchy-settings.lua`, e **uma linha** `require("hypr.omarchy-settings")` é inserida em
`~/.config/hypr/hyprland.lua` logo antes dos toggles do Omarchy (backup em
`hyprland.lua.omarchy-settings.bak`), para que esses valores prevaleçam sobre `monitors.lua`, `input.lua`
e `looknfeel.lua`. Cada página restaura só o que é dela: "Restaurar padrões" na página Hyprland, "Restaurar
este monitor" e "Restaurar todos os atalhos". Atalhos ficam isolados com `pcall`, então um atalho com problema
não derruba o resto do arquivo.
A barra é alterada pelos próprios comandos do Omarchy, que conversam com o shell em execução.

## Instalação

```bash
sudo pacman -S --needed python-gobject gtk4 libadwaita   # libadwaita >= 1.5 para a confirmação de tela
sudo pacman -S --needed impala bluetui wiremix           # TUIs abertas pela página Conectividade
./install.sh
omarchy-settings
```

Para testar sem instalar: `python3 -m omarchy_settings` dentro da pasta do projeto.

## Idioma

A interface segue o idioma do sistema (`LANGUAGE`, `LC_ALL`, `LC_MESSAGES`, `LANG`). Os textos do código estão
em inglês, que também é o idioma usado quando não há tradução; há tradução para português do Brasil (`po/pt_BR.po`),
usada também por outras variantes de português. Datas seguem o formato regional do sistema (`LC_TIME`).
Para testar outro idioma sem mudar o sistema: `LANGUAGE=pt_BR omarchy-settings`.

O `install.sh` compila os catálogos com `msgfmt` (pacote `gettext`). Para atualizar ou adicionar um idioma:

```bash
xgettext --language=Python --keyword=_ --keyword=ngettext:1,2 --from-code=UTF-8 \
  -o po/omarchy-settings.pot $(find omarchy_settings -name '*.py')
msgmerge -U po/pt_BR.po po/omarchy-settings.pot     # atualiza uma tradução existente
msginit -i po/omarchy-settings.pot -l de -o po/de.po  # ou cria uma nova
./install.sh
```

Os nomes dos atalhos do Omarchy aparecem como o próprio Omarchy os escreve (em inglês).

## Testes

```bash
sudo pacman -S --needed python-pytest
python3 -m pytest
```

Cobrem as partes sem interface (`core.py`, `layout.py`, `keybinds.py`) sem tocar no Hyprland em execução, e as
traduções: todo texto marcado no código tem tradução, nenhuma tradução sobra sem uso e os marcadores (`{name}`…)
batem entre o inglês e a tradução.
`tests/fixtures/` tem cópias reduzidas dos arquivos de atalhos do Omarchy; um teste extra lê os arquivos reais
(pulado se o Omarchy não estiver instalado) e falha se uma atualização mudar o formato deles.

## Estrutura

```
omarchy_settings/
  core.py            execução de comandos e edição das configs (sem GTK, testável)
  keybinds.py        atalhos: leitura das fontes Lua, identificação e geração (sem GTK)
  layout.py          geometria da disposição de monitores: encaixe e sobreposição (sem GTK)
  i18n.py            tradução (gettext) no idioma do sistema
  ui.py              helpers de widgets
  app.py             janela principal
  pages/             themes, hyprland, monitors, shortcuts, bar, connectivity
data/                .desktop
po/                  template (.pot) e traduções (.po)
tests/               pytest + fixtures
install.sh
```

## Próximos passos

- Página de **aplicativos padrão** (navegador, terminal, editor, gerenciador de arquivos; apps para PDF e imagens).
- Trocar a tecla dos atalhos gerados em laço pelo Omarchy (workspaces 1–0, janelas de grupo, painéis da barra);
  hoje só dá para desativá-los.
- Remover uma única cópia do Espaçador da barra (hoje a remoção vale para todas).
- Se o app for publicado: empacotamento (PKGBUILD/AUR) e mais idiomas.
