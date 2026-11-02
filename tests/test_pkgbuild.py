import re
from pathlib import Path

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

