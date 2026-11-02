import re
from pathlib import Path

from omarchy_settings import __version__
from omarchy_settings.deps import dependencies

PKGBUILD = (Path(__file__).parent.parent / "packaging" / "arch" / "PKGBUILD").read_text()


def array(name):
    body = re.search(rf"^{name}=\((.*?)\)$", PKGBUILD, re.S | re.M).group(1)
    return [item.split(":")[0] for item in re.findall(r"""['"]([^'"]+)['"]""", body)]


def packages(group):
    return {d.package for d in dependencies() if d.group == group}


def test_dependencies_follow_deps_py():
    assert set(array("depends")) | set(array("makedepends")) == packages("required") | {"python"}
    assert array("makedepends") == ["gettext"]
    assert set(array("optdepends")) == packages("optional")


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
