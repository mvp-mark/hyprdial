"""Interface translation with gettext.

The language follows the system (LANGUAGE, LC_ALL, LC_MESSAGES, LANG). Source strings are in English, which is
also the fallback when there is no catalog for the system language. Catalogs live in omarchy_settings/locale and
are compiled from po/*.po by install.sh.
"""
from __future__ import annotations

import gettext
import locale
from pathlib import Path

DOMAIN = "omarchy-settings"
LOCALE_DIR = Path(__file__).parent / "locale"

try:
    locale.setlocale(locale.LC_ALL, "")  # dates and numbers in the system format
except locale.Error:
    pass

_translation = gettext.translation(DOMAIN, LOCALE_DIR, fallback=True)
_ = _translation.gettext
ngettext = _translation.ngettext
