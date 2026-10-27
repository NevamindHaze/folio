"""Line icons drawn with QPainter, so the app needs no SVG plugin or icon theme."""

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

_SIZE = 48  # drawn on a 24-unit grid at 2x for HiDPI


def _p(*pts):
    path = QPainterPath(QPointF(*pts[0]))
    for pt in pts[1:]:
        path.lineTo(QPointF(*pt))
    return path


def _draw(name, p):
    if name == "menu":
        for y in (7, 12, 17):
            p.drawLine(QPointF(4, y), QPointF(20, y))
    elif name == "sidebar":
        p.drawRoundedRect(QRectF(3, 4, 18, 16), 2.5, 2.5)
        p.drawLine(QPointF(9, 4), QPointF(9, 20))
    elif name == "open":
        p.drawPath(_p((3, 19), (3, 6), (9, 6), (11, 8), (19, 8), (19, 11)))
        p.drawPath(_p((3, 19), (6, 11), (21, 11), (18, 19), (3, 19)))
    elif name == "save":
        p.drawLine(QPointF(12, 3), QPointF(12, 14))
        p.drawPath(_p((7.5, 9.5), (12, 14), (16.5, 9.5)))
        p.drawPath(_p((4, 14), (4, 20), (20, 20), (20, 14)))
    elif name == "up":
        p.drawPath(_p((6, 15), (12, 9), (18, 15)))
    elif name == "down":
        p.drawPath(_p((6, 9), (12, 15), (18, 9)))
    elif name in ("zoom_in", "zoom_out", "search"):
        p.drawEllipse(QPointF(10.5, 10.5), 6.5, 6.5)
        p.drawLine(QPointF(15.5, 15.5), QPointF(20.5, 20.5))
        if name != "search":
            p.drawLine(QPointF(7.5, 10.5), QPointF(13.5, 10.5))
        if name == "zoom_in":
            p.drawLine(QPointF(10.5, 7.5), QPointF(10.5, 13.5))
    elif name == "fit":
        p.drawLine(QPointF(4, 6), QPointF(4, 18))
        p.drawLine(QPointF(20, 6), QPointF(20, 18))
        p.drawLine(QPointF(7, 12), QPointF(17, 12))
        p.drawPath(_p((10, 9), (7, 12), (10, 15)))
        p.drawPath(_p((14, 9), (17, 12), (14, 15)))
    elif name == "select":
        p.drawLine(QPointF(12, 5), QPointF(12, 19))
        p.drawPath(_p((8.5, 4), (10, 4), (12, 5.5), (14, 4), (15.5, 4)))
        p.drawPath(_p((8.5, 20), (10, 20), (12, 18.5), (14, 20), (15.5, 20)))
    elif name == "highlight":
        p.drawPath(_p((14, 4), (19, 9), (11, 17), (6, 12), (14, 4)))
        p.drawPath(_p((6, 12), (4, 17), (6, 19), (11, 17)))
        p.drawLine(QPointF(3, 21), QPointF(21, 21))
    elif name == "erase":
        p.drawPath(_p((13, 4), (20, 11), (12, 19), (8, 19), (4, 15), (13, 4)))
        p.drawLine(QPointF(8.5, 9.5), QPointF(15.5, 16.5))
        p.drawLine(QPointF(12, 19), QPointF(20, 19))
    elif name == "ocr":
        for a, b, c in (((3, 8), (3, 3), (8, 3)), ((16, 3), (21, 3), (21, 8)),
                        ((21, 16), (21, 21), (16, 21)), ((8, 21), (3, 21), (3, 16))):
            p.drawPath(_p(a, b, c))
        p.drawPath(_p((7, 8), (7, 7), (17, 7), (17, 8)))
        p.drawLine(QPointF(12, 7), QPointF(12, 17))
        p.drawLine(QPointF(10, 17), QPointF(14, 17))
    elif name == "undo":
        path = QPainterPath(QPointF(5, 10))
        path.lineTo(QPointF(15, 10))
        path.cubicTo(QPointF(22, 10), QPointF(22, 20), QPointF(15, 20))
        path.lineTo(QPointF(9, 20))
        p.drawPath(path)
        p.drawPath(_p((9, 6), (5, 10), (9, 14)))
    elif name == "moon":
        path = QPainterPath()
        path.addEllipse(QPointF(12, 12), 8, 8)
        cut = QPainterPath()
        cut.addEllipse(QPointF(17, 8), 7, 7)
        p.drawPath(path.subtracted(cut))
    elif name == "sun":
        p.drawEllipse(QPointF(12, 12), 4, 4)
        import math
        for i in range(8):
            a = i * math.pi / 4
            p.drawLine(QPointF(12 + 7 * math.cos(a), 12 + 7 * math.sin(a)),
                       QPointF(12 + 9.5 * math.cos(a), 12 + 9.5 * math.sin(a)))
    elif name == "close":
        p.drawLine(QPointF(6, 6), QPointF(18, 18))
        p.drawLine(QPointF(18, 6), QPointF(6, 18))


def icon(name, color):
    pm = QPixmap(_SIZE, _SIZE)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(_SIZE / 24, _SIZE / 24)
    pen = QPen(QColor(color), 1.7)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    _draw(name, p)
    p.end()
    return QIcon(pm)


def swatch(color, ring=None):
    pm = QPixmap(_SIZE, _SIZE)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(0, 0, 0, 60), 2))
    p.setBrush(QColor(color))
    p.drawEllipse(QPointF(24, 24), 15, 15)
    p.end()
    return QIcon(pm)


def app_icon():
    """The Folio logo: a page with a yellow highlight stroke."""
    pm = QPixmap(256, 256)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#2f6fed"))
    p.drawRoundedRect(QRectF(16, 16, 224, 224), 52, 52)
    p.setBrush(QColor("#ffffff"))
    p.drawRoundedRect(QRectF(68, 48, 120, 160), 12, 12)
    p.setBrush(QColor("#ffd43b"))
    p.drawRoundedRect(QRectF(84, 104, 88, 22), 5, 5)
    p.setBrush(QColor("#c5d3ee"))
    for y in (76, 140, 164):
        p.drawRoundedRect(QRectF(84, y, 88 if y != 164 else 56, 10), 5, 5)
    p.end()
    return QIcon(pm)
