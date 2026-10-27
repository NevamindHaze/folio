"""Light and dark colour themes and the Qt stylesheet built from them."""

THEMES = {
    "light": {
        "panel": "#f7f7f8", "input": "#ffffff", "text": "#1f2328", "muted": "#7a808a",
        "icon": "#3b4048", "border": "#e1e3e8", "hover": "#e9ebef", "checked": "#dfe7fb",
        "accent": "#2f6fed", "canvas": "#e9ebee", "banner": "#fff7d6", "banner_border": "#f0dc8a",
    },
    "dark": {
        "panel": "#232428", "input": "#2c2e33", "text": "#e6e7ea", "muted": "#8b9099",
        "icon": "#d4d6db", "border": "#34363c", "hover": "#30323a", "checked": "#2d3b5c",
        "accent": "#5b8ef5", "canvas": "#17181b", "banner": "#3a3420", "banner_border": "#5c5130",
    },
}


def stylesheet(t):
    return f"""
    QMainWindow, QStatusBar {{ background: {t['panel']}; color: {t['text']}; }}
    QStatusBar {{ border-top: 1px solid {t['border']}; font-size: 12px; color: {t['muted']}; }}
    QStatusBar QLabel {{ color: {t['muted']}; padding: 0 6px; }}
    QToolBar {{ background: {t['panel']}; border: none; border-bottom: 1px solid {t['border']};
               padding: 4px 6px; spacing: 2px; }}
    QToolBar::separator {{ background: {t['border']}; width: 1px; margin: 5px 7px; }}
    QToolButton {{ border: none; border-radius: 7px; padding: 4px; color: {t['text']}; }}
    QToolButton:hover {{ background: {t['hover']}; }}
    QToolButton:checked {{ background: {t['checked']}; }}
    QToolButton:disabled {{ color: {t['muted']}; }}
    QToolButton::menu-indicator {{ image: none; width: 0; }}
    QLineEdit {{ background: {t['input']}; color: {t['text']}; border: 1px solid {t['border']};
                border-radius: 7px; padding: 4px 8px; selection-background-color: {t['accent']}; }}
    QLineEdit:focus {{ border: 1px solid {t['accent']}; }}
    QLabel {{ color: {t['text']}; }}
    QMenu {{ background: {t['input']}; color: {t['text']}; border: 1px solid {t['border']};
            border-radius: 8px; padding: 5px; }}
    QMenu::item {{ padding: 6px 22px 6px 14px; border-radius: 5px; }}
    QMenu::item:selected {{ background: {t['hover']}; }}
    QMenu::item:disabled {{ color: {t['muted']}; }}
    QMenu::separator {{ height: 1px; background: {t['border']}; margin: 4px 6px; }}
    QMenu::indicator {{ width: 12px; height: 12px; left: 4px; }}
    #sidebar {{ background: {t['panel']}; border-right: 1px solid {t['border']}; }}
    QTabBar {{ background: {t['panel']}; }}
    QTabBar::tab {{ background: transparent; color: {t['muted']}; padding: 8px 4px;
                   border: none; border-bottom: 2px solid transparent; font-size: 12px; }}
    QTabBar::tab:selected {{ color: {t['text']}; border-bottom: 2px solid {t['accent']}; }}
    QTabBar::tab:hover {{ color: {t['text']}; }}
    QListWidget, QTreeWidget {{ background: {t['panel']}; color: {t['text']}; border: none;
                               outline: none; font-size: 12px; }}
    QListWidget::item, QTreeWidget::item {{ padding: 5px; border-radius: 6px; }}
    QListWidget::item:hover, QTreeWidget::item:hover {{ background: {t['hover']}; }}
    QListWidget::item:selected, QTreeWidget::item:selected {{ background: {t['checked']}; color: {t['text']}; }}
    #thumbs::item {{ padding: 6px; }}
    QSplitter::handle {{ background: {t['border']}; }}
    #banner {{ background: {t['banner']}; border-bottom: 1px solid {t['banner_border']}; }}
    QPushButton {{ background: {t['accent']}; color: white; border: none; border-radius: 7px;
                  padding: 6px 14px; font-weight: 600; }}
    QPushButton:hover {{ background: {t['accent']}; }}
    QProgressBar {{ background: {t['border']}; border: none; border-radius: 3px; max-height: 6px; }}
    QProgressBar::chunk {{ background: {t['accent']}; border-radius: 3px; }}
    QScrollBar:vertical {{ background: transparent; width: 11px; margin: 0; }}
    QScrollBar:horizontal {{ background: transparent; height: 11px; margin: 0; }}
    QScrollBar::handle {{ background: {t['muted']}; border-radius: 4px; min-height: 30px; min-width: 30px;
                         margin: 2px; }}
    QScrollBar::handle:hover {{ background: {t['icon']}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
    QToolTip {{ background: {t['input']}; color: {t['text']}; border: 1px solid {t['border']}; padding: 4px; }}
    """
