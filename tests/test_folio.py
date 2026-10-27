"""End-to-end checks that run headless: python3 tests/test_folio.py

Covers opening, selecting + highlighting, saving and reopening, and OCR of a scanned page.
Works with plain python3 or pytest.
"""

import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import fitz  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from folio import ocr  # noqa: E402
from folio.app import MainWindow  # noqa: E402

APP = QApplication.instance() or QApplication([])
TEXT = "The canine heart has four chambers and the feline liver is large"


def _text_pdf(path):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), TEXT, fontsize=12)
    page.insert_text((72, 130), "Second line about bovine rumen digestion", fontsize=12)
    doc.save(path)


def _scanned_pdf(path):
    """A page that is only a picture of text, like a scanner produces."""
    src = fitz.open()
    page = src.new_page()
    page.insert_text((72, 100), "Equine dentistry requires careful", fontsize=20)
    page.insert_text((72, 140), "examination of the incisors", fontsize=20)
    pix = page.get_pixmap(dpi=200)
    doc = fitz.open()
    out = doc.new_page(width=page.rect.width, height=page.rect.height)
    out.insert_image(out.rect, pixmap=pix)
    doc.save(path)


def _window(path):
    w = MainWindow()
    w.resize(1000, 800)
    w.show()
    assert w.open_path(path)
    APP.processEvents()
    return w


def _select_words(view, pno, first, last):
    words = view.page_words(pno)
    i0 = next(i for i, w in enumerate(words) if w[4] == first)
    i1 = next(i for i, w in enumerate(words) if w[4] == last and i >= i0)
    view.sel_anchor, view.sel_head = (pno, i0), (pno, i1)


def test_highlight_save_reopen():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "notes.pdf")
        _text_pdf(path)
        w = _window(path)
        _select_words(w.view, 0, "canine", "chambers")
        assert w.view.selected_text() == "canine heart has four chambers"
        w._pick_color("Green")
        assert w.dirty
        assert w.save()
        w.dirty = False
        w.close()

        doc = fitz.open(path)
        page = doc[0]
        annots = list(page.annots(types=[fitz.PDF_ANNOT_HIGHLIGHT]))
        assert len(annots) == 1, annots
        a = annots[0]
        assert a.info["content"] == "canine heart has four chambers"
        g = a.colors["stroke"]
        assert g[1] > g[0] and g[1] > g[2], g  # green
        assert "canine" in page.get_textbox(a.rect)

        # reopen in the app: the highlight list shows it and erase + undo work
        w = _window(path)
        w.tabs.setCurrentIndex(2)
        assert w.hl_list.count() == 1 and "canine" in w.hl_list.item(0).text()
        xref = w.view.highlight_at(0, (a.rect.tl + a.rect.br) / 2)
        assert xref
        w.view.delete_annot(0, xref)
        assert not list(w.doc[0].annots())
        w.view.undo()
        assert len(list(w.doc[0].annots())) == 1
        w.dirty = False
        w.close()


def test_ocr_scanned_page():
    assert ocr.available(), "tesseract is not installed"
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "scan.pdf")
        _scanned_pdf(path)
        w = _window(path)
        assert w.banner.isVisibleTo(w), "scanned-document banner should show"
        assert not w.view.page_words(0)
        w.ocr_all()
        w.ocr_worker.wait()
        APP.processEvents()
        text = w.doc[0].get_text().lower()
        assert "dentistry" in text and "incisors" in text, text
        assert w.doc[0].search_for("dentistry")

        # highlight OCR'd text and check it survives a save
        _select_words(w.view, 0, "Equine", "dentistry")
        w.view.highlight_selection()
        assert w.save()
        w.dirty = False
        w.close()
        doc = fitz.open(path)
        page = doc[0]
        assert "dentistry" in page.get_text().lower()
        hl = list(page.annots(types=[fitz.PDF_ANNOT_HIGHLIGHT]))
        assert len(hl) == 1 and "dentistry" in hl[0].info["content"].lower()


def test_search():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "notes.pdf")
        _text_pdf(path)
        w = _window(path)
        w.search_edit.setText("rumen")
        w.search_next()
        APP.processEvents()
        assert w._search_state["flat"] == [(0, 0)]
        assert w.view.current_hit == (0, 0)
        w.close()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok ", name)
