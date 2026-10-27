"""OCR with the local Tesseract engine.

Pages are rendered to greyscale PNG, passed to the `tesseract` CLI, and the
recognised words are written back into the PDF as an invisible text layer
(render mode 3), the same technique scanners and OCRmyPDF use. After that the
text is ordinary PDF text: selectable, searchable, copyable and highlightable,
and it is kept when the file is saved.
"""

import csv
import io
import shutil
import subprocess

import fitz
from PyQt6.QtCore import QThread, pyqtSignal

DPI = 300


def available():
    return shutil.which("tesseract") is not None


def languages():
    if not available():
        return []
    try:
        out = subprocess.run(["tesseract", "--list-langs"], capture_output=True,
                             text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [l.strip() for l in out.splitlines()[1:] if l.strip() and l.strip() != "osd"]


def page_needs_ocr(page):
    return not page.get_text("text").strip()


def recognise_png(png, lang="eng", dpi=DPI):
    """Return [(x0, y0, x1, y1, word)] in image pixels."""
    proc = subprocess.run(
        ["tesseract", "stdin", "stdout", "--dpi", str(dpi), "-l", lang, "--psm", "3", "tsv"],
        input=png, capture_output=True, timeout=300)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode(errors="replace").strip() or "tesseract failed")
    words = []
    reader = csv.DictReader(io.StringIO(proc.stdout.decode("utf-8", errors="replace")),
                            delimiter="\t", quoting=csv.QUOTE_NONE)
    for row in reader:
        try:
            if row["level"] != "5" or float(row["conf"]) < 0:
                continue
        except (KeyError, ValueError, TypeError):
            continue
        text = (row.get("text") or "").strip()
        if not text:
            continue
        x, y, w, h = (int(row[k]) for k in ("left", "top", "width", "height"))
        words.append((x, y, x + w, y + h, text))
    return words


def render_png(page, dpi=DPI):
    return page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY, alpha=False).tobytes("png")


def apply_words(page, words, dpi=DPI):
    """Insert recognised words into `page` as invisible, correctly sized text."""
    if not words:
        return 0
    scale = 72.0 / dpi
    derot = page.derotation_matrix
    shape = page.new_shape()
    count = 0
    for x0, y0, x1, y1, text in words:
        # Base-14 Helvetica only covers Latin-1; drop anything else.
        text = text.encode("latin-1", "ignore").decode("latin-1")
        if not text:
            continue
        r = fitz.Rect(x0 * scale, y0 * scale, x1 * scale, y1 * scale) * derot
        h = r.height
        if h <= 0.5 or r.width <= 0.5:
            continue
        fontsize = h / 1.1
        width = fitz.get_text_length(text, fontname="helv", fontsize=fontsize)
        if width <= 0:
            continue
        origin = fitz.Point(r.x0, r.y1 - h * 0.12)
        stretch = fitz.Matrix(r.width / width, 1)
        shape.insert_text(origin, text, fontsize=fontsize, fontname="helv",
                          render_mode=3, morph=(origin, stretch))
        count += 1
    shape.commit()
    return count


class OcrWorker(QThread):
    """Renders and recognises pages off the UI thread, using its own document."""

    pageDone = pyqtSignal(int, list)
    failed = pyqtSignal(str)

    def __init__(self, pdf_bytes, pages, lang):
        super().__init__()
        self.pdf_bytes = pdf_bytes
        self.pages = pages
        self.lang = lang
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            doc = fitz.open("pdf", self.pdf_bytes)
            for pno in self.pages:
                if self._stop:
                    break
                words = recognise_png(render_png(doc[pno]), self.lang)
                self.pageDone.emit(pno, words)
            doc.close()
        except Exception as e:  # report any failure to the UI instead of dying silently
            self.failed.emit(str(e))
