"""EditorWindow: trim timeline, playback preview, export options."""
from PySide6.QtCore import QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

import theme
from gif_export import encode_gif

WIDTH_PRESETS = [240, 320, 480, 640, 0]  # 0 = original


def pil_to_qpixmap(img) -> QPixmap:
    rgb = img.convert("RGB")
    data = rgb.tobytes("raw", "RGB")
    qimg = QImage(data, rgb.width, rgb.height, rgb.width * 3, QImage.Format_RGB888)
    return QPixmap.fromImage(qimg.copy())


class TrimSlider(QWidget):
    """Two-handle range slider over [0, frame_count-1] for in/out trim points."""

    range_changed = Signal(int, int)

    HANDLE_W = 10
    GRAB_RADIUS = 14  # px; a click farther than this from both handles must not start a drag

    def __init__(self, parent=None):
        super().__init__(parent)
        self._count = 1
        self._in = 0
        self._out = 0
        self._dragging = None  # "in" | "out" | None
        self.setMinimumHeight(28)
        self.setMouseTracking(True)

    def set_count(self, count: int):
        self._count = max(1, count)
        self._in = 0
        self._out = self._count - 1
        self.update()
        self.range_changed.emit(self._in, self._out)

    def in_point(self) -> int:
        return self._in

    def out_point(self) -> int:
        return self._out

    def _x_for_frame(self, frame: int) -> float:
        usable = self.width() - self.HANDLE_W
        if self._count <= 1:
            return self.HANDLE_W / 2
        return self.HANDLE_W / 2 + usable * (frame / (self._count - 1))

    def _frame_for_x(self, x: float) -> int:
        usable = self.width() - self.HANDLE_W
        if usable <= 0:
            return 0
        frac = (x - self.HANDLE_W / 2) / usable
        frac = min(1.0, max(0.0, frac))
        return round(frac * (self._count - 1))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        track_y = self.height() // 2
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(theme.BORDER))
        painter.drawRect(0, track_y - 2, self.width(), 4)

        x_in = self._x_for_frame(self._in)
        x_out = self._x_for_frame(self._out)
        painter.setBrush(QColor(theme.ACCENT))
        painter.drawRect(QRect(int(x_in), track_y - 2, int(x_out - x_in), 4))

        for x in (x_in, x_out):
            painter.setBrush(QColor(theme.TEXT_PRIMARY))
            painter.setPen(QColor(theme.BG))
            painter.drawEllipse(int(x - self.HANDLE_W / 2), track_y - self.HANDLE_W // 2, self.HANDLE_W, self.HANDLE_W)

    def mousePressEvent(self, event):
        x = event.position().x()
        x_in = self._x_for_frame(self._in)
        x_out = self._x_for_frame(self._out)
        dist_in = abs(x - x_in)
        dist_out = abs(x - x_out)
        # Only actually grab a handle if the click landed near one. Without
        # this, a click anywhere on the track — even nowhere near either
        # handle — silently started dragging whichever was nearest, which
        # misfires easily once the two handles are close together (e.g.
        # after trimming once already): a click meant for the end handle
        # could grab the start handle instead, leaving the end untouched.
        if dist_in > self.GRAB_RADIUS and dist_out > self.GRAB_RADIUS:
            self._dragging = None
            return
        self._dragging = "in" if dist_in <= dist_out else "out"

    def mouseMoveEvent(self, event):
        if not self._dragging:
            return
        frame = self._frame_for_x(event.position().x())
        if self._dragging == "in":
            self._in = min(frame, self._out)
        else:
            self._out = max(frame, self._in)
        self.update()
        self.range_changed.emit(self._in, self._out)

    def mouseReleaseEvent(self, event):
        self._dragging = None


class EditorWindow(QWidget):
    def __init__(self, frames: list, fps: int, settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Framezy — Editor")
        self.frames = frames
        self.settings = settings
        self._preview_frames = []
        self._preview_index = 0
        self._playing = True

        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumSize(320, 180)
        self.preview_label.setStyleSheet("background:#111;")

        self.trim_slider = TrimSlider()
        self.trim_slider.set_count(len(frames))
        self.trim_slider.range_changed.connect(self._on_range_changed)

        self.frame_info_label = QLabel()

        # --- playback controls row ---
        self.play_btn = QPushButton("Pause")
        self.play_btn.setIcon(theme.icon("fa5s.pause"))
        self.play_btn.clicked.connect(self._toggle_play)

        # --- export options ---
        self.fps_spin = QSpinBox()
        self.fps_spin.setRange(1, 60)
        self.fps_spin.setValue(fps)

        self.width_combo = QComboBox()
        for w in WIDTH_PRESETS:
            self.width_combo.addItem("Original" if w == 0 else f"{w}px", w)
        self.width_combo.setCurrentIndex(WIDTH_PRESETS.index(settings.get("output_width", 480)) if settings.get("output_width", 480) in WIDTH_PRESETS else 2)

        self.speed_spin = QDoubleSpinBox()
        self.speed_spin.setRange(0.1, 5.0)
        self.speed_spin.setSingleStep(0.1)
        self.speed_spin.setValue(settings.get("playback_speed", 1.0))

        self.loop_spin = QSpinBox()
        self.loop_spin.setRange(0, 100)
        self.loop_spin.setValue(settings.get("loop_count", 0))
        self.loop_spin.setSpecialValueText("Infinite")

        self.reverse_check = QCheckBox("Reverse")
        self.boomerang_check = QCheckBox("Boomerang")

        self.quality_combo = QComboBox()
        self.quality_combo.addItem("Quality (ffmpeg)", "quality")
        self.quality_combo.addItem("Fast (Pillow)", "fast")
        self.quality_combo.setCurrentIndex(0 if settings.get("quality_mode", "quality") == "quality" else 1)

        self.export_btn = QPushButton("Export GIF")
        self.export_btn.setIcon(theme.icon("fa5s.file-export"))
        self.export_btn.clicked.connect(self._export)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setVisible(False)

        self.status_label = QLabel("")
        self.status_label.setObjectName("statusLabel")

        self._build_layout()

        self.play_timer = QTimer(self)
        self.play_timer.timeout.connect(self._advance_preview)
        self._restart_play_timer()
        self._refresh_preview_sequence()

    def _build_layout(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.addWidget(self.preview_label, stretch=1)
        layout.addWidget(self.trim_slider)

        info_row = QHBoxLayout()
        info_row.addWidget(self.play_btn)
        info_row.addWidget(self.frame_info_label)
        info_row.addStretch()
        layout.addLayout(info_row)

        playback_group = QGroupBox("Playback")
        playback_form = QFormLayout(playback_group)
        playback_form.addRow("FPS:", self.fps_spin)
        playback_form.addRow("Speed:", self.speed_spin)

        effects_group = QGroupBox("Effects")
        effects_layout = QVBoxLayout(effects_group)
        effects_layout.addWidget(self.reverse_check)
        effects_layout.addWidget(self.boomerang_check)
        effects_layout.addStretch()

        output_group = QGroupBox("Output")
        output_form = QFormLayout(output_group)
        output_form.addRow("Width:", self.width_combo)
        output_form.addRow("Loops:", self.loop_spin)

        groups_row = QHBoxLayout()
        groups_row.addWidget(playback_group)
        groups_row.addWidget(effects_group)
        groups_row.addWidget(output_group)
        layout.addLayout(groups_row)

        export_group = QGroupBox("Export")
        export_layout = QVBoxLayout(export_group)
        export_row = QHBoxLayout()
        export_row.addWidget(QLabel("Encode:"))
        export_row.addWidget(self.quality_combo)
        export_row.addStretch()
        export_row.addWidget(self.export_btn)
        export_layout.addLayout(export_row)
        export_layout.addWidget(self.progress_bar)
        export_layout.addWidget(self.status_label)
        layout.addWidget(export_group)

        self.fps_spin.valueChanged.connect(self._on_option_changed)
        self.speed_spin.valueChanged.connect(self._on_option_changed)
        self.width_combo.currentIndexChanged.connect(self._on_option_changed)
        self.loop_spin.valueChanged.connect(self._on_option_changed)
        self.reverse_check.toggled.connect(self._on_option_changed)
        self.boomerang_check.toggled.connect(self._on_option_changed)
        self.quality_combo.currentIndexChanged.connect(self._on_option_changed)

    # ---- trim / preview -----------------------------------------------

    def _on_range_changed(self, in_point, out_point):
        self._refresh_preview_sequence()

    def _on_option_changed(self, *_args):
        # Any editor control (fps, speed, width, loops, reverse, boomerang,
        # quality) restarts the preview from the top so the change is
        # immediately visible instead of only showing up on export.
        self._restart_play_timer()
        self._refresh_preview_sequence()
        self._playing = True
        self.play_btn.setText("Pause")
        self.play_btn.setIcon(theme.icon("fa5s.pause"))

    def _refresh_preview_sequence(self):
        self._preview_frames = self._trimmed_frames()
        self._preview_index = 0
        self._update_preview()

    def _restart_play_timer(self):
        fps = max(1, self.fps_spin.value())
        speed = self.speed_spin.value() or 1.0
        interval_ms = max(1, int(1000 / (fps * speed)))
        self.play_timer.start(interval_ms)

    def _toggle_play(self):
        self._playing = not self._playing
        self.play_btn.setText("Pause" if self._playing else "Play")
        self.play_btn.setIcon(theme.icon("fa5s.pause" if self._playing else "fa5s.play"))

    def _advance_preview(self):
        if not self._playing or not self._preview_frames:
            return
        self._preview_index += 1
        if self._preview_index >= len(self._preview_frames):
            self._preview_index = 0
        self._update_preview()

    def _update_preview(self):
        if not self._preview_frames:
            return
        idx = min(self._preview_index, len(self._preview_frames) - 1)
        pix = pil_to_qpixmap(self._preview_frames[idx])
        scaled = pix.scaled(self.preview_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.preview_label.setPixmap(scaled)
        in_pt, out_pt = self.trim_slider.in_point(), self.trim_slider.out_point()
        self.frame_info_label.setText(
            f"Frame {idx + 1}/{len(self._preview_frames)}  (trim {in_pt + 1}-{out_pt + 1})"
        )

    # ---- export ---------------------------------------------------------

    def _trimmed_frames(self) -> list:
        in_pt, out_pt = self.trim_slider.in_point(), self.trim_slider.out_point()
        frames = self.frames[in_pt:out_pt + 1]
        if self.reverse_check.isChecked():
            frames = list(reversed(frames))
        if self.boomerang_check.isChecked():
            frames = frames + list(reversed(frames))[1:-1]
        return frames

    def _export(self):
        default_dir = self.settings.get("save_folder", "")
        out_path, _ = QFileDialog.getSaveFileName(self, "Export GIF", f"{default_dir}/capture.gif", "GIF files (*.gif)")
        if not out_path:
            return

        frames = self._trimmed_frames()
        if not frames:
            QMessageBox.warning(self, "Export failed", "No frames in trimmed range.")
            return

        width_value = self.width_combo.currentData()
        loop_value = self.loop_spin.value()
        quality_mode = self.quality_combo.currentData()

        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.export_btn.setEnabled(False)
        self.status_label.setText("Exporting...")

        def progress_cb(stage, frac):
            self.progress_bar.setValue(int(frac * 100))
            self.status_label.setText(stage)
            self.repaint()

        try:
            report = encode_gif(
                frames,
                out_path,
                fps=self.fps_spin.value(),
                width=(width_value or None),
                loop_count=loop_value,
                quality_mode=quality_mode,
                progress_cb=progress_cb,
            )
            size_kb = report["file_size"] / 1024
            self.status_label.setText(
                f"Saved {report['path']} — {report['frame_count']} frames, {size_kb:.0f} KB, engine={report['engine']}"
            )
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))
            self.status_label.setText("Export failed.")
        finally:
            self.progress_bar.setVisible(False)
            self.export_btn.setEnabled(True)
