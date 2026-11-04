#!/usr/bin/env bash
# Builds the package for a release tag, the way .github/workflows/release.yml does it:
#   packaging/arch/build-release.sh v0.6.0 [out-dir]
# Checks that the tag, __version__ and pkgver agree and that the package is called hyprdial (never like Omarchy's
# own omarchy-settings), pins the checksum of GitHub's tarball for the tag in PKGBUILD and .SRCINFO, and builds.
# out-dir (default: dist/ at the repository root) gets the .pkg.tar.zst and the pinned PKGBUILD.
set -euo pipefail

tag=${1:?usage: build-release.sh vX.Y.Z [out-dir]}
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$(dirname "$HERE")")"
OUT="$(realpath -m "${2:-$ROOT/dist}")"
version=${tag#v}

fail() { echo "error: $*" >&2; exit 1; }

app_version=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$ROOT/hyprdial/__init__.py")
pkgver=$(sed -n 's/^pkgver=//p' "$HERE/PKGBUILD")
pkgname=$(sed -n 's/^pkgname=//p' "$HERE/PKGBUILD")
pkgrel=$(sed -n 's/^pkgrel=//p' "$HERE/PKGBUILD")
[[ $tag == v* ]] || fail "the tag must look like vX.Y.Z, got $tag"
[[ $app_version == "$version" ]] || fail "__version__ is $app_version, the tag is $tag"
[[ $pkgver == "$version" ]] || fail "pkgver is $pkgver, the tag is $tag"
# Omarchy's repository has a package called omarchy-settings; one with that name would replace it
[[ $pkgname == hyprdial ]] || fail "pkgname is $pkgname, expected hyprdial"
[[ -s $ROOT/docs/releases/$tag.md ]] || fail "missing release notes: docs/releases/$tag.md"

url=$(sed -n 's/^url="\(.*\)"/\1/p' "$HERE/PKGBUILD")
url=${url//\$pkgname/$pkgname}
sum=$(curl -fsSL "$url/archive/refs/tags/$tag.tar.gz" | sha256sum | cut -d' ' -f1)
echo "Tarball checksum: $sum"
sed -i "s/^sha256sums=.*/sha256sums=('$sum')/" "$HERE/PKGBUILD"
(cd "$HERE" && makepkg --printsrcinfo > .SRCINFO)

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cp "$HERE/PKGBUILD" "$work/"
(cd "$work" && makepkg --nodeps --clean -f)
mkdir -p "$OUT"
cp "$work/$pkgname-$version-$pkgrel-any.pkg.tar.zst" "$HERE/PKGBUILD" "$OUT/"
echo "Built $OUT/$pkgname-$version-$pkgrel-any.pkg.tar.zst"
