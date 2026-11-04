from hyprdial import search
from hyprdial.search import Entry


def entry(title, subtitle="", group="", page_title="Page"):
    return Entry(title, subtitle, "page", page_title, group)


ENTRIES = [
    entry("Gaps between windows", group="Windows"),
    entry("Night light", "Warmer screen", group="Night light", page_title="Power"),
    entry("Configuração do teclado", group="Teclado"),
    entry("Screensaver after", group="Idle"),
    entry("Lock the screen after", "Asks for the password", group="Idle"),
]


def test_fold_ignores_case_and_accents():
    assert search.fold("Configuração") == "configuracao"


def test_title_prefix_ranks_first():
    assert [e.title for e in search.search(ENTRIES, "screen")] == [
        "Screensaver after",
        "Lock the screen after",
        "Night light",
    ]


def test_every_word_must_match_and_accents_are_optional():
    assert [e.title for e in search.search(ENTRIES, "configuracao teclado")] == ["Configuração do teclado"]
    assert search.search(ENTRIES, "night bluetooth") == []


def test_group_and_page_titles_are_searched():
    assert [e.title for e in search.search(ENTRIES, "idle")] == ["Screensaver after", "Lock the screen after"]
    assert search.search(ENTRIES, "power")[0].title == "Night light"


def test_empty_query_and_limit():
    assert search.search(ENTRIES, "  ") == []
    assert len(search.search(ENTRIES * 30, "after", limit=5)) == 5


def test_unique():
    assert len(search.unique(ENTRIES + ENTRIES)) == len(ENTRIES)
