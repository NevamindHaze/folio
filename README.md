# Folio

A fast, clean PDF reader for Linux. It's built for studying: highlight like in Adobe Acrobat, and run OCR on scanned notes so you can select, search and highlight their text.

- **Fast.** Folio uses the MuPDF engine. Pages render on demand, so large textbooks open almost instantly and scroll smoothly.
- **Clean.** One docked toolbar and a sidebar for pages, outline, highlights and search results. Nothing floats over the page.
- **Highlights.** Pick the highlighter (or press `H`) and drag across text. There are four colours: yellow, green, blue and pink. Highlights are saved as standard PDF highlight annotations, so Adobe, Okular, Evince, browsers and phones all show them.
- **OCR.** Scanned PDFs and photos of pages get an invisible text layer from the local Tesseract engine. After that you can select, copy, search and highlight their text, and the text layer is saved into the PDF. Folio offers to run OCR when it opens a scanned document. Nothing is sent online.
- **Dark mode.** One click (`Ctrl+D`) switches the interface to dark, and pages are shown dark too (you can turn that off in the menu).
- Also: thumbnails, outline / table of contents, a list of all your highlights (click one to jump to it), search with a results list, recent files, it remembers where you were in each file, drag and drop, password-protected PDFs, and opening images, EPUB and XPS.

## Install

Folio needs Python 3, PyQt6, PyMuPDF and Tesseract. On Linux Mint, Ubuntu or Debian:

```bash
sudo apt install python3-pyqt6 python3-fitz tesseract-ocr tesseract-ocr-eng
```

For OCR in other languages, add packages such as `tesseract-ocr-deu` or `tesseract-ocr-fra`, then pick the language under **Menu → OCR language**.

### Option A: install script (per user, no root)

```bash
git clone https://github.com/NevamindHaze/folio.git
cd folio
./install.sh
```

This adds **Folio** to the menu (under Office) and a `folio` command in `~/.local/bin`. To remove it, run `./install.sh --uninstall`.

### Option B: .deb package

```bash
./packaging/build-deb.sh
sudo apt install ./dist/folio_0.1.0_all.deb
```

apt pulls in all the dependencies automatically. To remove it, run `sudo apt remove folio`.

### Make Folio your default PDF app

```bash
xdg-mime default folio.desktop application/pdf
```

You can also right-click a PDF, choose **Open With → Other Application → Folio**, and set it as the default.

## Run without installing

```bash
python3 -m folio path/to/file.pdf
```

## Using it

| Action | How |
| --- | --- |
| Select text | `V`, then drag. Double-click selects a word, Shift+click extends the selection. |
| Highlight | `H` (or click a colour), then drag across text. You can also select text first and press `Ctrl+Shift+H`. |
| Highlight colour | Click a swatch, or `Alt+1` … `Alt+4` |
| Remove a highlight | `E`, then click the highlight. Or select it in the Highlights tab and press Delete. |
| Undo highlight change | `Ctrl+Z` |
| Copy text | `Ctrl+C` |
| OCR this page / all pages | `Ctrl+R` / Menu → Recognize text on all pages without text |
| Search | `Ctrl+F`, then Enter / `F3` for the next result and `Shift+F3` for the previous one |
| Zoom | `Ctrl` + wheel (zooms where the cursor is), `Ctrl +` / `Ctrl −`, `Ctrl+0` fits the width |
| Save | `Ctrl+S` (fast incremental save) or `Ctrl+Shift+S` |
| Sidebar / dark mode / full screen | `Ctrl+B` / `Ctrl+D` / `F11` |
| Pan | Drag blank space, or middle-drag |

## Why this stack

Folio is Python + PyQt6 + PyMuPDF. All the heavy work (parsing, rendering, text extraction and annotations) runs in MuPDF's C code. MuPDF is one of the fastest PDF engines there is, much lighter than Acrobat's. Qt draws the interface natively and Python only connects the parts. On Mint all three dependencies come from the distro repositories, so there is nothing to compile, and the `.deb` is architecture-independent and very small. Rendering is lazy: only the visible pages and their neighbours are rendered, and pages are cached at the current zoom. OCR runs in a background thread, so the window never freezes.

## How OCR works

Each page is rendered at 300 dpi and passed to the `tesseract` command. The words it finds are written back onto the page as invisible text (PDF render mode 3) at the exact positions of the words in the image. Scanners and OCRmyPDF use the same technique. The page looks exactly the same, but now has real text.

## Tests

```bash
python3 tests/test_folio.py
```

The tests run headless. They open a PDF, highlight text, save and reopen it, erase and undo a highlight, search, and OCR a scanned page and then highlight the recognised text.

## Licence

AGPL-3.0, the same licence as MuPDF and PyMuPDF, which Folio links against.
