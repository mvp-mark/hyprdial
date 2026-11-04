import re
from pathlib import Path

from hyprdial import __version__, host
from hyprdial.deps import dependencies

PKGBUILD = (Path(__file__).parent.parent / "packaging" / "arch" / "PKGBUILD").read_text()


def array(name):
    body = re.search(rf"^{name}=\((.*?)\)$", PKGBUILD, re.S | re.M).group(1)
    return [item.split(":")[0] for item in re.findall(r"""['"]([^'"]+)['"]""", body)]


def packages(group):
    return {d.package for d in dependencies() if d.group == group}


def plain_packages(group):
    host._detected = "hyprland"
    try:
        return packages(group)
    finally:
        host._detected = "omarchy"


def test_dependencies_follow_deps_py():
    assert set(array("depends")) | set(array("makedepends")) == packages("required") | {"python"}
    assert array("makedepends") == ["gettext"]
    # one package for Omarchy and plain Hyprland: the optional dependencies of both
    assert set(array("optdepends")) == packages("optional") | plain_packages("optional")


def test_version_matches_the_app():
    assert re.search(r"^pkgver=(\S+)", PKGBUILD, re.M).group(1) == __version__


def test_srcinfo_matches_the_pkgbuild():
    srcinfo = (Path(__file__).parent.parent / "packaging" / "arch" / ".SRCINFO").read_text()
    fields = {}
    for line in srcinfo.splitlines():
        key, sep, value = line.strip().partition(" = ")
        if sep:
            fields.setdefault(key, []).append(value)
    for name in ("pkgver", "pkgrel"):
        assert fields[name] == [re.search(rf"^{name}=(\S+)", PKGBUILD, re.M).group(1)]
    assert fields["sha256sums"] == array("sha256sums")
    assert sorted(fields["depends"]) == sorted(array("depends"))


def test_name_differs_from_omarchys_own_package():
    # Omarchy's repository ships a package called omarchy-settings, which the omarchy package depends on
    assert re.search(r"^pkgname=(\S+)", PKGBUILD, re.M).group(1) == "hyprdial"
    assert "omarchy-settings" not in array("provides") + array("replaces")


def test_replaces_the_package_from_before_the_rename():
    assert array("replaces") == array("conflicts") == array("provides") == ["omarchy-settings-gui"]
