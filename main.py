"""Entry point: boots QApplication with DPI awareness, shows ControlPanel."""
import os
import sys

from dpi import set_dpi_awareness

# Must run before QApplication is constructed.
set_dpi_awareness()

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

import theme
from control_panel import ControlPanel


def _icon_path() -> str:
    # PyInstaller onefile extracts bundled data next to sys._MEIPASS at runtime.
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "assets", "icon.ico")


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Framezy")
    app.setWindowIcon(QIcon(_icon_path()))
    theme.apply(app)
    panel = ControlPanel()
    panel.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
