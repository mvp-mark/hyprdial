"""Settings search: matching and ranking (no GTK, testable). The window collects the entries from its rows."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field

MAX_RESULTS = 60


@dataclass
class Entry:
    title: str
    subtitle: str
    page: str  # page name in the stack
    page_title: str
    group: str
    widget: object = field(default=None, compare=False, repr=False)


def fold(text: str) -> str:
    """Lowercase without accents, so "configuracao" finds "Configuração"."""
    return "".join(c for c in unicodedata.normalize("NFD", text.casefold()) if unicodedata.category(c) != "Mn")


def rank(entry: Entry, words: list[str]) -> int | None:
    """Lower is better; None if some word is missing. Title matches beat subtitle and group matches."""
    title, rest = fold(entry.title), fold(f"{entry.subtitle} {entry.group} {entry.page_title}")
    score = 0
    for word in words:
        if title.startswith(word):
            continue
        if f" {word}" in f" {title}":
            score += 1
        elif word in title:
            score += 2
        elif word in rest:
            score += 4
        else:
            return None
    return score


def search(entries: list[Entry], query: str, limit: int = MAX_RESULTS) -> list[Entry]:
    words = fold(query).split()
    if not words:
        return []
    scored = [(s, i, e) for i, e in enumerate(entries) if (s := rank(e, words)) is not None]
    return [e for _s, _i, e in sorted(scored, key=lambda t: (t[0], t[1]))][:limit]


def unique(entries: list[Entry]) -> list[Entry]:
    """Drops repeated (title, subtitle, page, group) entries, keeping the first."""
    seen, result = set(), []
    for e in entries:
        key = (e.title, e.subtitle, e.page, e.group)
        if key not in seen:
            seen.add(key)
            result.append(e)
    return result
