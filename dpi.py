"""Windows DPI-awareness setup. Must run before QApplication is created."""
import sys


def set_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    import ctypes

    try:
        # PROCESS_PER_MONITOR_DPI_AWARE = 2 (Windows 8.1+)
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        try:
            # Fallback for older Windows (Vista+): system DPI aware only.
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass
