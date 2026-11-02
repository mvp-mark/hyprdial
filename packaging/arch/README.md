# Arch package

`PKGBUILD` builds the package from a release tag; `.SRCINFO` is its metadata in the format the AUR reads, made with
`makepkg --printsrcinfo` (`tests/test_pkgbuild.py` fails when the two disagree).

```bash
makepkg -si    # build and install from this folder
```

## Publishing on the AUR

Once:

1. Create an account at <https://aur.archlinux.org/register>.
2. Add your SSH **public** key under *My Account → SSH Public Key* (for example the contents of
   `~/.ssh/id_ed25519.pub`).
3. Check that the AUR knows you: `ssh aur@aur.archlinux.org help` should answer with a list of commands.

Then, for the first publication and every update:

```bash
packaging/arch/publish-aur.sh
```

It regenerates `.SRCINFO`, builds the package from the published tarball to make sure it works, clones the AUR
repository (empty the first time, which creates the `omarchy-settings` package) and pushes `PKGBUILD` and
`.SRCINFO`. The AUR repository's branch is `master`.

## A new release

1. Bump `__version__` in `omarchy_settings/__init__.py` and `pkgver` here (back to `pkgrel=1`, `sha256sums=('SKIP')`).
2. Commit, push, wait for CI, then tag: `git tag -a vX.Y.Z -m "omarchy-settings X.Y.Z" && git push origin vX.Y.Z`.
3. Pin the checksum of GitHub's tarball:
   `curl -sL https://github.com/mvp-mark/omarchy-settings/archive/refs/tags/vX.Y.Z.tar.gz | sha256sum`,
   put it in `sha256sums`, run `makepkg --printsrcinfo > .SRCINFO`, commit and push.
4. `packaging/arch/publish-aur.sh`.
