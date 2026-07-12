"""Dark theme + cyan accent: app-wide QSS and qtawesome icon helper."""
import tempfile
from pathlib import Path

import qtawesome as qta
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QStyleFactory

BG = "#1e2226"
SURFACE = "#262b30"
BORDER = "#3a4046"
TEXT_PRIMARY = "#e8eaed"
TEXT_SECONDARY = "#9aa4ad"
TEXT_DISABLED = "#5b6268"
ACCENT = "#26c6da"
ACCENT_HOVER = "#4dd0e1"
ACCENT_PRESSED = "#00acc1"
ACCENT_DISABLED = "#2c4649"

DARK_QSS = f"""
QWidget {{
    background: {BG};
    color: {TEXT_PRIMARY};
    font-size: 10pt;
}}

QPushButton {{
    background: {SURFACE};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 6px 12px;
}}
QPushButton:hover {{ border-color: {ACCENT}; }}
QPushButton:pressed {{ background: {ACCENT_PRESSED}; color: #0b1a1c; }}
QPushButton:disabled {{ color: {TEXT_DISABLED}; border-color: {BORDER}; }}
QPushButton:checked {{ background: {ACCENT}; color: #0b1a1c; }}

QLabel {{ color: {TEXT_SECONDARY}; }}
QLabel#statusLabel {{ color: {ACCENT}; }}
QLabel#dimensionLabel {{ color: {TEXT_PRIMARY}; font-weight: 600; }}
QLabel#hintLabel {{ color: {TEXT_SECONDARY}; font-size: 9pt; }}

QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 3px 6px;
    color: {TEXT_PRIMARY};
}}
QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border: 1px solid {ACCENT}; }}

QSpinBox::up-button, QDoubleSpinBox::up-button {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 16px;
    border-left: 1px solid {BORDER};
    border-top-right-radius: 4px;
    background: {SURFACE};
}}
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 16px;
    border-left: 1px solid {BORDER};
    border-bottom-right-radius: 4px;
    background: {SURFACE};
}}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{ background: {BORDER}; }}
QSpinBox::up-button:pressed, QDoubleSpinBox::up-button:pressed,
QSpinBox::down-button:pressed, QDoubleSpinBox::down-button:pressed {{ background: {ACCENT_PRESSED}; }}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    image: url(__UP_ARROW_PATH__);
    width: 10px; height: 10px;
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    image: url(__DOWN_ARROW_PATH__);
    width: 10px; height: 10px;
}}
QSpinBox::up-button:disabled, QSpinBox::down-button:disabled,
QDoubleSpinBox::up-button:disabled, QDoubleSpinBox::down-button:disabled {{ background: {BG}; }}
QComboBox QAbstractItemView {{
    background: {SURFACE};
    selection-background-color: {ACCENT};
    color: {TEXT_PRIMARY};
}}

QCheckBox {{ color: {TEXT_SECONDARY}; spacing: 6px; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border: 1px solid {ACCENT}; }}

QProgressBar {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 4px;
    text-align: center;
    color: {TEXT_PRIMARY};
}}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 3px; }}

QGroupBox {{
    border: 1px solid {BORDER};
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 14px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 4px;
    color: {TEXT_PRIMARY};
}}
"""


def _spinbox_arrow_paths() -> tuple[str, str]:
    # Qt's QSS border-triangle hack (border-color trick) silently renders as a
    # blank box under both native and Fusion styles in this Qt build, so the
    # up/down arrows are rasterized from qtawesome glyphs and referenced by
    # file path instead.
    cache_dir = Path(tempfile.gettempdir()) / "framezy_theme"
    cache_dir.mkdir(parents=True, exist_ok=True)
    up_path = cache_dir / "spin-up-arrow.png"
    down_path = cache_dir / "spin-down-arrow.png"
    qta.icon("fa5s.chevron-up", color=TEXT_PRIMARY).pixmap(32, 32).save(str(up_path))
    qta.icon("fa5s.chevron-down", color=TEXT_PRIMARY).pixmap(32, 32).save(str(down_path))
    return up_path.as_posix(), down_path.as_posix()


def apply(app: QApplication) -> None:
    # Native Windows styles ignore QSS-drawn spinbox arrows (renders as blank
    # rectangle button); Fusion is required for the rest of the custom QSS
    # (buttons, spinbox chrome, etc.) to be honored consistently.
    app.setStyle(QStyleFactory.create("Fusion"))
    up_path, down_path = _spinbox_arrow_paths()
    qss = DARK_QSS.replace("__UP_ARROW_PATH__", up_path).replace("__DOWN_ARROW_PATH__", down_path)
    app.setStyleSheet(qss)


def icon(name: str) -> QIcon:
    return qta.icon(name, color=ACCENT, color_disabled=TEXT_DISABLED)
