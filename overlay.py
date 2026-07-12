"""OverlayWindow: frameless, translucent frame with a click-through hole.

The user drags this over the video/content they want to capture. The border
is draggable/resizable; the interior ("hole") passes mouse clicks through to
whatever is underneath, via QWidget.setMask().
"""
import sys

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QFontMetrics, QPainter, QPen, QRegion
from PySide6.QtWidgets import QWidget

# Text drawn on top of the accent color (badge below, and the resize-handle
# fill) — dark enough to stay readable against the bright cyan/teal accent.
ON_ACCENT_TEXT = "#0b1a1c"

BADGE_GAP = 8  # px between the overlay's outer top edge and the size badge
BADGE_PADDING_X = 14
BADGE_PADDING_Y = 6

HANDLE_SIZE = 20
# The border ring must be at least as thick as a handle, or the handle's
# paint spills past the ring into the hole — since the hole is exactly what
# CaptureWorker records, any such spill gets baked into every recording.
BORDER_WIDTH = HANDLE_SIZE
MIN_SIZE = 60

# Resize handle identifiers (edges/corners), used for cursor + drag logic.
HANDLE_NONE = 0
HANDLE_TOP = 1
HANDLE_BOTTOM = 2
HANDLE_LEFT = 4
HANDLE_RIGHT = 8
HANDLE_TOPLEFT = HANDLE_TOP | HANDLE_LEFT
HANDLE_TOPRIGHT = HANDLE_TOP | HANDLE_RIGHT
HANDLE_BOTTOMLEFT = HANDLE_BOTTOM | HANDLE_LEFT
HANDLE_BOTTOMRIGHT = HANDLE_BOTTOM | HANDLE_RIGHT

_CURSOR_MAP = {
    HANDLE_TOP: Qt.SizeVerCursor,
    HANDLE_BOTTOM: Qt.SizeVerCursor,
    HANDLE_LEFT: Qt.SizeHorCursor,
    HANDLE_RIGHT: Qt.SizeHorCursor,
    HANDLE_TOPLEFT: Qt.SizeFDiagCursor,
    HANDLE_BOTTOMRIGHT: Qt.SizeFDiagCursor,
    HANDLE_TOPRIGHT: Qt.SizeBDiagCursor,
    HANDLE_BOTTOMLEFT: Qt.SizeBDiagCursor,
}


class _SizeBadge(QWidget):
    """Small floating pill showing the live capture size, held just above the
    overlay's top edge. A plain in-hole label was unreadable — it sat over
    whatever video content was showing through the (intentionally
    transparent) hole, so it's now its own top-level widget outside the
    frame instead."""

    def __init__(self, accent_color: QColor, parent=None):
        super().__init__(parent)
        self._accent_color = accent_color
        self._text = "0 x 0"
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

        self._caption_font = QFont()
        self._caption_font.setPointSizeF(self._caption_font.pointSizeF() * 0.75)
        self._caption_font.setBold(True)
        self._caption_font.setLetterSpacing(QFont.PercentageSpacing, 120)

        self._size_font = QFont()
        self._size_font.setPointSizeF(self._size_font.pointSizeF() * 1.05)
        self._size_font.setBold(True)

    def set_size_text(self, width: int, height: int) -> None:
        self._text = f"{width} x {height}"
        self._relayout()
        self.update()

    def _relayout(self) -> None:
        caption_metrics = QFontMetrics(self._caption_font)
        size_metrics = QFontMetrics(self._size_font)
        content_w = max(caption_metrics.horizontalAdvance("SIZE"), size_metrics.horizontalAdvance(self._text))
        content_h = caption_metrics.height() + size_metrics.height()
        self.resize(QSize(content_w + BADGE_PADDING_X * 2, content_h + BADGE_PADDING_Y * 2))

    def follow(self, overlay_outer_rect: QRect) -> None:
        """Center above the overlay's outer top edge. If there's no room
        above (frame is flush against the top of the screen), drop below
        the frame's bottom edge instead — it must never land inside the
        frame, since the inner hole is exactly what gets captured."""
        x = overlay_outer_rect.center().x() - self.width() // 2
        y = overlay_outer_rect.top() - self.height() - BADGE_GAP
        if y < 0:
            y = overlay_outer_rect.bottom() + BADGE_GAP
        self.move(x, y)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        painter.setPen(Qt.NoPen)
        painter.setBrush(self._accent_color)
        painter.drawRoundedRect(self.rect(), 6, 6)

        caption_metrics = QFontMetrics(self._caption_font)
        painter.setFont(self._caption_font)
        painter.setPen(QColor(ON_ACCENT_TEXT).lighter(140))
        caption_rect = QRect(0, BADGE_PADDING_Y - 2, self.width(), caption_metrics.height())
        painter.drawText(caption_rect, Qt.AlignHCenter | Qt.AlignTop, "SIZE")

        painter.setFont(self._size_font)
        painter.setPen(QColor(ON_ACCENT_TEXT))
        size_rect = QRect(0, caption_rect.bottom(), self.width(), self.height() - caption_rect.bottom())
        painter.drawText(size_rect, Qt.AlignHCenter | Qt.AlignTop, self._text)


class OverlayWindow(QWidget):
    """Transparent capture-region frame. Emits geometry_changed while the
    user drags/resizes so listeners (e.g. the control panel) can show live
    dimensions."""

    geometry_changed = Signal(QRect)  # inner hole rect, in global screen coords

    def __init__(self, border_color: str = "#26c6da", parent=None):
        super().__init__(parent)
        self._border_color = QColor(border_color)
        self._drag_mode = HANDLE_NONE
        self._drag_start_mouse = QPoint()
        self._drag_start_geom = QRect()
        self._moving = False
        self._locked = False

        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setMouseTracking(True)

        self._badge = _SizeBadge(self._border_color)

        self.resize(400, 400)
        self._update_mask()

    # ---- geometry helpers -------------------------------------------------

    def inner_rect(self) -> QRect:
        """The click-through hole, in local widget coordinates."""
        return self.rect().adjusted(
            BORDER_WIDTH, BORDER_WIDTH, -BORDER_WIDTH, -BORDER_WIDTH
        )

    def capture_rect_global(self) -> QRect:
        """Inner hole rect mapped to global screen coordinates — this is
        exactly what capture.py should grab (excludes the border)."""
        top_left = self.mapToGlobal(self.inner_rect().topLeft())
        return QRect(top_left, self.inner_rect().size())

    # ---- painting -----------------------------------------------------

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        outer = self.rect()

        # Border frame (only the border area is painted; hole stays alpha 0).
        pen = QPen(self._border_color, BORDER_WIDTH)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        half = BORDER_WIDTH / 2
        painter.drawRect(outer.adjusted(int(half), int(half), -int(half) - 1, -int(half) - 1))

        # Resize-grip handles: white nub + colored outline + dark ring, so
        # they read as "grab points" distinct from the plain border line
        # and stay visible against both the border color and whatever
        # bright/dark video content is showing through the hole nearby.
        for rect in self._handle_rects().values():
            painter.setPen(QPen(QColor("#000000"), 2))
            painter.setBrush(QColor("#FFFFFF"))
            painter.drawEllipse(rect)
            inset = rect.adjusted(4, 4, -4, -4)
            painter.setPen(Qt.NoPen)
            painter.setBrush(self._border_color)
            painter.drawEllipse(inset)

    def _handle_rects(self) -> dict:
        w = self.width()
        h = self.height()
        s = HANDLE_SIZE
        return {
            HANDLE_TOPLEFT: QRect(0, 0, s, s),
            HANDLE_TOPRIGHT: QRect(w - s, 0, s, s),
            HANDLE_BOTTOMLEFT: QRect(0, h - s, s, s),
            HANDLE_BOTTOMRIGHT: QRect(w - s, h - s, s, s),
            HANDLE_TOP: QRect(w // 2 - s // 2, 0, s, s),
            HANDLE_BOTTOM: QRect(w // 2 - s // 2, h - s, s, s),
            HANDLE_LEFT: QRect(0, h // 2 - s // 2, s, s),
            HANDLE_RIGHT: QRect(w - s, h // 2 - s // 2, s, s),
        }

    # ---- click-through mask ------------------------------------------------

    def _update_mask(self):
        outer_region = QRegion(self.rect())
        inner_region = QRegion(self.inner_rect())
        border_region = outer_region.subtracted(inner_region)
        # Handles are drawn larger than the border strip (see HANDLE_SIZE vs
        # BORDER_WIDTH) so they're easy to spot; without unioning them in,
        # the outer part of each visible handle would silently pass clicks
        # through to whatever is beneath the overlay instead of resizing it.
        for rect in self._handle_rects().values():
            border_region = border_region.united(QRegion(rect, QRegion.Ellipse))
        self.setMask(border_region)

    def resizeEvent(self, event):
        self._update_mask()
        super().resizeEvent(event)
        self._sync_badge()
        self.geometry_changed.emit(self.capture_rect_global())

    def moveEvent(self, event):
        super().moveEvent(event)
        self._sync_badge()
        self.geometry_changed.emit(self.capture_rect_global())

    def showEvent(self, event):
        super().showEvent(event)
        self._sync_badge()
        self._badge.show()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._badge.hide()

    def closeEvent(self, event):
        self._badge.close()
        super().closeEvent(event)

    def _sync_badge(self):
        inner = self.inner_rect()
        self._badge.set_size_text(inner.width(), inner.height())
        self._badge.follow(QRect(self.pos(), self.size()))

    # ---- mouse-driven move/resize -----------------------------------------

    def _handle_at(self, pos: QPoint) -> int:
        for handle, rect in self._handle_rects().items():
            if rect.contains(pos):
                return handle
        return HANDLE_NONE

    def set_locked(self, locked: bool) -> None:
        """Freeze move/resize — used while recording, so the capture rect
        can't drift out from under an in-progress recording."""
        self._locked = locked
        if locked:
            self._drag_mode = HANDLE_NONE
            self._moving = False
            self.setCursor(QCursor(Qt.ArrowCursor))

    def mousePressEvent(self, event):
        if self._locked or event.button() != Qt.LeftButton:
            return
        pos = event.position().toPoint()
        handle = self._handle_at(pos)
        self._drag_start_mouse = event.globalPosition().toPoint()
        self._drag_start_geom = self.geometry()
        if handle != HANDLE_NONE:
            self._drag_mode = handle
        else:
            # Border area (mask already excludes the hole, so any click here
            # is on the frame) -> move the whole window.
            self._moving = True

    def mouseMoveEvent(self, event):
        if self._locked:
            return
        pos = event.position().toPoint()
        if self._drag_mode != HANDLE_NONE or self._moving:
            global_pos = event.globalPosition().toPoint()
            delta = global_pos - self._drag_start_mouse
            geom = QRect(self._drag_start_geom)

            if self._moving:
                geom.translate(delta)
            else:
                if self._drag_mode & HANDLE_LEFT:
                    geom.setLeft(min(geom.left() + delta.x(), geom.right() - MIN_SIZE))
                if self._drag_mode & HANDLE_RIGHT:
                    geom.setRight(max(geom.right() + delta.x(), geom.left() + MIN_SIZE))
                if self._drag_mode & HANDLE_TOP:
                    geom.setTop(min(geom.top() + delta.y(), geom.bottom() - MIN_SIZE))
                if self._drag_mode & HANDLE_BOTTOM:
                    geom.setBottom(max(geom.bottom() + delta.y(), geom.top() + MIN_SIZE))

            self.setGeometry(geom)
        else:
            handle = self._handle_at(pos)
            cursor = _CURSOR_MAP.get(handle, Qt.SizeAllCursor if handle == HANDLE_NONE else Qt.ArrowCursor)
            self.setCursor(QCursor(cursor))

    def mouseReleaseEvent(self, event):
        self._drag_mode = HANDLE_NONE
        self._moving = False
        self._update_mask()
        self.geometry_changed.emit(self.capture_rect_global())

    # ---- Win32 layered-window click-through fallback -----------------------

    def enable_native_click_through(self, enabled: bool) -> None:
        """Fallback if Qt setMask doesn't fully pass clicks through on some
        Windows versions: toggle WS_EX_TRANSPARENT on the raw HWND. Only
        applies while the user isn't actively dragging the frame (a fully
        transparent window can't receive the mouse-press that starts a
        drag)."""
        if sys.platform != "win32":
            return
        import ctypes

        hwnd = int(self.winId())
        GWL_EXSTYLE = -20
        WS_EX_LAYERED = 0x00080000
        WS_EX_TRANSPARENT = 0x00000020

        user32 = ctypes.windll.user32
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        if enabled:
            style |= WS_EX_LAYERED | WS_EX_TRANSPARENT
        else:
            style &= ~WS_EX_TRANSPARENT
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
