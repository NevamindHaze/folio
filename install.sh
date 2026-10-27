#!/bin/sh
# Install Folio for the current user (no root needed once dependencies are present).
#   ./install.sh            install to ~/.local
#   ./install.sh --uninstall
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
PREFIX="${PREFIX:-$HOME/.local}"
LIB="$PREFIX/share/folio"

if [ "$1" = "--uninstall" ]; then
    rm -rf "$LIB" "$PREFIX/bin/folio" "$PREFIX/share/applications/folio.desktop" \
        "$PREFIX/share/icons/hicolor/scalable/apps/folio.svg"
    update-desktop-database "$PREFIX/share/applications" 2>/dev/null || true
    echo "Folio removed."
    exit 0
fi

missing=""
python3 -c "import PyQt6.QtWidgets" 2>/dev/null || missing="$missing python3-pyqt6"
python3 -c "import fitz" 2>/dev/null || missing="$missing python3-fitz"
command -v tesseract >/dev/null 2>&1 || missing="$missing tesseract-ocr tesseract-ocr-eng"
if [ -n "$missing" ]; then
    echo "Missing dependencies. Install them first with:"
    echo "    sudo apt install$missing"
    exit 1
fi

mkdir -p "$LIB" "$PREFIX/bin" "$PREFIX/share/applications" "$PREFIX/share/icons/hicolor/scalable/apps"
rm -rf "$LIB/folio"
cp -r "$HERE/folio" "$LIB/"
find "$LIB" -name __pycache__ -prune -exec rm -rf {} +
cat > "$PREFIX/bin/folio" <<EOF
#!/bin/sh
exec python3 -c 'import sys; sys.path.insert(0, "$LIB"); from folio.app import main; sys.exit(main())' "\$@"
EOF
chmod +x "$PREFIX/bin/folio"
sed "s|^Exec=folio|Exec=$PREFIX/bin/folio|" "$HERE/packaging/folio.desktop" > "$PREFIX/share/applications/folio.desktop"
cp "$HERE/packaging/folio.svg" "$PREFIX/share/icons/hicolor/scalable/apps/folio.svg"
update-desktop-database "$PREFIX/share/applications" 2>/dev/null || true
gtk-update-icon-cache -q "$PREFIX/share/icons/hicolor" 2>/dev/null || true

echo "Folio installed. Find it in the menu under Office, or run: folio file.pdf"
echo "To make it your default PDF app:  xdg-mime default folio.desktop application/pdf"
