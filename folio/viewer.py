"""Continuous-scroll page view with lazy rendering, text selection and highlighting."""

from collections import OrderedDict

import fitz
from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPainter, QPen
from PyQt6.QtWidgets import QAbstractScrollArea, QApplication

GAP = 14
MARGIN = 18
MIN_ZOOM, MAX_ZOOM = 0.1, 6.0
CACHE_PAGES = 48
# dark pages: black ink -> light grey, white paper -> soft charcoal (gentler than a plain invert)
DARK_TINT = (0xDADCE0, 0x1E1F22)

HIGHLIGHT_COLORS = {
    "Yellow": "#ffe14d",
    "Green": "#8de38a",
    "Blue": "#86c5ff",
    "Pink": "#ff9fcb",
}


def _hex_to_rgb(h):
    c = QColor(h)
    return (c.redF(), c.greenF(), c.blueF())


class PageView(QAbstractScrollArea):
    pageChanged = pyqtSignal(int)
    zoomChanged = pyqtSignal(float)
    annotsChanged = pyqtSignal(int)
    selectionChanged = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.doc = None
        self.sizes = []          # rotated page sizes in points
        self.rot = []            # unrotated page coords -> rotated page coords
        self.tops = []           # y of each page in layout pixels
        self.zoom = 1.0
        self.fit = "width"       # "width", "page" or None
        self.dark = False
        self.bg = QColor("#e9ebee")
        self.tool = "select"     # "select", "highlight", "erase"
        self.color = HIGHLIGHT_COLORS["Yellow"]
        self.cache = OrderedDict()
        self.words = {}
        self.pending = set()
        self.sel_anchor = self.sel_head = None
        self.hits = {}
        self.current_hit = None
        self.undo_stack = []
        self._current_page = -1
        self._pan = None
        self._render_timer = QTimer(self, singleShot=True, interval=0)
        self._render_timer.timeout.connect(self._render_next)
        self.viewport().setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.verticalScrollBar().valueChanged.connect(self._on_scroll)
        self.horizontalScrollBar().valueChanged.connect(lambda _: self.viewport().update())
        self.verticalScrollBar().setSingleStep(40)

    # ----- document -----------------------------------------------------------------
    def set_document(self, doc):
        self.doc = doc
        self.cache.clear()
        self.words.clear()
        self.pending.clear()
        self.hits = {}
        self.current_hit = None
        self.undo_stack = []
        self.sel_anchor = self.sel_head = None
        self.sizes, self.rot = [], []
        if doc is not None:
            for page in doc:
                r = page.rect
                self.sizes.append((r.width, r.height))
                self.rot.append(page.rotation_matrix)
        self._current_page = -1
        self._relayout()
        self.verticalScrollBar().setValue(0)
        self._on_scroll()

    def invalidate_page(self, pno, text=False):
        for key in [k for k in self.cache if k[0] == pno]:
            del self.cache[key]
        if text:
            self.words.pop(pno, None)
        self.viewport().update()

    def set_dark(self, dark, bg):
        self.dark = dark
        self.bg = QColor(bg)
        self.cache.clear()
        self.viewport().update()

    # ----- layout & zoom ------------------------------------------------------------
    def _relayout(self):
        z = self.zoom
        y = MARGIN
        self.tops = []
        maxw = 0
        for w, h in self.sizes:
            self.tops.append(y)
            y += h * z + GAP
            maxw = max(maxw, w * z)
        total_h = y - GAP + MARGIN if self.sizes else 0
        self._content_w = maxw + 2 * MARGIN
        vp = self.viewport().size()
        self.verticalScrollBar().setRange(0, max(0, int(total_h - vp.height())))
        self.verticalScrollBar().setPageStep(vp.height())
        self.horizontalScrollBar().setRange(0, max(0, int(self._content_w - vp.width())))
        self.horizontalScrollBar().setPageStep(vp.width())
        self.viewport().update()

    def _fit_zoom(self):
        if not self.sizes or not self.fit:
            return self.zoom
        vw = self.viewport().width() - 2 * MARGIN
        vh = self.viewport().height() - 2 * MARGIN
        maxw = max(w for w, _ in self.sizes)
        if self.fit == "width":
            return max(MIN_ZOOM, min(MAX_ZOOM, vw / maxw))
        w, h = self.sizes[max(0, self.current_page())]
        return max(MIN_ZOOM, min(MAX_ZOOM, min(vw / w, vh / h)))

    def set_zoom(self, zoom, fit=None, anchor=None):
        self.fit = fit
        if fit:
            zoom = self._fit_zoom()
        zoom = max(MIN_ZOOM, min(MAX_ZOOM, zoom))
        if anchor is None:
            anchor = QPointF(self.viewport().width() / 2, self.viewport().height() / 3)
        loc = self.page_at(anchor)
        self.zoom = zoom
        self._relayout()
        if loc:
            pno, pt = loc
            pos = pt * self._to_page(pno)  # where that point lands now, in viewport pixels
            self.verticalScrollBar().setValue(int(self.verticalScrollBar().value() + pos.y - anchor.y()))
            self.horizontalScrollBar().setValue(int(self.horizontalScrollBar().value() + pos.x - anchor.x()))
        self.zoomChanged.emit(self.zoom)
        self.viewport().update()

    def zoom_by(self, factor, anchor=None):
        self.set_zoom(self.zoom * factor, None, anchor)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.fit:
            self.set_zoom(0, self.fit)
        else:
            self._relayout()

    # ----- geometry -----------------------------------------------------------------
    def page_rect(self, pno):
        """Page rectangle in viewport coordinates."""
        w, h = self.sizes[pno]
        z = self.zoom
        vw = self.viewport().width()
        cw = max(self._content_w, vw)
        x = (cw - w * z) / 2 - self.horizontalScrollBar().value()
        y = self.tops[pno] - self.verticalScrollBar().value()
        return QRectF(x, y, w * z, h * z)

    def visible_pages(self):
        if not self.sizes:
            return []
        top = self.verticalScrollBar().value()
        bottom = top + self.viewport().height()
        z = self.zoom
        # binary search for the first page whose bottom is below `top`
        lo, hi = 0, len(self.tops) - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if self.tops[mid] + self.sizes[mid][1] * z < top:
                lo = mid + 1
            else:
                hi = mid
        out = []
        for i in range(lo, len(self.tops)):
            if self.tops[i] > bottom:
                break
            out.append(i)
        return out

    def _to_page(self, pno):
        """Matrix: unrotated PDF coordinates -> viewport pixels for page `pno`."""
        r = self.page_rect(pno)
        return self.rot[pno] * fitz.Matrix(self.zoom, self.zoom) * fitz.Matrix(1, 0, 0, 1, r.x(), r.y())

    def page_at(self, pos, clamp=False):
        """(page number, unrotated PDF point) under a viewport position."""
        pages = self.visible_pages()
        found = None
        for pno in pages:
            r = self.page_rect(pno)
            if r.top() - GAP / 2 <= pos.y() <= r.bottom() + GAP / 2:
                found = pno
                break
        if found is None and clamp and pages:
            found = min(pages, key=lambda n: min(abs(self.page_rect(n).top() - pos.y()),
                                                 abs(self.page_rect(n).bottom() - pos.y())))
        if found is None:
            return None
        pt = fitz.Point(pos.x(), pos.y()) * ~self._to_page(found)
        return found, pt

    def current_page(self):
        if not self.sizes:
            return -1
        pages = self.visible_pages()
        if not pages:
            return max(0, self._current_page)
        probe = self.verticalScrollBar().value() + self.viewport().height() / 3
        for pno in pages:
            if self.tops[pno] + self.sizes[pno][1] * self.zoom + GAP > probe:
                return pno
        return pages[-1]

    def go_to_page(self, pno, y_pt=None):
        if not self.sizes:
            return
        pno = max(0, min(len(self.sizes) - 1, pno))
        y = self.tops[pno] - MARGIN
        if y_pt is not None:
            y = self.tops[pno] + y_pt * self.zoom - self.viewport().height() / 3
        self.verticalScrollBar().setValue(int(y))

    def reveal_rect(self, pno, rect):
        """Scroll so that an unrotated PDF rect on page pno is visible."""
        r = fitz.Rect(rect) * self.rot[pno]
        top = self.tops[pno] + r.y0 * self.zoom
        vtop = self.verticalScrollBar().value()
        if not (vtop + 40 < top < vtop + self.viewport().height() - 80):
            self.verticalScrollBar().setValue(int(top - self.viewport().height() / 3))
        self.viewport().update()

    def _on_scroll(self, *_):
        cur = self.current_page()
        if cur != self._current_page:
            self._current_page = cur
            self.pageChanged.emit(cur)
        self.viewport().update()

    # ----- rendering ----------------------------------------------------------------
    def _key(self, pno):
        return (pno, round(self.zoom * self.devicePixelRatioF(), 4), self.dark)

    def _render(self, pno):
        dpr = self.devicePixelRatioF()
        s = self.zoom * dpr
        pix = self.doc[pno].get_pixmap(matrix=fitz.Matrix(s, s), alpha=False)
        if self.dark:
            pix.tint_with(*DARK_TINT)
        img = QImage(pix.samples, pix.width, pix.height, pix.stride,
                     QImage.Format.Format_RGB888).copy()
        img.setDevicePixelRatio(dpr)
        key = self._key(pno)
        self.cache[key] = img
        self.cache.move_to_end(key)
        while len(self.cache) > CACHE_PAGES:
            self.cache.popitem(last=False)

    def _render_next(self):
        if not self.doc:
            return
        visible = self.visible_pages()
        # render the page nearest the middle of the screen first
        mid = (visible[0] + visible[-1]) / 2 if visible else 0
        todo = [p for p in visible if self._key(p) not in self.cache]
        if not todo:
            # prefetch the neighbours once everything visible is sharp
            for p in (visible[-1] + 1, visible[0] - 1) if visible else ():
                if 0 <= p < len(self.sizes) and self._key(p) not in self.cache:
                    self._render(p)
                    break
            return
        todo.sort(key=lambda p: abs(p - mid))
        self._render(todo[0])
        self.viewport().update()
        self._render_timer.start()

    def paintEvent(self, e):
        p = QPainter(self.viewport())
        p.fillRect(self.viewport().rect(), self.bg)
        if not self.doc:
            p.end()
            return
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        need_render = False
        paper = QColor("#1e1f22") if self.dark else QColor("white")
        shadow = QColor(0, 0, 0, 70 if self.dark else 28)
        for pno in self.visible_pages():
            r = self.page_rect(pno)
            p.fillRect(r.adjusted(-1, -1, 1, 2), shadow)
            img = self.cache.get(self._key(pno))
            if img is None:
                need_render = True
                fallback = next((v for k, v in self.cache.items()
                                 if k[0] == pno and k[2] == self.dark), None)
                if fallback is not None:
                    p.drawImage(r, fallback)
                else:
                    p.fillRect(r, paper)
            else:
                p.drawImage(r.topLeft(), img)
            self._paint_overlays(p, pno)
        p.end()
        if need_render and not self._render_timer.isActive():
            self._render_timer.start()
        elif not need_render and not self._render_timer.isActive():
            QTimer.singleShot(60, self._render_next)

    def _paint_overlays(self, p, pno):
        m = self._to_page(pno)
        hits = self.hits.get(pno)
        if hits:
            for i, q in enumerate(hits):
                cur = self.current_hit == (pno, i)
                p.fillRect(self._qrect(q.rect, m), QColor(255, 140, 0, 150 if cur else 70))
                if cur:
                    p.setPen(QPen(QColor(230, 110, 0), 1.5))
                    p.drawRect(self._qrect(q.rect, m))
        sel = self.selected_lines(pno)
        if sel:
            for rect in sel:
                p.fillRect(self._qrect(rect, m), QColor(47, 111, 237, 80))

    @staticmethod
    def _qrect(rect, m):
        r = fitz.Rect(rect) * m
        return QRectF(r.x0, r.y0, r.width, r.height)

    # ----- text ---------------------------------------------------------------------
    def page_words(self, pno):
        w = self.words.get(pno)
        if w is None:
            w = self.doc[pno].get_text("words", sort=False)
            self.words[pno] = w
        return w

    def word_at(self, pno, pt, nearest=False, slack=2.0):
        words = self.page_words(pno)
        if not words:
            return None
        for i, w in enumerate(words):
            if w[0] - slack <= pt.x <= w[2] + slack and w[1] - slack <= pt.y <= w[3] + slack:
                return i
        if not nearest:
            return None
        best, best_d = None, None
        for i, w in enumerate(words):
            dy = max(w[1] - pt.y, 0, pt.y - w[3])
            dx = max(w[0] - pt.x, 0, pt.x - w[2])
            d = dy * 6 + dx
            if best_d is None or d < best_d:
                best, best_d = i, d
        return best

    def _sel_range(self):
        if self.sel_anchor is None or self.sel_head is None:
            return None
        a, b = sorted((self.sel_anchor, self.sel_head))
        return a, b

    def selected_words(self):
        """Yield (pno, word tuple) for the current selection in reading order."""
        rng = self._sel_range()
        if not rng:
            return
        (p0, i0), (p1, i1) = rng
        for pno in range(p0, p1 + 1):
            words = self.page_words(pno)
            start = i0 if pno == p0 else 0
            end = i1 if pno == p1 else len(words) - 1
            for i in range(start, end + 1):
                yield pno, words[i]

    def selected_lines(self, pno):
        rng = self._sel_range()
        if not rng or not (rng[0][0] <= pno <= rng[1][0]):
            return []
        return [r for p, r, _ in self._line_groups() if p == pno]

    def _line_groups(self):
        """Merge selected words into one rect per text line: [(pno, rect, text)]."""
        groups = []
        last = None
        for pno, w in self.selected_words():
            key = (pno, w[5], w[6])
            r = fitz.Rect(w[:4])
            if last == key or (groups and groups[-1][0] == pno and last and last[0] == pno
                               and abs(groups[-1][1].y0 - r.y0) < r.height * 0.5
                               and abs(groups[-1][1].y1 - r.y1) < r.height * 0.5
                               and r.x0 >= groups[-1][1].x1 - 1):
                g = groups[-1]
                g[1] |= r
                g[2].append(w[4])
            else:
                groups.append([pno, r, [w[4]]])
            last = key
        return [(p, r, " ".join(t)) for p, r, t in groups]

    def selected_text(self):
        return "\n".join(t for _, _, t in self._line_groups())

    def has_selection(self):
        return self._sel_range() is not None

    def clear_selection(self):
        if self.sel_anchor is not None:
            self.sel_anchor = self.sel_head = None
            self.selectionChanged.emit(False)
            self.viewport().update()

    def copy_selection(self):
        text = self.selected_text()
        if text:
            QApplication.clipboard().setText(text)
        return bool(text)

    # ----- annotations --------------------------------------------------------------
    def highlight_selection(self, color=None):
        groups = self._line_groups()
        if not groups:
            return 0
        color = color or self.color
        by_page = {}
        for pno, r, t in groups:
            by_page.setdefault(pno, []).append((r, t))
        made = []
        for pno, items in by_page.items():
            page = self.doc[pno]
            annot = page.add_highlight_annot(quads=[r.quad for r, _ in items])
            annot.set_colors(stroke=_hex_to_rgb(color))
            annot.set_info(content=" ".join(t for _, t in items), title="Folio")
            annot.update()
            made.append((pno, annot.xref))
            self.invalidate_page(pno)
            self.annotsChanged.emit(pno)
        self.undo_stack.append(("add", made))
        self.clear_selection()
        return len(made)

    def delete_annot(self, pno, xref, record=True):
        page = self.doc[pno]
        for annot in page.annots():
            if annot.xref == xref:
                if record:
                    self.undo_stack.append(("del", [(pno, annot.type[0], [q for q in _quads(annot)],
                                                     annot.colors.get("stroke"), annot.info)]))
                page.delete_annot(annot)
                self.invalidate_page(pno)
                self.annotsChanged.emit(pno)
                return True
        return False

    def highlight_at(self, pno, pt):
        page = self.doc[pno]
        for annot in page.annots(types=[fitz.PDF_ANNOT_HIGHLIGHT]):
            if any(q.rect.contains(pt) for q in _quads(annot)):
                return annot.xref
        return None

    def undo(self):
        if not self.undo_stack:
            return False
        kind, items = self.undo_stack.pop()
        if kind == "add":
            for pno, xref in items:
                self.delete_annot(pno, xref, record=False)
        else:
            for pno, _, quads, stroke, info in items:
                page = self.doc[pno]
                annot = page.add_highlight_annot(quads=quads)
                if stroke:
                    annot.set_colors(stroke=stroke)
                annot.set_info(content=info.get("content", ""), title=info.get("title", ""))
                annot.update()
                self.invalidate_page(pno)
                self.annotsChanged.emit(pno)
        return True

    # ----- input --------------------------------------------------------------------
    def wheelEvent(self, e):
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            steps = e.angleDelta().y() / 120
            if steps:
                self.zoom_by(1.1 ** steps, e.position())
            e.accept()
            return
        super().wheelEvent(e)

    def mousePressEvent(self, e):
        self.setFocus()
        pos = e.position()
        if e.button() == Qt.MouseButton.MiddleButton:
            self._pan = (pos, self.horizontalScrollBar().value(), self.verticalScrollBar().value())
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        if e.button() != Qt.MouseButton.LeftButton or not self.doc:
            return
        loc = self.page_at(pos)
        if self.tool == "erase":
            if loc:
                xref = self.highlight_at(*loc)
                if xref:
                    self.delete_annot(loc[0], xref)
            return
        i = self.word_at(*loc) if loc else None
        if i is None:
            self.clear_selection()
            self._pan = (pos, self.horizontalScrollBar().value(), self.verticalScrollBar().value())
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        if e.modifiers() & Qt.KeyboardModifier.ShiftModifier and self.sel_anchor:
            self.sel_head = (loc[0], i)
        else:
            self.sel_anchor = self.sel_head = (loc[0], i)
        self._selecting = True
        self.viewport().update()

    def mouseDoubleClickEvent(self, e):
        loc = self.page_at(e.position())
        if loc and self.tool != "erase":
            i = self.word_at(*loc)
            if i is not None:
                self.sel_anchor = self.sel_head = (loc[0], i)
                self._finish_selection()

    def mouseMoveEvent(self, e):
        pos = e.position()
        if self._pan:
            start, hx, vy = self._pan
            d = pos - start
            self.horizontalScrollBar().setValue(int(hx - d.x()))
            self.verticalScrollBar().setValue(int(vy - d.y()))
            return
        if getattr(self, "_selecting", False):
            # autoscroll while dragging past the edges
            vh = self.viewport().height()
            if pos.y() < 20:
                self.verticalScrollBar().setValue(self.verticalScrollBar().value() - 20)
            elif pos.y() > vh - 20:
                self.verticalScrollBar().setValue(self.verticalScrollBar().value() + 20)
            loc = self.page_at(pos, clamp=True)
            if loc:
                i = self.word_at(*loc, nearest=True)
                if i is not None and (loc[0], i) != self.sel_head:
                    self.sel_head = (loc[0], i)
                    self.viewport().update()
            return
        self._update_cursor(pos)

    def mouseReleaseEvent(self, e):
        if self._pan:
            self._pan = None
            self._update_cursor(e.position())
            return
        if getattr(self, "_selecting", False):
            self._finish_selection()

    def _finish_selection(self):
        self._selecting = False
        if self.tool == "highlight" and self.has_selection():
            self.highlight_selection()
        else:
            self.selectionChanged.emit(self.has_selection())
            self.viewport().update()

    def _update_cursor(self, pos):
        loc = self.page_at(pos) if self.doc else None
        shape = Qt.CursorShape.ArrowCursor
        if loc:
            if self.tool == "erase":
                if self.highlight_at(*loc):
                    shape = Qt.CursorShape.PointingHandCursor
            elif self.word_at(*loc) is not None:
                shape = Qt.CursorShape.IBeamCursor
            else:
                shape = Qt.CursorShape.OpenHandCursor
        self.viewport().setCursor(shape)

    def keyPressEvent(self, e):
        k = e.key()
        vs = self.verticalScrollBar()
        if k in (Qt.Key.Key_PageDown, Qt.Key.Key_Space):
            vs.setValue(vs.value() + int(self.viewport().height() * 0.9))
        elif k == Qt.Key.Key_PageUp:
            vs.setValue(vs.value() - int(self.viewport().height() * 0.9))
        elif k == Qt.Key.Key_Down:
            vs.setValue(vs.value() + 60)
        elif k == Qt.Key.Key_Up:
            vs.setValue(vs.value() - 60)
        elif k == Qt.Key.Key_Home:
            vs.setValue(0)
        elif k == Qt.Key.Key_End:
            vs.setValue(vs.maximum())
        elif k == Qt.Key.Key_Escape:
            self.clear_selection()
        else:
            super().keyPressEvent(e)


def _quads(annot):
    v = annot.vertices or []
    return [fitz.Quad(v[i:i + 4]) for i in range(0, len(v) - 3, 4)]
