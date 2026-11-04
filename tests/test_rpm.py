import re
from pathlib import Path

from hyprdial import __version__
from hyprdial.deps import dependencies

SPEC = (Path(__file__).parent.parent / "packaging" / "rpm" / "hyprdial.spec").read_text()


def requires(kind: str, section: str) -> set[str]:
    """Requires or Recommends in the Fedora (else) or openSUSE (if) branch."""
    suse, _sep, fedora = SPEC.partition("%else")
    text = suse.rpartition("%if")[2] if section == "suse" else fedora.partition("%endif")[0]
    common = SPEC.partition("%if")[0]
    return set(re.findall(rf"^{kind}:\s+(.+?)\s*$", text + common, re.MULTILINE))


def names(family: str, group: str) -> set[str]:
    return {d.package for d in dependencies(family) if d.group == group}


def test_version_matches_the_app():
    assert re.search(r"^Version:\s+(\S+)", SPEC, re.MULTILINE).group(1) == __version__


def test_fedora_requires_follow_deps_py(plain_hyprland):  # Omarchy (and its Waybar option) is Arch-only
    assert requires("Requires", "fedora") == (names("fedora", "required") - {"gettext"}) | {"python3"}
    assert requires("Recommends", "fedora") == names("fedora", "optional")


def test_opensuse_requires_the_same_typelibs():
    # openSUSE packages provide typelib(Gtk) = 4.0 and so on; deps.py names the packages that provide them
    assert requires("Requires", "suse") == {"python3", "python3-gobject", "typelib(Gtk) = 4.0", "typelib(Adw) = 1"}
    assert requires("Recommends", "suse") == {"typelib(NM) = 1.0"}
    assert {"typelib-1_0-Gtk-4_0", "typelib-1_0-Adw-1"} <= names("suse", "required")
