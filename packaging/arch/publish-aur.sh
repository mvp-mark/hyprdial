#!/usr/bin/env bash
# Publishes packaging/arch/PKGBUILD to the AUR as "hyprdial".
# Needs an AUR account with your SSH public key (https://aur.archlinux.org/account/), see packaging/arch/README.md.
#   packaging/arch/publish-aur.sh            first publication and every update
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

cd "$HERE"
makepkg --printsrcinfo > .SRCINFO
version=$(awk -F' = ' '/^\tpkgver/ {v=$2} /^\tpkgrel/ {r=$2} END {print v "-" r}' .SRCINFO)

echo "Checking that the package builds from the published tarball…"
build="$WORK/build"
mkdir "$build" && cp PKGBUILD "$build/"
(cd "$build" && makepkg --nodeps --clean --cleanbuild -f >/dev/null)

echo "Cloning the AUR repository (empty the first time)…"
git -c init.defaultBranch=master clone ssh://aur@aur.archlinux.org/hyprdial.git "$WORK/aur"
cp PKGBUILD .SRCINFO "$WORK/aur/"
cd "$WORK/aur"
git add PKGBUILD .SRCINFO
if git diff --cached --quiet; then
  echo "The AUR already has $version; nothing to publish."
  exit 0
fi
git commit -m "Update to $version"
git push origin master
echo "Published hyprdial $version: https://aur.archlinux.org/packages/hyprdial"
