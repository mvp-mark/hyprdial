from omarchy_settings import themes_data as td


def make_theme(root, slug, colors='mode = "dark"\naccent = "#112233"\n', preview=True):
    d = root / slug
    d.mkdir(parents=True)
    (d / "colors.toml").write_text(colors)
    if preview:
        (d / "preview.png").write_bytes(b"png")
    return d


def test_display_name_matches_omarchy_theme_list():
    assert td.display_name("catppuccin-latte") == "Catppuccin Latte"
    assert td.display_name("retro-82") == "Retro 82"


def test_user_theme_overlays_official(tmp_path):
    official, user = tmp_path / "official", tmp_path / "user"
    make_theme(official, "nord")
    overlay = user / "nord"
    overlay.mkdir(parents=True)
    (overlay / "colors.toml").write_text('mode = "light"\naccent = "#abcdef"\n')  # only overlays the colors
    make_theme(user, "mine", preview=False)
    themes = {t.slug: t for t in td.list_themes(user, official)}
    assert set(themes) == {"nord", "mine"}
    assert themes["nord"].preview == official / "nord" / "preview.png"
    assert themes["nord"].colors["accent"] == "#abcdef" and not themes["nord"].dark
    assert themes["nord"].user and themes["mine"].preview is None


def test_swatches_skip_missing_colors(tmp_path):
    make_theme(tmp_path, "t", 'background = "#000000"\naccent = "#ffffff"\nred = 3\n')
    (theme,) = td.list_themes(tmp_path / "none", tmp_path)
    assert theme.swatches() == ["#000000", "#ffffff"]


def test_broken_colors_file_is_ignored(tmp_path):
    make_theme(tmp_path, "t", "not = [valid")
    (theme,) = td.list_themes(tmp_path / "none", tmp_path)
    assert theme.colors == {} and theme.dark


def test_wallpapers_and_current(tmp_path):
    state, user_bgs = tmp_path / "state", tmp_path / "bgs"
    theme_bgs = state / "theme" / "backgrounds"
    theme_bgs.mkdir(parents=True)
    (state / "theme.name").write_text("nord\n")
    for name in ("2-b.jpg", "1-a.png", "notes.txt"):
        (theme_bgs / name).write_bytes(b"x")
    (user_bgs / "nord").mkdir(parents=True)
    (user_bgs / "nord" / "mine.webp").write_bytes(b"x")
    (state / "background").symlink_to(theme_bgs / "2-b.jpg")
    assert [p.name for p in td.wallpapers(state, user_bgs)] == ["mine.webp", "1-a.png", "2-b.jpg"]
    assert td.current_wallpaper(state) == (theme_bgs / "2-b.jpg").resolve()
    assert td.current_slug(state) == "nord"


def test_missing_state(tmp_path):
    assert td.current_slug(tmp_path) == "" and td.wallpapers(tmp_path, tmp_path) == []
    assert td.current_wallpaper(tmp_path) is None


def test_accent_from_the_current_theme(tmp_path):
    (tmp_path / "theme").mkdir()
    (tmp_path / "theme" / "colors.toml").write_text('accent = "#7D82D9"\nbackground = "#060B1E"\n')
    assert td.accent(tmp_path) == ("#7d82d9", "#000000")
    (tmp_path / "theme" / "colors.toml").write_text('accent = "blue"\n')
    assert td.accent(tmp_path) is None
    assert td.readable_on("#1e66f5") == "#ffffff" and td.readable_on("#f9e2af") == "#000000"
    assert "--accent-bg-color: #7d82d9" in td.accent_css(("#7d82d9", "#000000"))
