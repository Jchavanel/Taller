"""Temas visuales de la aplicación (paleta cálida, claro / oscuro / automático)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

CLARO = "claro"
OSCURO = "oscuro"
AUTO = "auto"

TEMAS = {CLARO: "Claro", OSCURO: "Oscuro", AUTO: "Automático (según el sistema)"}

# Paleta cálida: cremas y arenas, con el rojo del taller como acento.
_PALETA_CLARO = {
    "bg": "#FAF6F0",
    "surface": "#FFFDFB",
    "surface_alt": "#F2EBE0",
    "header": "#EDE3D5",
    "border": "#E3D8C7",
    "border_strong": "#D3C4AE",
    "text": "#2C2621",
    "text_muted": "#7C7264",
    "accent": "#E0301C",
    "accent_hover": "#C8291A",
    "accent_press": "#AE2216",
    "accent_fg": "#FFFFFF",
    "selection": "#F6DAD3",
    "selection_text": "#2C2621",
    "danger": "#C0392B",
    "warn_bg": "#FFF3CD",
    "warn_fg": "#7A5C00",
    "shadow": "rgba(120, 90, 60, 0.16)",
}

_PALETA_OSCURO = {
    "bg": "#1E1B18",
    "surface": "#262220",
    "surface_alt": "#2E2926",
    "header": "#332D29",
    "border": "#3D3733",
    "border_strong": "#4C443E",
    "text": "#EFE8DF",
    "text_muted": "#A99E8F",
    "accent": "#F0503C",
    "accent_hover": "#F26550",
    "accent_press": "#D8412F",
    "accent_fg": "#1E1B18",
    "selection": "#4A2B24",
    "selection_text": "#F6ECE4",
    "danger": "#E4675A",
    "warn_bg": "#453A1C",
    "warn_fg": "#EFD79B",
    "shadow": "rgba(0, 0, 0, 0.45)",
}


def _sistema_es_oscuro() -> bool:
    try:
        return QApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except (AttributeError, TypeError):
        return False


def resolver(tema: str) -> str:
    """Devuelve 'claro' u 'oscuro' teniendo en cuenta el modo automático."""
    if tema == AUTO:
        return OSCURO if _sistema_es_oscuro() else CLARO
    return tema if tema in (CLARO, OSCURO) else CLARO


def _paleta(tema_efectivo: str) -> dict:
    return _PALETA_OSCURO if tema_efectivo == OSCURO else _PALETA_CLARO


def hoja_estilo(tema: str) -> str:
    c = _paleta(resolver(tema))
    return f"""
* {{
    outline: 0;
}}
QWidget {{
    background-color: {c['bg']};
    color: {c['text']};
    font-size: 13px;
}}
QMainWindow, QDialog {{
    background-color: {c['bg']};
}}
QToolTip {{
    background-color: {c['text']};
    color: {c['bg']};
    border: none;
    padding: 4px 7px;
    border-radius: 4px;
}}

/* ---- barra de menús ---- */
QMenuBar {{
    background-color: {c['surface']};
    border-bottom: 1px solid {c['border']};
    padding: 2px 4px;
}}
QMenuBar::item {{
    background: transparent;
    padding: 6px 12px;
    border-radius: 6px;
}}
QMenuBar::item:selected {{
    background-color: {c['surface_alt']};
}}
QMenu {{
    background-color: {c['surface']};
    border: 1px solid {c['border']};
    border-radius: 8px;
    padding: 5px;
}}
QMenu::item {{
    padding: 7px 24px 7px 18px;
    border-radius: 6px;
}}
QMenu::item:selected {{
    background-color: {c['accent']};
    color: {c['accent_fg']};
}}
QMenu::separator {{
    height: 1px;
    background: {c['border']};
    margin: 5px 8px;
}}

/* ---- pestañas ---- */
QTabWidget::pane {{
    border: 1px solid {c['border']};
    border-radius: 10px;
    background-color: {c['surface']};
    top: -1px;
}}
QTabBar::tab {{
    background: transparent;
    color: {c['text_muted']};
    padding: 9px 20px;
    margin-right: 2px;
    border: none;
    border-top-left-radius: 9px;
    border-top-right-radius: 9px;
    font-weight: 600;
}}
QTabBar::tab:hover {{
    color: {c['text']};
}}
QTabBar::tab:selected {{
    background-color: {c['surface']};
    color: {c['accent']};
    border: 1px solid {c['border']};
    border-bottom-color: {c['surface']};
}}

/* ---- botones ---- */
QPushButton, QToolButton {{
    background-color: {c['surface']};
    color: {c['text']};
    border: 1px solid {c['border_strong']};
    border-radius: 8px;
    padding: 7px 14px;
    font-weight: 600;
}}
QToolButton {{ padding: 7px 12px; }}
QPushButton:hover, QToolButton:hover {{
    background-color: {c['surface_alt']};
    border-color: {c['accent']};
}}
QPushButton:pressed, QToolButton:pressed {{
    background-color: {c['header']};
}}
QToolButton::menu-indicator {{ image: none; width: 0; }}
QPushButton:disabled, QToolButton:disabled,
QPushButton[primary="true"]:disabled {{
    color: {c['text_muted']};
    background-color: {c['bg']};
    border-color: {c['border']};
}}
QPushButton[primary="true"] {{
    background-color: {c['accent']};
    color: {c['accent_fg']};
    border: 1px solid {c['accent']};
}}
QPushButton[primary="true"]:hover {{
    background-color: {c['accent_hover']};
    border-color: {c['accent_hover']};
}}
QPushButton[primary="true"]:pressed {{
    background-color: {c['accent_press']};
}}
QDialogButtonBox QPushButton {{
    min-width: 90px;
}}

/* ---- campos ---- */
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QDateEdit, QComboBox {{
    background-color: {c['surface']};
    border: 1px solid {c['border_strong']};
    border-radius: 7px;
    padding: 6px 8px;
    selection-background-color: {c['accent']};
    selection-color: {c['accent_fg']};
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus,
QDoubleSpinBox:focus, QDateEdit:focus, QComboBox:focus {{
    border: 1px solid {c['accent']};
}}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled,
QDateEdit:disabled {{
    background-color: {c['bg']};
    color: {c['text_muted']};
}}
QComboBox::drop-down {{
    border: none;
    width: 22px;
}}
QComboBox QAbstractItemView {{
    background-color: {c['surface']};
    border: 1px solid {c['border']};
    border-radius: 6px;
    selection-background-color: {c['accent']};
    selection-color: {c['accent_fg']};
    padding: 3px;
}}

/* ---- tablas ---- */
QTableView, QTableWidget {{
    background-color: {c['surface']};
    alternate-background-color: {c['surface_alt']};
    gridline-color: {c['border']};
    border: 1px solid {c['border']};
    border-radius: 10px;
    selection-background-color: {c['selection']};
    selection-color: {c['selection_text']};
}}
QTableView::item, QTableWidget::item {{
    padding: 5px 6px;
}}
QHeaderView::section {{
    background-color: {c['header']};
    color: {c['text_muted']};
    padding: 7px 8px;
    border: none;
    border-right: 1px solid {c['border']};
    border-bottom: 2px solid {c['border_strong']};
    font-weight: 700;
}}
QTableCornerButton::section {{
    background-color: {c['header']};
    border: none;
}}

/* ---- grupos ---- */
QGroupBox {{
    border: 1px solid {c['border']};
    border-radius: 10px;
    margin-top: 14px;
    padding: 10px 8px 6px 8px;
    font-weight: 700;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    top: 2px;
    padding: 0 6px;
    color: {c['accent']};
}}

QLabel[clase="aviso"] {{
    background: {c['warn_bg']};
    color: {c['warn_fg']};
    padding: 8px 11px;
    border-radius: 6px;
    font-weight: bold;
}}

/* ---- calendario ---- */
QCalendarWidget QWidget {{ alternate-background-color: {c['surface_alt']}; }}
QCalendarWidget QToolButton {{
    background: transparent;
    color: {c['text']};
    border: none;
    border-radius: 6px;
    padding: 4px 10px;
    font-weight: 600;
}}
QCalendarWidget QToolButton:hover {{ background: {c['surface_alt']}; }}
QCalendarWidget QMenu {{ background: {c['surface']}; }}
QCalendarWidget #qt_calendar_navigationbar {{
    background: {c['header']};
    border-top-left-radius: 8px; border-top-right-radius: 8px;
}}
QCalendarWidget QAbstractItemView {{
    background: {c['surface']};
    selection-background-color: {c['accent']};
    selection-color: {c['accent_fg']};
    outline: 0;
}}
QCalendarWidget QAbstractItemView:disabled {{ color: {c['text_muted']}; }}
QCalendarWidget QSpinBox {{ background: {c['surface']}; }}

/* ---- varios ---- */
QStatusBar {{
    background-color: {c['surface']};
    border-top: 1px solid {c['border']};
    color: {c['text_muted']};
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 17px; height: 17px;
    border: 1px solid {c['border_strong']};
    border-radius: 5px;
    background: {c['surface']};
}}
QRadioButton::indicator {{ border-radius: 9px; }}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background: {c['accent']};
    border-color: {c['accent']};
}}
QScrollBar:vertical {{
    background: transparent; width: 12px; margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {c['border_strong']};
    border-radius: 5px; min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: {c['accent']}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar:horizontal {{
    background: transparent; height: 12px; margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {c['border_strong']};
    border-radius: 5px; min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{ background: {c['accent']}; }}
QSplitter::handle {{ background: {c['border']}; }}
QSplitter::handle:horizontal {{ width: 3px; }}
QProgressBar {{
    border: 1px solid {c['border']};
    border-radius: 6px;
    background: {c['surface']};
    text-align: center;
}}
QProgressBar::chunk {{
    background-color: {c['accent']};
    border-radius: 5px;
}}
"""


def aplicar_tema(app: QApplication, tema: str) -> None:
    """Aplica el tema a toda la aplicación (estilo Fusion + hoja de estilo)."""
    app.setStyle("Fusion")
    efectivo = resolver(tema)
    c = _paleta(efectivo)

    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(c["bg"]))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(c["text"]))
    pal.setColor(QPalette.ColorRole.Base, QColor(c["surface"]))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(c["surface_alt"]))
    pal.setColor(QPalette.ColorRole.Text, QColor(c["text"]))
    pal.setColor(QPalette.ColorRole.Button, QColor(c["surface"]))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(c["text"]))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(c["accent"]))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(c["accent_fg"]))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(c["text"]))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(c["bg"]))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(c["text_muted"]))
    dis = QPalette.ColorGroup.Disabled
    pal.setColor(dis, QPalette.ColorRole.Text, QColor(c["text_muted"]))
    pal.setColor(dis, QPalette.ColorRole.ButtonText, QColor(c["text_muted"]))
    app.setPalette(pal)
    app.setStyleSheet(hoja_estilo(tema))


def color(tema: str, token: str) -> str:
    return _paleta(resolver(tema)).get(token, "#000000")
