# RPM package (Fedora, openSUSE)

`hyprdial.spec` builds a `noarch` package from a release tag's tarball, with the dependencies of each family
(`tests/test_rpm.py` checks them against `hyprdial/deps.py`). CI builds it and installs it on Fedora and openSUSE
Tumbleweed on every push (`.github/workflows/tests.yml`, job `distros`).

Build it locally on Fedora or openSUSE:

```bash
sudo dnf install rpm-build rpmdevtools desktop-file-utils gettext   # zypper install … on openSUSE
spectool -g -R packaging/rpm/hyprdial.spec                           # downloads the tag's tarball
rpmbuild -ba packaging/rpm/hyprdial.spec
sudo dnf install ~/rpmbuild/RPMS/noarch/hyprdial-*.rpm
```

## Fedora: COPR

Once: create an account at <https://copr.fedorainfracloud.org>, put the API token from
<https://copr.fedorainfracloud.org/api/> in `~/.config/copr`, and create the project:

```bash
sudo dnf install copr-cli rpmdevtools
copr-cli create hyprdial --chroot fedora-rawhide-x86_64 --chroot fedora-43-x86_64
```

For each release (after the tag exists on GitHub):

```bash
spectool -g -R packaging/rpm/hyprdial.spec && rpmbuild -bs packaging/rpm/hyprdial.spec
copr-cli build hyprdial ~/rpmbuild/SRPMS/hyprdial-*.src.rpm
```

Users then install it with `sudo dnf copr enable <account>/hyprdial && sudo dnf install hyprdial`.

## openSUSE: OBS

Once: create an account at <https://build.opensuse.org>, install `osc`, and create the package in your home
project (`osc meta pkg -e home:<account> hyprdial`, adding the `openSUSE_Tumbleweed` repository).

For each release:

```bash
osc checkout home:<account>/hyprdial && cd home:<account>/hyprdial
cp <repo>/packaging/rpm/hyprdial.spec . && spectool -g hyprdial.spec
osc addremove && osc commit -m "Update to X.Y.Z"
```

## A new release

Bump `Version` (back to `Release: 1`) and add a `%changelog` entry together with `__version__` and the Arch
`pkgver` (see `packaging/arch/README.md`).
