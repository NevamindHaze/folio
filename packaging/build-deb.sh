#!/bin/sh
# Build dist/folio_<version>_all.deb (needs only dpkg-deb, which every Debian/Ubuntu/Mint system has).
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$ROOT/folio/__init__.py")"
BUILD="$(mktemp -d)"
PKG="$BUILD/folio_${VERSION}_all"
trap 'rm -rf "$BUILD"' EXIT

mkdir -p "$PKG/DEBIAN" "$PKG/usr/lib/folio" "$PKG/usr/bin" "$PKG/usr/share/applications" \
    "$PKG/usr/share/icons/hicolor/scalable/apps" "$PKG/usr/share/doc/folio"
cp -r "$ROOT/folio" "$PKG/usr/lib/folio/"
find "$PKG" -name __pycache__ -prune -exec rm -rf {} +
cat > "$PKG/usr/bin/folio" <<'EOF'
#!/bin/sh
exec python3 -c 'import sys; sys.path.insert(0, "/usr/lib/folio"); from folio.app import main; sys.exit(main())' "$@"
EOF
chmod 755 "$PKG/usr/bin/folio"
cp "$ROOT/packaging/folio.desktop" "$PKG/usr/share/applications/"
cp "$ROOT/packaging/folio.svg" "$PKG/usr/share/icons/hicolor/scalable/apps/"
cp "$ROOT/README.md" "$ROOT/LICENSE" "$PKG/usr/share/doc/folio/"
cat > "$PKG/DEBIAN/control" <<EOF
Package: folio
Version: $VERSION
Section: graphics
Priority: optional
Architecture: all
Depends: python3, python3-pyqt6, python3-fitz | python3-pymupdf, tesseract-ocr, tesseract-ocr-eng
Maintainer: NevamindHaze <85500705+NevamindHaze@users.noreply.github.com>
Homepage: https://github.com/NevamindHaze/folio
Description: Fast, clean PDF reader with highlighting and OCR
 Folio is a lightweight PDF reader built on MuPDF. It has smooth continuous
 scrolling, thumbnails, search, dark mode, Adobe-style text highlighting saved
 as standard PDF annotations, and local OCR (Tesseract) for scanned documents.
EOF
chmod -R u=rwX,go=rX "$PKG"
mkdir -p "$ROOT/dist"
dpkg-deb --root-owner-group --build "$PKG" "$ROOT/dist/" >/dev/null
echo "Built $ROOT/dist/folio_${VERSION}_all.deb"
