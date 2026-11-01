"""Atalhos do Hyprland (sem GTK, testável).

Os atalhos ativos vêm de `hyprctl binds -j`, que no modo Lua não diz o que cada um faz. A ação é
recuperada lendo as chamadas o.bind(...) dos arquivos do Omarchy e do bindings.lua do usuário; só os
atalhos encontrados assim podem trocar de tecla. Qualquer atalho ativo pode ser desativado.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import core

OMARCHY_PATH = Path(os.environ.get("OMARCHY_PATH", "/usr/share/omarchy"))
DEFAULT_DIR = OMARCHY_PATH / "default" / "hypr" / "bindings"
USER_FILE = core.CONF_DIR / "hypr" / "bindings.lua"

MOD_BITS = [(64, "SUPER"), (1, "SHIFT"), (4, "CTRL"), (8, "ALT")]
MOD_ALIASES = {"SUPER": "SUPER", "MOD4": "SUPER", "WIN": "SUPER", "LOGO": "SUPER", "SHIFT": "SHIFT",
               "CTRL": "CTRL", "CONTROL": "CTRL", "ALT": "ALT", "MOD1": "ALT"}

CATEGORIES = {
    "applications": "Aplicativos",
    "tiling": "Janelas e workspaces",
    "utilities": "Utilitários e capturas",
    "clipboard": "Área de transferência",
    "media": "Mídia, volume e brilho",
    "voxtype": "Ditado por voz",
    "user": "Do seu bindings.lua",
    "other": "Outros",
}
CATEGORY_ORDER = list(CATEGORIES)

KINDS = [("launch", "Abrir aplicativo"), ("command", "Executar comando"), ("tui", "Abrir no terminal")]

KEY_NAMES = {
    "RETURN": "Enter", "SPACE": "Espaço", "ESCAPE": "Esc", "TAB": "Tab", "BACKSPACE": "Backspace",
    "DELETE": "Delete", "PRINT": "Print", "SLASH": "/", "COMMA": ",", "PERIOD": ".", "MINUS": "-",
    "EQUAL": "=", "LEFT": "←", "RIGHT": "→", "UP": "↑", "DOWN": "↓", "HOME": "Home", "END": "End",
    "XF86AUDIORAISEVOLUME": "Volume +", "XF86AUDIOLOWERVOLUME": "Volume −", "XF86AUDIOMUTE": "Mudo",
    "XF86AUDIOMICMUTE": "Mudo mic", "XF86MONBRIGHTNESSUP": "Brilho +", "XF86MONBRIGHTNESSDOWN": "Brilho −",
    "XF86AUDIOPLAY": "Play", "XF86AUDIOPAUSE": "Pausa", "XF86AUDIONEXT": "Próxima", "XF86AUDIOPREV": "Anterior",
}

# Códigos de tecla usados pelo Omarchy (posição física, independe do layout)
KEYCODES = {20: "-", 21: "=", 34: "[", 35: "]", 201: "Copilot"}


# ------------------------------------------------------------------ teclas
def split_keys(text: str) -> tuple[list[str], str]:
    """'SUPER + SHIFT + B' -> (['SUPER', 'SHIFT'], 'B'); modificadores na ordem canônica."""
    parts = [p.strip() for p in text.replace(",", "+").split("+") if p.strip()]
    if not parts:
        return [], ""
    mods = {MOD_ALIASES.get(p.upper(), p.upper()) for p in parts[:-1]}
    return [m for _, m in MOD_BITS if m in mods], parts[-1]


def join_keys(mods: list[str], key: str) -> str:
    return " + ".join([m for _, m in MOD_BITS if m in mods] + [key])


def canon(text: str) -> str:
    """Identidade de um atalho, independente da ordem dos modificadores e de maiúsculas."""
    mods, key = split_keys(text)
    return join_keys(mods, key.upper())


def from_modmask(modmask: int, key: str) -> str:
    return join_keys([name for bit, name in MOD_BITS if modmask & bit], key)


def key_label(key: str) -> str:
    """Nome amigável da tecla final; code:10..19 são as teclas 1..0 da fileira de números."""
    m = re.fullmatch(r"code:(\d+)", key)
    if m and 10 <= int(m.group(1)) <= 19:
        return str((int(m.group(1)) - 9) % 10)
    if m and int(m.group(1)) in KEYCODES:
        return KEYCODES[int(m.group(1))]
    name = KEY_NAMES.get(key.upper())
    if name:
        return name
    return key.upper() if len(key) == 1 else key[:1].upper() + key[1:]


def keycaps(text: str) -> list[str]:
    mods, key = split_keys(text)
    return [m.capitalize() if m != "CTRL" else "Ctrl" for m in mods] + [key_label(key)]


# ------------------------------------------------------------------ leitura das fontes Lua
def _skip(text: str, i: int) -> int | None:
    """Se uma string ou comentário Lua começa em i, devolve o índice logo depois dele."""
    if text.startswith("--[[", i):
        end = text.find("]]", i + 4)
        return len(text) if end < 0 else end + 2
    if text.startswith("--", i):
        end = text.find("\n", i)
        return len(text) if end < 0 else end
    if text.startswith("[[", i):
        end = text.find("]]", i + 2)
        return len(text) if end < 0 else end + 2
    if text[i] in "\"'":
        quote, j = text[i], i + 1
        while j < len(text) and text[j] != quote:
            j += 2 if text[j] == "\\" else 1
        return j + 1
    return None


def _args(text: str, i: int) -> tuple[list[str], int]:
    """Separa os argumentos de uma chamada começando logo após '('."""
    depth, start, args = 0, i, []
    while i < len(text):
        skipped = _skip(text, i)
        if skipped is not None:
            i = skipped
            continue
        c = text[i]
        if c in "([{":
            depth += 1
        elif c in ")]}":
            if depth == 0:
                args.append(text[start:i].strip())
                return args, i + 1
            depth -= 1
        elif c == "," and depth == 0:
            args.append(text[start:i].strip())
            start = i + 1
        i += 1
    return args, i


def find_binds(text: str) -> list[tuple[str, list[str]]]:
    """Chamadas o.bind(...) e o.bind_toggle(...) fora de strings e comentários."""
    calls, i = [], 0
    while i < len(text):
        skipped = _skip(text, i)
        if skipped is not None:
            i = skipped
            continue
        for name in ("o.bind_toggle(", "o.bind("):
            if text.startswith(name, i) and (i == 0 or not re.match(r"[\w.:]", text[i - 1])):
                args, i = _args(text, i + len(name))
                calls.append((name[:-1], args))
                break
        else:
            i += 1
    return calls


LUA_KEYWORDS = {"and", "break", "do", "else", "elseif", "end", "false", "for", "function", "goto", "if", "in",
                "local", "nil", "not", "or", "repeat", "return", "then", "true", "until", "while"}
# Nomes que existem em qualquer arquivo de configuração; o resto seria local do arquivo de origem.
GLOBAL_NAMES = {"hl", "o", "string", "table", "math", "os", "tostring", "tonumber", "ipairs", "pairs", "type",
                "print", "select", "unpack"}


def free_names(expr: str) -> set[str]:
    """Nomes que a expressão Lua usa sem declarar (ignora campos, chaves de tabela e locais declarados nela)."""
    code, i = [], 0
    while i < len(expr):  # tira strings e comentários
        skipped = _skip(expr, i)
        if skipped is not None:
            code.append(" ")
            i = skipped
        else:
            code.append(expr[i])
            i += 1
    text = "".join(code)
    declared, used = set(), set()
    for m in re.finditer(r"[A-Za-z_]\w*", text):
        name, before, after = m.group(), text[:m.start()].rstrip(), text[m.end():].lstrip()
        if name in LUA_KEYWORDS or before.endswith((".", ":")) and not before.endswith(".."):
            continue
        if re.search(r"\b(local|for)\s*$", before) or re.search(r"\bfunction\s*\([\w\s,]*$", before) \
                or re.search(r"\bfor\s+[\w\s,]*$", before):
            declared.add(name)  # local x / for x, y in / function(a, b)
        elif after.startswith("=") and not after.startswith("=="):
            if before.endswith(("{", ",")):
                continue  # chave de tabela: { omarchy = ... }
            declared.add(name)
        else:
            used.add(name)
    return used - declared - GLOBAL_NAMES


def lua_string(expr: str) -> str | None:
    m = re.fullmatch(r'"([^"\\]*)"|\'([^\'\\]*)\'', expr.strip())
    return None if m is None else (m.group(1) if m.group(1) is not None else m.group(2))


@dataclass
class SourceBind:
    keys: str
    desc: str | None
    action: str  # expressão Lua: dispatcher e, se houver, opções
    category: str

    @property
    def movable(self) -> bool:
        """A ação pode ser copiada para outro arquivo se não depende de nada local ao arquivo de origem."""
        return not free_names(self.action)


def parse_source(text: str, category: str) -> list[SourceBind]:
    result = []
    for name, args in find_binds(text):
        if len(args) < 3:
            continue
        keys, desc = lua_string(args[0]), lua_string(args[1])
        if keys is None:
            continue  # tecla calculada (ex.: dentro de um for)
        rest = ", ".join(args[2:])
        action = f'"omarchy-toggle-" .. {rest}' if name == "o.bind_toggle" else rest
        result.append(SourceBind(keys, desc, action, category))
    return result


def source_binds() -> list[SourceBind]:
    binds = []
    for path in sorted(DEFAULT_DIR.glob("*.lua")):
        try:
            binds += parse_source(path.read_text(), path.stem if path.stem in CATEGORIES else "other")
        except OSError:
            pass
    try:
        binds += parse_source(USER_FILE.read_text(), "user")
    except OSError:
        pass
    return binds


def live_binds() -> list[dict]:
    try:
        data = json.loads(core.out(["hyprctl", "binds", "-j"]))
    except (ValueError, TypeError):
        return []
    return [b for b in data if isinstance(b, dict) and not b.get("mouse") and not b.get("submap")] \
        if isinstance(data, list) else []


def guess_category(desc: str) -> str:
    d = desc.lower()
    if any(w in d for w in ("workspace", "window", "focus", "group", "monitor", "scratchpad")):
        return "tiling"
    return "other"


# ------------------------------------------------------------------ modelo da página
@dataclass
class Entry:
    keys: str  # tecla original (identidade do atalho)
    desc: str
    category: str
    action: str | None = None  # None = não dá para mudar de tecla, só desativar
    locked: str = ""  # por que não dá para mudar de tecla
    override: dict | None = None  # {} desativado, {"keys": ...} mudou de tecla
    extra: dict = field(default_factory=dict)

    @property
    def current_keys(self) -> str | None:
        if self.override is None:
            return self.keys
        return self.override.get("keys")


def empty_state() -> dict:
    return {"overrides": {}, "custom": []}


def live_keys(bind: dict, by_desc: dict) -> str | None:
    """Teclas de um atalho ativo. Atalhos por código de tecla (code:N) vêm sem 'key' do hyprctl:
    procura pela descrição nas fontes, ou reconstrói os gerados em laço (workspace N -> code:N+9)."""
    modmask = int(bind.get("modmask", 0))
    key = str(bind.get("key", ""))
    if key:
        return from_modmask(modmask, key)
    if bind.get("keycode"):
        return from_modmask(modmask, f"code:{bind['keycode']}")
    mods = tuple(name for bit, name in MOD_BITS if modmask & bit)
    src = by_desc.get((mods, bind.get("description")))
    if src:
        return src.keys
    m = re.search(r"\b(\d+)$", bind.get("description") or "")
    if m and 1 <= int(m.group(1)) <= 10:
        return from_modmask(modmask, f"code:{int(m.group(1)) + 9}")
    return None


def build_entries(live: list[dict], sources: list[SourceBind], state: dict) -> list[Entry]:
    overrides = state.get("overrides", {})
    by_canon: dict[str, SourceBind] = {}
    for s in sources:
        by_canon.setdefault(canon(s.keys), s)
    # teclas ocupadas por mudanças deste app; não aparecem como atalhos à parte
    taken = {canon(o["keys"]) for o in overrides.values() if o.get("keys")}
    taken |= {canon(c["keys"]) for c in state.get("custom", [])}

    by_desc = {(tuple(split_keys(s.keys)[0]), s.desc): s for s in sources}

    entries: dict[str, Entry] = {}
    for b in live:
        text = live_keys(b, by_desc)
        if text is None:
            continue
        c = canon(text)
        if c in taken or c in entries:
            continue
        src = by_canon.get(c)
        desc = b.get("description") or (src.desc if src else "") or text
        category = src.category if src else guess_category(desc)
        if src is None:
            entries[c] = Entry(text, desc, category, locked="Gerado em laço pelo Omarchy; só dá para desativar")
        elif not src.movable:
            entries[c] = Entry(src.keys, desc, category,
                               locked="Usa uma função interna do Omarchy; só dá para desativar")
        else:
            entries[c] = Entry(src.keys, desc, category, src.action)

    for orig, override in overrides.items():
        src = by_canon.get(canon(orig))
        entries[canon(orig)] = Entry(orig, override.get("desc") or (src.desc if src else orig),
                                     src.category if src else guess_category(override.get("desc", "")),
                                     action=override.get("action") or (src.action if src and src.movable else None),
                                     override=dict(override))
    return sorted(entries.values(), key=lambda e: (CATEGORY_ORDER.index(e.category), e.desc.lower()))


def custom_action(kind: str, command: str) -> str:
    if kind == "launch":
        return f"{{ launch = {core.lua(command)} }}"
    if kind == "tui":
        return f"{{ tui = {core.lua(command)} }}"
    return core.lua(command)


def render(state: dict) -> list[str]:
    """Linhas Lua: todos os unbinds primeiro, depois os binds; cada uma isolada com pcall."""
    overrides, custom = state.get("overrides", {}), state.get("custom", [])
    if not overrides and not custom:
        return []
    lines = ["", "-- Atalhos"]
    for orig in sorted(overrides):
        lines.append(f"pcall(function() hl.unbind({core.lua(orig)}) end)")
    for orig in sorted(overrides):
        o = overrides[orig]
        if o.get("keys") and o.get("action"):
            lines.append(f"pcall(function() o.bind({core.lua(o['keys'])}, {core.lua(o.get('desc') or '')}, "
                         f"{o['action']}) end)")
    for c in custom:
        lines.append(f"pcall(function() o.bind({core.lua(c['keys'])}, {core.lua(c['desc'])}, "
                     f"{custom_action(c['kind'], c['command'])}) end)")
    return lines
