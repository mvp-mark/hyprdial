import pytest

from hyprdial import distro


@pytest.mark.parametrize(
    "text, family",
    [
        ('NAME="Arch Linux"\nID=arch\n', "arch"),
        ('ID=cachyos\nID_LIKE="arch"\n', "arch"),
        ("ID=fedora\nVERSION_ID=43\n", "fedora"),
        ('ID="opensuse-tumbleweed"\nID_LIKE="opensuse suse"\n', "suse"),
        ("ID=ubuntu\nID_LIKE=debian\n", "debian"),
        ('ID=pop\nID_LIKE="ubuntu debian"\n', "debian"),
        ("ID=nixos\n", None),
        ("", None),
    ],
)
def test_family_from_os_release(tmp_path, text, family):
    path = tmp_path / "os-release"
    path.write_text(text)
    assert distro.family_of(distro.os_release(path)) == family


def test_missing_os_release(tmp_path):
    assert distro.os_release(tmp_path / "none") == {}


def test_manager_needs_its_command(commands):
    assert distro.manager("arch") is None
    commands.have = {"pacman"}
    assert distro.manager("arch").name == "pacman"
    assert distro.manager("fedora") is None
