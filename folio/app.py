"""Main window: docked toolbar, sidebar (thumbnails / outline / highlights / search) and page view."""

import hashlib
import os
import sys

import fitz
from PyQt6.QtCore import QSettings, QSize, Qt, QTimer
from PyQt6.QtGui import QAction, QActionGroup, QColor, QIcon, QImage, QKeySequence, QPalette, QPixmap, QShortcut
from PyQt6.QtWidgets import (QApplication, QFileDialog, QFrame, QHBoxLayout, QInputDialog, QLabel,
                             QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox,
                             QProgressBar, QPushButton, QSizePolicy, QSplitter, QStackedWidget,
                             QStyleFactory, QTabBar, QToolBar, QToolButton, QTreeWidget,
                             QTreeWidgetItem, QVBoxLayout, QWidget)

from . import __version__, icons, ocr
from .theme import THEMES, stylesheet
from .viewer import DARK_TINT, HIGHLIGHT_COLORS, PageView

FILE_FILTER = "Documents (*.pdf *.png *.jpg *.jpeg *.tif *.tiff *.bmp *.webp *.xps *.epub *.cbz);;All files (*)"
THUMB_W = 132


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("folio", "folio")
        self.doc = None
        self.path = None          # file on disk, None for unsaved (e.g. an opened image)
        self.dirty = False
        self.ocr_worker = None
        self.theme = self.settings.value("theme", "light")
        self.invert_pages = self.settings.value("invertPages", True, type=bool)
        self.ocr_lang = self.settings.value("ocrLang", "eng")
        self._search_state = None

        self.setWindowTitle("Folio")
        self.setWindowIcon(icons.app_icon())
        self.resize(self.settings.value("size", QSize(1200, 860)))
        self.setAcceptDrops(True)

        self.view = PageView()
        self._build_toolbar()
        self._build_sidebar()
        self._build_banner()

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        rl.addWidget(self.banner)
        rl.addWidget(self.view)

        self.splitter = QSplitter()
        self.splitter.addWidget(self.sidebar)
        self.splitter.addWidget(right)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([210, 990])
        self.splitter.setHandleWidth(1)
        self.setCentralWidget(self.splitter)
        self.sidebar.setVisible(self.settings.value("sidebar", True, type=bool))

        self.status_label = QLabel()
        self.progress = QProgressBar(maximumWidth=180, textVisible=False, visible=False)
        self.statusBar().addWidget(self.status_label, 1)
        self.statusBar().addPermanentWidget(self.progress)
        self.statusBar().setSizeGripEnabled(False)

        self.view.pageChanged.connect(self._on_page_changed)
        self.view.zoomChanged.connect(self._on_zoom_changed)
        self.view.annotsChanged.connect(self._on_annots_changed)
        self._build_shortcuts()
        self.apply_theme()
        self._set_tool("select")
        self._update_actions()

    # ----- UI construction --------------------------------------------------------------
    def _btn(self, icon_name, tip, slot, shortcut=None, checkable=False):
        act = QAction(tip, self)
        act.setToolTip(f"{tip} ({QKeySequence(shortcut).toString()})" if shortcut else tip)
        act.setData(icon_name)
        act.setCheckable(checkable)
        if shortcut:
            act.setShortcut(QKeySequence(shortcut))
        act.triggered.connect(slot)
        self.addAction(act)
        return act

    def _build_toolbar(self):
        tb = QToolBar("Tools", movable=False, floatable=False)
        tb.setIconSize(QSize(20, 20))
        tb.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, tb)
        self.toolbar = tb
        self.icon_actions = []

        def add(act):
            tb.addAction(act)
            self.icon_actions.append(act)
            return act

        self.menu_btn = QToolButton(popupMode=QToolButton.ToolButtonPopupMode.InstantPopup)
        self.menu_btn.setToolTip("Menu")
        self.menu_btn.setMenu(self._build_menu())
        tb.addWidget(self.menu_btn)
        self.act_sidebar = add(self._btn("sidebar", "Sidebar", self.toggle_sidebar, "Ctrl+B"))
        self.act_open = add(self._btn("open", "Open", self.open_dialog, QKeySequence.StandardKey.Open))
        self.act_save = add(self._btn("save", "Save", self.save, QKeySequence.StandardKey.Save))
        tb.addSeparator()
        self.act_prev = add(self._btn("up", "Previous page", lambda: self.view.go_to_page(self.view.current_page() - 1), "Left"))
        self.page_edit = QLineEdit(maximumWidth=46, minimumWidth=46, alignment=Qt.AlignmentFlag.AlignCenter)
        self.page_edit.setToolTip("Go to page")
        self.page_edit.returnPressed.connect(self._go_to_typed_page)
        tb.addWidget(self.page_edit)
        self.page_count = QLabel(" / 0 ")
        tb.addWidget(self.page_count)
        self.act_next = add(self._btn("down", "Next page", lambda: self.view.go_to_page(self.view.current_page() + 1), "Right"))
        tb.addSeparator()
        self.act_zoom_out = add(self._btn("zoom_out", "Zoom out", lambda: self.view.zoom_by(1 / 1.15), QKeySequence.StandardKey.ZoomOut))
        self.zoom_btn = QToolButton(popupMode=QToolButton.ToolButtonPopupMode.InstantPopup)
        self.zoom_btn.setText("100%")
        self.zoom_btn.setMinimumWidth(64)
        self.zoom_btn.setToolTip("Zoom")
        zm = QMenu(self)
        zm.addAction("Fit width", lambda: self.view.set_zoom(0, "width"))
        zm.addAction("Fit page", lambda: self.view.set_zoom(0, "page"))
        zm.addSeparator()
        for z in (50, 75, 100, 125, 150, 200, 300, 400):
            zm.addAction(f"{z}%", lambda z=z: self.view.set_zoom(z / 100))
        self.zoom_btn.setMenu(zm)
        tb.addWidget(self.zoom_btn)
        self.act_zoom_in = add(self._btn("zoom_in", "Zoom in", lambda: self.view.zoom_by(1.15), QKeySequence.StandardKey.ZoomIn))
        self.act_fit = add(self._btn("fit", "Fit width", lambda: self.view.set_zoom(0, "width"), "Ctrl+0"))
        tb.addSeparator()

        self.tool_group = QActionGroup(self)
        self.act_select = add(self._btn("select", "Select text", lambda: self._set_tool("select"), "V", True))
        self.act_highlight = add(self._btn("highlight", "Highlighter", lambda: self._set_tool("highlight"), "H", True))
        self.act_erase = add(self._btn("erase", "Remove highlight", lambda: self._set_tool("erase"), "E", True))
        for a in (self.act_select, self.act_highlight, self.act_erase):
            self.tool_group.addAction(a)
        self.color_group = QActionGroup(self)
        self.color_actions = {}
        saved = self.settings.value("color", "Yellow")
        for i, (name, hexcol) in enumerate(HIGHLIGHT_COLORS.items(), 1):
            a = QAction(icons.swatch(hexcol), name, self, checkable=True)
            a.setToolTip(f"{name} highlight (Alt+{i})")
            a.setShortcut(QKeySequence(f"Alt+{i}"))
            a.triggered.connect(lambda _, n=name: self._pick_color(n))
            self.color_group.addAction(a)
            tb.addAction(a)
            self.color_actions[name] = a
        (self.color_actions.get(saved) or self.color_actions["Yellow"]).setChecked(True)
        self.view.color = HIGHLIGHT_COLORS.get(saved, HIGHLIGHT_COLORS["Yellow"])
        self.act_undo = add(self._btn("undo", "Undo highlight change", self.undo, QKeySequence.StandardKey.Undo))
        tb.addSeparator()
        self.act_ocr = add(self._btn("ocr", "Recognize text (OCR) on this page", self.ocr_current, "Ctrl+R"))

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        tb.addWidget(spacer)
        self.search_edit = QLineEdit(placeholderText="Search", clearButtonEnabled=True)
        self.search_edit.setMinimumWidth(110)
        self.search_edit.setMaximumWidth(240)
        self.search_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.search_edit.returnPressed.connect(self.search_next)
        self.search_edit.textChanged.connect(self._search_text_changed)
        self.search_action = self.search_edit.addAction(QIcon(), QLineEdit.ActionPosition.LeadingPosition)
        tb.addWidget(self.search_edit)
        self.act_theme = add(self._btn("moon", "Dark mode", self.toggle_theme, "Ctrl+D"))

    def _build_menu(self):
        m = QMenu(self)
        m.addAction("Open…", self.open_dialog)
        self.recent_menu = m.addMenu("Open recent")
        self.recent_menu.aboutToShow.connect(self._fill_recent)
        m.addAction("Save", self.save)
        m.addAction("Save as…", self.save_as)
        m.addSeparator()
        m.addAction("Recognize text on this page", self.ocr_current)
        m.addAction("Recognize text on all pages without text", self.ocr_all)
        self.lang_menu = m.addMenu("OCR language")
        self.lang_menu.aboutToShow.connect(self._fill_langs)
        m.addSeparator()
        m.addAction("Copy selected text", self.view.copy_selection)
        inv = m.addAction("Dark pages in dark mode")
        inv.setCheckable(True)
        inv.setChecked(self.invert_pages)
        inv.toggled.connect(self._set_invert)
        m.addAction("Full screen", self.toggle_fullscreen)
        m.addSeparator()
        m.addAction("Keyboard shortcuts", self.show_shortcuts)
        m.addAction(f"About Folio {__version__}", self.about)
        m.addAction("Quit", self.close)
        return m

    def _build_sidebar(self):
        self.sidebar = QFrame(objectName="sidebar")
        self.sidebar.setMinimumWidth(170)
        lay = QVBoxLayout(self.sidebar)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.tabs = QTabBar(expanding=True, drawBase=False)
        for t in ("Pages", "Outline", "Highlights", "Results"):
            self.tabs.addTab(t)
        self.stack = QStackedWidget()
        self.tabs.currentChanged.connect(self._on_tab)
        lay.addWidget(self.tabs)
        lay.addWidget(self.stack)

        self.thumbs = QListWidget(objectName="thumbs")
        self.thumbs.setViewMode(QListWidget.ViewMode.IconMode)
        self.thumbs.setFlow(QListWidget.Flow.TopToBottom)
        self.thumbs.setWrapping(False)
        self.thumbs.setMovement(QListWidget.Movement.Static)
        self.thumbs.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.thumbs.setUniformItemSizes(False)
        self.thumbs.setSpacing(6)
        self.thumbs.setIconSize(QSize(THUMB_W, int(THUMB_W * 1.42)))
        self.thumbs.itemClicked.connect(lambda it: self.view.go_to_page(self.thumbs.row(it)))
        self.thumbs.verticalScrollBar().valueChanged.connect(lambda _: self._thumb_timer.start())
        self._thumb_timer = QTimer(self, singleShot=True, interval=30)
        self._thumb_timer.timeout.connect(self._render_thumbs)
        self._thumb_done = set()

        self.outline = QTreeWidget(headerHidden=True)
        self.outline.itemClicked.connect(self._outline_clicked)
        self.hl_list = QListWidget()
        self.hl_list.setWordWrap(True)
        self.hl_list.itemClicked.connect(self._hl_clicked)
        self.hl_list.setToolTip("Click to jump · Delete key removes the highlight")
        QShortcut(QKeySequence.StandardKey.Delete, self.hl_list, self._delete_listed_highlight,
                  context=Qt.ShortcutContext.WidgetShortcut)
        self.results = QListWidget()
        self.results.setWordWrap(True)
        self.results.itemClicked.connect(self._result_clicked)
        for w in (self.thumbs, self.outline, self.hl_list, self.results):
            self.stack.addWidget(w)
        self._hl_stale = True

    def _build_banner(self):
        self.banner = QFrame(objectName="banner", visible=False)
        bl = QHBoxLayout(self.banner)
        bl.setContentsMargins(14, 7, 10, 7)
        self.banner_text = QLabel("This document looks scanned. Recognize its text so you can select, search and highlight it.")
        self.banner_text.setWordWrap(True)
        bl.addWidget(self.banner_text, 1)
        b = QPushButton("Recognize text")
        b.clicked.connect(self.ocr_all)
        bl.addWidget(b)
        x = QToolButton(autoRaise=True)
        x.setText("✕")
        x.setToolTip("Dismiss")
        x.clicked.connect(lambda: self.banner.setVisible(False))
        bl.addWidget(x)

    def _build_shortcuts(self):
        QShortcut(QKeySequence.StandardKey.Find, self, lambda: (self.search_edit.setFocus(), self.search_edit.selectAll()))
        QShortcut(QKeySequence("F3"), self, self.search_next)
        QShortcut(QKeySequence("Shift+F3"), self, lambda: self.search_next(back=True))
        QShortcut(QKeySequence("Shift+Return"), self.search_edit, lambda: self.search_next(back=True),
                  context=Qt.ShortcutContext.WidgetShortcut)
        QShortcut(QKeySequence("Escape"), self.search_edit, self._clear_search, context=Qt.ShortcutContext.WidgetShortcut)
        QShortcut(QKeySequence.StandardKey.Copy, self, self.view.copy_selection)
        QShortcut(QKeySequence("Ctrl+Shift+H"), self, lambda: self.view.highlight_selection() and self._mark_dirty())
        QShortcut(QKeySequence("F11"), self, self.toggle_fullscreen)
        QShortcut(QKeySequence("Ctrl+="), self, lambda: self.view.zoom_by(1.15))
        QShortcut(QKeySequence("Ctrl+Shift+S"), self, self.save_as)
        QShortcut(QKeySequence("Ctrl+Q"), self, self.close)
        self.view.selectionChanged.connect(lambda has: self.status(
            "Selected text — Ctrl+C to copy, Ctrl+Shift+H to highlight" if has else ""))

    # ----- theme ------------------------------------------------------------------------
    def apply_theme(self):
        t = THEMES[self.theme]
        app = QApplication.instance()
        pal = QPalette()
        for role, key in ((QPalette.ColorRole.Window, "panel"), (QPalette.ColorRole.Base, "input"),
                          (QPalette.ColorRole.AlternateBase, "panel"), (QPalette.ColorRole.Text, "text"),
                          (QPalette.ColorRole.WindowText, "text"), (QPalette.ColorRole.ButtonText, "text"),
                          (QPalette.ColorRole.Button, "panel"), (QPalette.ColorRole.Highlight, "accent"),
                          (QPalette.ColorRole.ToolTipBase, "input"), (QPalette.ColorRole.ToolTipText, "text"),
                          (QPalette.ColorRole.PlaceholderText, "muted")):
            pal.setColor(role, QColor(t[key]))
        pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
        app.setPalette(pal)
        app.setStyleSheet(stylesheet(t))
        for act in self.icon_actions:
            name = act.data()
            if act is self.act_theme:
                name = "sun" if self.theme == "dark" else "moon"
                act.setToolTip(("Light mode" if self.theme == "dark" else "Dark mode") + " (Ctrl+D)")
            act.setIcon(icons.icon(name, t["icon"]))
        self.menu_btn.setIcon(icons.icon("menu", t["icon"]))
        self.search_action.setIcon(icons.icon("search", t["muted"]))
        self.view.set_dark(self.theme == "dark" and self.invert_pages, t["canvas"])
        self._thumb_done.clear()
        self._thumb_timer.start()

    def toggle_theme(self):
        self.theme = "light" if self.theme == "dark" else "dark"
        self.settings.setValue("theme", self.theme)
        self.apply_theme()

    def _set_invert(self, on):
        self.invert_pages = on
        self.settings.setValue("invertPages", on)
        self.apply_theme()

    # ----- tools ------------------------------------------------------------------------
    def _set_tool(self, tool):
        self.view.tool = tool
        {"select": self.act_select, "highlight": self.act_highlight, "erase": self.act_erase}[tool].setChecked(True)
        if tool == "highlight" and self.view.has_selection():
            self.view.highlight_selection()
            self._mark_dirty()
        hints = {"select": "", "highlight": "Highlighter: drag across text to highlight it",
                 "erase": "Click a highlight to remove it"}
        self.status(hints[tool])

    def _pick_color(self, name):
        self.view.color = HIGHLIGHT_COLORS[name]
        self.settings.setValue("color", name)
        self._set_tool("highlight")

    def undo(self):
        if self.view.undo():
            self._mark_dirty()

    def toggle_sidebar(self):
        self.sidebar.setVisible(not self.sidebar.isVisible())
        self.settings.setValue("sidebar", self.sidebar.isVisible())
        if self.sidebar.isVisible():
            self._thumb_timer.start()

    def toggle_fullscreen(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    # ----- opening & saving -------------------------------------------------------------
    def open_dialog(self):
        start = os.path.dirname(self.path) if self.path else self.settings.value("lastDir", os.path.expanduser("~"))
        path, _ = QFileDialog.getOpenFileName(self, "Open document", start, FILE_FILTER)
        if path:
            self.open_path(path)

    def open_path(self, path):
        if not self.maybe_save():
            return False
        path = os.path.abspath(path)
        try:
            doc = fitz.open(path)
        except Exception as e:
            QMessageBox.warning(self, "Folio", f"Couldn't open {os.path.basename(path)}:\n{e}")
            return False
        if doc.needs_pass:
            while True:
                pw, ok = QInputDialog.getText(self, "Password", f"{os.path.basename(path)} is protected. Password:",
                                              QLineEdit.EchoMode.Password)
                if not ok:
                    return False
                if doc.authenticate(pw):
                    break
        save_path = path
        if not doc.is_pdf:
            # images, XPS, EPUB…: convert to PDF in memory so they can be OCR'd and annotated
            doc = fitz.open("pdf", doc.convert_to_pdf())
            save_path = None
        self._stop_ocr()
        self._remember_position()
        if self.doc:
            self.doc.close()
        self.doc, self.path, self.dirty = doc, save_path, save_path is None
        self.source_name = os.path.basename(path)
        self.settings.setValue("lastDir", os.path.dirname(path))
        self._add_recent(path)
        self.view.set_document(doc)
        self._clear_search()
        self._load_sidebar()
        self._restore_position()
        self._check_scanned()
        self._update_actions()
        self._update_title()
        return True

    def _reload(self):
        """Reopen self.path after a full save, keeping the reading position."""
        page, zoom, fit = self.view.current_page(), self.view.zoom, self.view.fit
        doc = fitz.open(self.path)
        self.doc.close()
        self.doc = doc
        self.view.set_document(doc)
        self.view.set_zoom(zoom, fit)
        self.view.go_to_page(page)
        self._load_sidebar()

    def save(self):
        if not self.doc:
            return False
        if not self.path:
            return self.save_as()
        try:
            if self.doc.can_save_incrementally():
                self.doc.saveIncr()
            else:
                tmp = self.path + ".folio-tmp"
                self.doc.save(tmp, garbage=1, deflate=True)
                os.replace(tmp, self.path)
                self._reload()
        except Exception as e:
            QMessageBox.warning(self, "Folio", f"Couldn't save:\n{e}")
            return False
        self.dirty = False
        self._update_title()
        self.status("Saved")
        return True

    def save_as(self):
        if not self.doc:
            return False
        base = self.path or os.path.join(self.settings.value("lastDir", os.path.expanduser("~")),
                                         os.path.splitext(self.source_name)[0] + ".pdf")
        path, _ = QFileDialog.getSaveFileName(self, "Save as", base, "PDF (*.pdf)")
        if not path:
            return False
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        try:
            if self.path and os.path.abspath(path) == self.path:
                return self.save()
            self.doc.save(path, garbage=1, deflate=True)
        except Exception as e:
            QMessageBox.warning(self, "Folio", f"Couldn't save:\n{e}")
            return False
        self.path = path
        self.source_name = os.path.basename(path)
        self._add_recent(path)
        self._reload()
        self.dirty = False
        self._update_title()
        self.status(f"Saved {os.path.basename(path)}")
        return True

    def maybe_save(self):
        if not (self.doc and self.dirty):
            return True
        r = QMessageBox.question(self, "Folio", f"Save changes to {self.source_name}?",
                                 QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
                                 | QMessageBox.StandardButton.Cancel)
        if r == QMessageBox.StandardButton.Save:
            return self.save()
        return r == QMessageBox.StandardButton.Discard

    def _mark_dirty(self):
        if not self.dirty:
            self.dirty = True
            self._update_title()

    def _update_title(self):
        name = self.source_name if self.doc else ""
        self.setWindowTitle(f"{'• ' if self.dirty else ''}{name} — Folio" if name else "Folio")

    def _update_actions(self):
        has = self.doc is not None
        for a in (self.act_save, self.act_prev, self.act_next, self.act_zoom_in, self.act_zoom_out,
                  self.act_fit, self.act_ocr, self.act_undo):
            a.setEnabled(has)
        self.page_count.setText(f" / {len(self.doc) if has else 0} ")

    # ----- recent files & reading position ----------------------------------------------
    def _add_recent(self, path):
        rec = [p for p in (self.settings.value("recent", []) or []) if p != path]
        self.settings.setValue("recent", [path] + rec[:11])

    def _fill_recent(self):
        self.recent_menu.clear()
        for p in self.settings.value("recent", []) or []:
            if os.path.exists(p):
                self.recent_menu.addAction(os.path.basename(p), lambda p=p: self.open_path(p)).setToolTip(p)
        if self.recent_menu.isEmpty():
            self.recent_menu.addAction("No recent files").setEnabled(False)

    def _pos_key(self):
        return "pos/" + hashlib.sha1(self.path.encode()).hexdigest()[:16] if self.path else None

    def _remember_position(self):
        key = self._pos_key()
        if key and self.doc:
            self.settings.setValue(key, [self.view.current_page(), self.view.zoom, self.view.fit or ""])

    def _restore_position(self):
        key = self._pos_key()
        val = self.settings.value(key) if key else None
        if val:
            try:
                page, zoom, fit = int(val[0]), float(val[1]), val[2] or None
                self.view.set_zoom(zoom, fit)
                self.view.go_to_page(page)
                return
            except (ValueError, IndexError, TypeError):
                pass
        self.view.set_zoom(0, "width")
        self.view.go_to_page(0)

    # ----- sidebar ----------------------------------------------------------------------
    def _load_sidebar(self):
        self.thumbs.clear()
        self._thumb_done.clear()
        blank = QPixmap(THUMB_W, int(THUMB_W * 1.3))
        blank.fill(QColor("#ffffff"))
        for i, (w, h) in enumerate(self.view.sizes):
            pm = blank.scaled(THUMB_W, int(THUMB_W * h / w)) if w else blank
            it = QListWidgetItem(QIcon(pm), str(i + 1))
            it.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
            self.thumbs.addItem(it)
        self.outline.clear()
        parents = {0: self.outline.invisibleRootItem()}
        for lvl, title, page, *_ in self.doc.get_toc(simple=False):
            parent = parents.get(lvl - 1, self.outline.invisibleRootItem())
            it = QTreeWidgetItem(parent, [title])
            it.setData(0, Qt.ItemDataRole.UserRole, page - 1)
            parents[lvl] = it
        self._hl_stale = True
        if self.tabs.currentIndex() == 2:
            self._refresh_highlights()
        self._thumb_timer.start()

    def _render_thumbs(self):
        if not self.doc or not self.sidebar.isVisible() or self.tabs.currentIndex() != 0:
            return
        vp = self.thumbs.viewport().rect()
        dpr = self.devicePixelRatioF()
        for i in range(self.thumbs.count()):
            it = self.thumbs.item(i)
            r = self.thumbs.visualItemRect(it)
            if r.bottom() < vp.top() - 300:
                continue
            if r.top() > vp.bottom() + 300:
                break
            if i in self._thumb_done:
                continue
            page = self.doc[i]
            s = THUMB_W / page.rect.width * dpr
            pix = page.get_pixmap(matrix=fitz.Matrix(s, s), alpha=False)
            if self.view.dark:
                pix.tint_with(*DARK_TINT)
            img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888).copy()
            pm = QPixmap.fromImage(img)
            pm.setDevicePixelRatio(dpr)
            it.setIcon(QIcon(pm))
            self._thumb_done.add(i)
            # one thumbnail per tick keeps scrolling smooth
            self._thumb_timer.start()
            return

    def _on_tab(self, i):
        self.stack.setCurrentIndex(i)
        if i == 0:
            self._thumb_timer.start()
        elif i == 2 and self._hl_stale:
            self._refresh_highlights()

    def _outline_clicked(self, item):
        page = item.data(0, Qt.ItemDataRole.UserRole)
        if page is not None and page >= 0:
            self.view.go_to_page(page)

    def _refresh_highlights(self):
        self.hl_list.clear()
        self._hl_stale = False
        if not self.doc:
            return
        for pno in range(len(self.doc)):
            page = self.doc[pno]
            for annot in page.annots(types=[fitz.PDF_ANNOT_HIGHLIGHT]):
                text = (annot.info.get("content") or "").strip()
                if not text:
                    text = page.get_textbox(annot.rect).strip().replace("\n", " ")
                stroke = annot.colors.get("stroke") or (1, 1, 0)
                col = QColor.fromRgbF(*stroke[:3])
                it = QListWidgetItem(icons.swatch(col.name()), f"p. {pno + 1}  ·  {text[:160] or '(highlight)'}")
                it.setData(Qt.ItemDataRole.UserRole, (pno, annot.xref, tuple(annot.rect)))
                self.hl_list.addItem(it)
        if self.hl_list.count() == 0:
            it = QListWidgetItem("No highlights yet.\nPick the highlighter (H) and drag across text.")
            it.setFlags(Qt.ItemFlag.NoItemFlags)
            self.hl_list.addItem(it)

    def _hl_clicked(self, item):
        data = item.data(Qt.ItemDataRole.UserRole)
        if data:
            self.view.reveal_rect(data[0], data[2])

    def _delete_listed_highlight(self):
        item = self.hl_list.currentItem()
        data = item.data(Qt.ItemDataRole.UserRole) if item else None
        if data and self.view.delete_annot(data[0], data[1]):
            self._refresh_highlights()

    def _on_annots_changed(self, pno):
        self._mark_dirty()
        self._thumb_done.discard(pno)
        self._thumb_timer.start()
        if self.tabs.currentIndex() == 2:
            self._refresh_highlights()
        else:
            self._hl_stale = True

    # ----- navigation feedback ----------------------------------------------------------
    def _on_page_changed(self, pno):
        if pno >= 0:
            self.page_edit.setText(str(pno + 1))
            if self.thumbs.count() > pno and self.sidebar.isVisible():
                self.thumbs.setCurrentRow(pno)

    def _on_zoom_changed(self, z):
        self.zoom_btn.setText(f"{round(z * 100)}%")

    def _go_to_typed_page(self):
        try:
            self.view.go_to_page(int(self.page_edit.text()) - 1)
        except ValueError:
            pass
        self.view.setFocus()

    def status(self, text):
        self.status_label.setText(text)

    # ----- search -----------------------------------------------------------------------
    def _search_text_changed(self, text):
        if not text:
            self._clear_search()

    def _clear_search(self):
        self._search_state = None
        self.view.hits = {}
        self.view.current_hit = None
        self.results.clear()
        self.view.viewport().update()

    def search_next(self, back=False):
        term = self.search_edit.text().strip()
        if not term or not self.doc:
            return
        st = self._search_state
        if not st or st["term"] != term:
            self._start_search(term)
            return
        flat = st["flat"]
        if not flat:
            return
        st["index"] = (st["index"] + (-1 if back else 1)) % len(flat)
        self._show_hit()

    def _start_search(self, term):
        self._search_state = {"term": term, "flat": [], "index": -1, "next_page": 0,
                              "start": max(0, self.view.current_page())}
        self.view.hits = {}
        self.results.clear()
        self.tabs.setCurrentIndex(3)
        if not self.sidebar.isVisible():
            self.toggle_sidebar()
        self._search_chunk()

    def _search_chunk(self):
        st = self._search_state
        if not st or not self.doc:
            return
        n = len(self.doc)
        end = min(n, st["next_page"] + 20)
        for pno in range(st["next_page"], end):
            page = self.doc[pno]
            quads = page.search_for(st["term"], quads=True)
            if not quads:
                continue
            self.view.hits[pno] = quads
            for i, q in enumerate(quads):
                st["flat"].append((pno, i))
                r = q.rect
                line = page.get_textbox(fitz.Rect(-1e4, r.y0 - 1, 1e4, r.y1 + 1))
                it = QListWidgetItem(f"p. {pno + 1}  ·  {' '.join(line.split())[:140]}")
                it.setData(Qt.ItemDataRole.UserRole, len(st["flat"]) - 1)
                self.results.addItem(it)
            # jump to the first hit at or after the page being read
            if st["index"] < 0 and pno >= st["start"]:
                st["index"] = len(st["flat"]) - len(quads)
                self._show_hit()
        st["next_page"] = end
        if end < n:
            self.status(f"Searching… page {end} of {n}")
            QTimer.singleShot(0, self._search_chunk)
        else:
            total = len(st["flat"])
            if st["index"] < 0 and total:
                st["index"] = 0
                self._show_hit()
            self.status(f"{total} result{'s' if total != 1 else ''} for “{st['term']}”" if total
                        else f"No results for “{st['term']}”")
            self.view.viewport().update()

    def _show_hit(self):
        st = self._search_state
        pno, i = st["flat"][st["index"]]
        self.view.current_hit = (pno, i)
        self.view.reveal_rect(pno, self.view.hits[pno][i].rect)
        self.results.setCurrentRow(st["index"])
        if st["next_page"] >= len(self.doc):
            self.status(f"Result {st['index'] + 1} of {len(st['flat'])}")

    def _result_clicked(self, item):
        idx = item.data(Qt.ItemDataRole.UserRole)
        if idx is not None and self._search_state:
            self._search_state["index"] = idx
            self._show_hit()

    # ----- OCR --------------------------------------------------------------------------
    def _check_scanned(self):
        self.banner.setVisible(False)
        if not ocr.available():
            return
        for pno in range(min(3, len(self.doc))):
            page = self.doc[pno]
            if ocr.page_needs_ocr(page) and page.get_images():
                self.banner.setVisible(True)
                return

    def _fill_langs(self):
        self.lang_menu.clear()
        langs = ocr.languages()
        if not langs:
            self.lang_menu.addAction("Tesseract not installed").setEnabled(False)
        group = QActionGroup(self.lang_menu)
        for code in langs:
            a = self.lang_menu.addAction(code, lambda c=code: self._set_lang(c))
            a.setCheckable(True)
            a.setChecked(code == self.ocr_lang)
            group.addAction(a)

    def _set_lang(self, code):
        self.ocr_lang = code
        self.settings.setValue("ocrLang", code)

    def ocr_current(self):
        if self.doc:
            self._run_ocr([max(0, self.view.current_page())], force=True)

    def ocr_all(self):
        if self.doc:
            self._run_ocr([p for p in range(len(self.doc)) if ocr.page_needs_ocr(self.doc[p])])

    def _run_ocr(self, pages, force=False):
        self.banner.setVisible(False)
        if not ocr.available():
            QMessageBox.information(self, "Folio", "Text recognition needs Tesseract:\n\n"
                                    "sudo apt install tesseract-ocr tesseract-ocr-eng")
            return
        if self.ocr_worker and self.ocr_worker.isRunning():
            self.status("Text recognition is already running")
            return
        if not force:
            pages = [p for p in pages if ocr.page_needs_ocr(self.doc[p])]
        elif not ocr.page_needs_ocr(self.doc[pages[0]]):
            r = QMessageBox.question(self, "Folio", "This page already has text. Recognize it again anyway?\n"
                                     "(Use this only for scans whose text layer is broken.)")
            if r != QMessageBox.StandardButton.Yes:
                return
        if not pages:
            self.status("Every page already has text")
            return
        self._ocr_total, self._ocr_done, self._ocr_words = len(pages), 0, 0
        self.progress.setRange(0, len(pages))
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self.status(f"Recognizing text… 0 of {len(pages)} pages")
        self.ocr_worker = ocr.OcrWorker(self.doc.tobytes(), pages, self.ocr_lang)
        self.ocr_worker.pageDone.connect(self._ocr_page_done)
        self.ocr_worker.failed.connect(self._ocr_failed)
        self.ocr_worker.finished.connect(self._ocr_finished)
        self.ocr_worker.start()

    def _ocr_page_done(self, pno, words):
        if not self.doc:
            return
        self._ocr_words += ocr.apply_words(self.doc[pno], words)
        self.view.invalidate_page(pno, text=True)
        self._ocr_done += 1
        self.progress.setValue(self._ocr_done)
        self.status(f"Recognizing text… {self._ocr_done} of {self._ocr_total} pages")
        if words:
            self._mark_dirty()

    def _ocr_failed(self, msg):
        QMessageBox.warning(self, "Folio", f"Text recognition failed:\n{msg}")

    def _ocr_finished(self):
        self.progress.setVisible(False)
        self.status(f"Recognized {self._ocr_words} words on {self._ocr_done} page"
                    f"{'s' if self._ocr_done != 1 else ''}. Save to keep the text layer.")

    def _stop_ocr(self):
        if self.ocr_worker and self.ocr_worker.isRunning():
            self.ocr_worker.stop()
            self.ocr_worker.pageDone.disconnect()
            self.ocr_worker.wait()

    # ----- misc -------------------------------------------------------------------------
    def show_shortcuts(self):
        QMessageBox.information(self, "Keyboard shortcuts", (
            "Ctrl+O  open · Ctrl+S  save · Ctrl+Shift+S  save as\n"
            "Ctrl+F  search · Enter / F3  next result · Shift+F3  previous\n"
            "Ctrl+ +/−  zoom · Ctrl+0  fit width · Ctrl+wheel  zoom at cursor\n"
            "V  select text · H  highlighter · E  remove highlight\n"
            "Alt+1…4  highlight colour · Ctrl+Shift+H  highlight selection\n"
            "Ctrl+C  copy · Ctrl+Z  undo highlight change\n"
            "Ctrl+R  recognize text on this page\n"
            "Ctrl+B  sidebar · Ctrl+D  dark mode · F11  full screen\n"
            "Middle-drag or drag blank space to pan"))

    def about(self):
        QMessageBox.about(self, "About Folio", f"<b>Folio {__version__}</b><br>A fast, clean PDF reader with "
                          f"highlighting and OCR.<br>MuPDF {fitz.VersionFitz} · PyMuPDF {fitz.VersionBind}")

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        urls = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if urls:
            self.open_path(urls[0])

    def closeEvent(self, e):
        if not self.maybe_save():
            e.ignore()
            return
        self._stop_ocr()
        self._remember_position()
        self.settings.setValue("size", self.size())
        e.accept()


def main(argv=None):
    argv = sys.argv if argv is None else argv
    QApplication.setApplicationName("Folio")
    QApplication.setDesktopFileName("folio")
    app = QApplication(argv)
    app.setStyle(QStyleFactory.create("Fusion"))
    win = MainWindow()
    win.show()
    args = [a for a in argv[1:] if not a.startswith("-")]
    if args:
        QTimer.singleShot(0, lambda: win.open_path(args[0]))
    return app.exec()
