import gettext
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
PO_DIR = ROOT / "po"
needs_gettext = pytest.mark.skipif(not shutil.which("msgfmt") or not shutil.which("xgettext"),
                                   reason="ferramentas do gettext não instaladas")


def unquote(line: str) -> str:
    body = line[line.index('"') + 1:line.rindex('"')]
    return re.sub(r"\\(.)", lambda m: {"n": "\n", "t": "\t"}.get(m.group(1), m.group(1)), body)


def parse_po(path: Path) -> list[dict]:
    """Entradas {campo: texto} de um .po (msgid, msgid_plural, msgstr, msgstr[0]...)."""
    entries, current, field = [], {}, None
    for line in path.read_text().splitlines() + [""]:
        if not line.strip():
            if current:
                entries.append(current)
            current, field = {}, None
        elif line.startswith("#"):
            continue
        elif line.startswith('"'):
            current[field] += unquote(line)
        else:
            field, _, rest = line.partition(" ")
            current[field] = unquote(rest)
    return [e for e in entries if e.get("msgid")]


def placeholders(text: str) -> set[str]:
    return set(re.findall(r"\{(\w*)[^}]*\}", text))


@pytest.mark.parametrize("po", sorted(PO_DIR.glob("*.po")), ids=lambda p: p.stem)
def test_placeholders_match(po):
    """Marcadores diferentes entre inglês e tradução quebrariam o .format() em tempo de execução."""
    for e in parse_po(po):
        for key, value in e.items():
            if not key.startswith("msgstr") or not value:
                continue
            source = e["msgid_plural"] if key not in ("msgstr", "msgstr[0]") else e["msgid"]
            assert placeholders(value) == placeholders(source), (key, e["msgid"], value)


@needs_gettext
@pytest.mark.parametrize("po", sorted(PO_DIR.glob("*.po")), ids=lambda p: p.stem)
def test_catalog_covers_every_message(po, tmp_path):
    """Todo texto marcado no código tem tradução, e nada traduzido sobra sem uso."""
    sources = sorted(str(p) for p in (ROOT / "omarchy_settings").rglob("*.py"))
    pot = tmp_path / "messages.pot"
    subprocess.run(["xgettext", "--language=Python", "--keyword=_", "--keyword=ngettext:1,2",
                    "--from-code=UTF-8", "-o", str(pot), *sources], check=True)
    wanted = {e["msgid"] for e in parse_po(pot)}
    have = {e["msgid"]: e for e in parse_po(po)}
    assert wanted - set(have) == set(), "sem tradução"
    assert set(have) - wanted == set(), "tradução sem uso no código"
    empty = [m for m, e in have.items() if not any(v for k, v in e.items() if k.startswith("msgstr"))]
    assert empty == []


@needs_gettext
def test_compiled_catalog_translates(tmp_path):
    mo = tmp_path / "pt_BR" / "LC_MESSAGES" / "omarchy-settings.mo"
    mo.parent.mkdir(parents=True)
    subprocess.run(["msgfmt", "--check", "-o", str(mo), str(PO_DIR / "pt_BR.po")], check=True)
    t = gettext.translation("omarchy-settings", tmp_path, languages=["pt_BR"])
    assert t.gettext("Themes") == "Temas"
    assert t.ngettext("{n} shortcut", "{n} shortcuts", 1).format(n=1) == "1 atalho"
    assert t.ngettext("{n} shortcut", "{n} shortcuts", 5).format(n=5) == "5 atalhos"


def test_unknown_language_falls_back_to_english():
    env = {**os.environ, "LANGUAGE": "xx", "LC_ALL": "C.UTF-8", "LANG": "C.UTF-8", "PYTHONPATH": str(ROOT)}
    out = subprocess.run([sys.executable, "-c", "from omarchy_settings.i18n import _; print(_('Themes'))"],
                         env=env, capture_output=True, text=True, check=True).stdout.strip()
    assert out == "Themes"
