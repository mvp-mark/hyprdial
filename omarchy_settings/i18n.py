"""Tradução da interface com gettext.

O idioma segue o sistema (LANGUAGE, LC_ALL, LC_MESSAGES, LANG). Os textos do código estão em inglês, que
também é o idioma usado quando não há catálogo para o idioma do sistema. Os catálogos ficam em
omarchy_settings/locale e são compilados de po/*.po pelo install.sh.
"""
from __future__ import annotations

import gettext
import locale
from pathlib import Path

DOMAIN = "omarchy-settings"
LOCALE_DIR = Path(__file__).parent / "locale"

try:
    locale.setlocale(locale.LC_ALL, "")  # datas e números no formato do sistema
except locale.Error:
    pass

_translation = gettext.translation(DOMAIN, LOCALE_DIR, fallback=True)
_ = _translation.gettext
ngettext = _translation.ngettext
