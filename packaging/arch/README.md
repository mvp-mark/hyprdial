# Arch package

`PKGBUILD` builds the package from a release tag; `.SRCINFO` is its metadata in the format the AUR reads, made with
`makepkg --printsrcinfo` (`tests/test_pkgbuild.py` fails when the two disagree).

The package is called **`hyprdial`** and replaces `omarchy-settings-gui`, its name before 1.0. It must never be
called `omarchy-settings`: that is a package in Omarchy's own repository (its defaults, fonts and helpers, required
by `omarchy`), and a package with that name would replace it. The command is `hyprdial`; `omarchy-settings` stays
as a link to it.

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
repository (empty the first time, which creates the `hyprdial` package) and pushes `PKGBUILD` and
`.SRCINFO`. The AUR repository's branch is `master`.

## A new release

1. Bump `__version__` in `hyprdial/__init__.py`, `pkgver` here and `Version` in `packaging/rpm/hyprdial.spec` (back to `pkgrel=1`,
   `sha256sums=('SKIP')`, then `makepkg --printsrcinfo > .SRCINFO`), point the main README's `pacman -U` line at
   the new version, and write the notes in `docs/releases/vX.Y.Z.md`.
2. Commit, push, then tag: `git tag -a vX.Y.Z -m "Hyprdial X.Y.Z" && git push origin vX.Y.Z`.
3. `.github/workflows/release.yml` does the rest: runs the tests, runs `build-release.sh` (checks that the tag,
   `__version__` and `pkgver` agree and that the package is called `hyprdial`, pins the tarball's
   checksum, builds), publishes the release with the package and the PKGBUILD, and commits the pinned checksum to
   `main` (`git pull` afterwards).
4. `packaging/arch/publish-aur.sh`.

`packaging/arch/build-release.sh vX.Y.Z` runs the same build locally, into `dist/`.
