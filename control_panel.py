"""ControlPanel: small always-on-top toolbar wiring overlay + capture + editor."""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

import config
import theme
from capture import CaptureWorker
from editor import EditorWindow
from overlay import OverlayWindow


class ControlPanel(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Framezy")
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)

        self.settings = config.load()
        self.overlay: OverlayWindow | None = None
        self.capture_worker: CaptureWorker | None = None
        self.editor_window: EditorWindow | None = None

        self._build_ui()
        self._update_button_states()
        self._on_select_region()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        self.select_region_btn = QPushButton("Select Region")
        self.select_region_btn.setIcon(theme.icon("fa5s.crop-alt"))
        self.select_region_btn.clicked.connect(self._on_select_region)

        self.record_btn = QPushButton("Record")
        self.record_btn.setIcon(theme.icon("fa5s.circle"))
        self.record_btn.clicked.connect(self._on_record)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setIcon(theme.icon("fa5s.stop"))
        self.stop_btn.clicked.connect(self._on_stop)

        btn_row = QHBoxLayout()
        btn_row.addWidget(self.select_region_btn)
        btn_row.addWidget(self.record_btn)
        btn_row.addWidget(self.stop_btn)
        layout.addLayout(btn_row)

        settings_row = QHBoxLayout()
        settings_row.addWidget(QLabel("FPS:"))
        self.fps_spin = QSpinBox()
        self.fps_spin.setRange(1, 60)
        self.fps_spin.setValue(self.settings.get("fps", 20))
        settings_row.addWidget(self.fps_spin)

        settings_row.addWidget(QLabel("Max sec:"))
        self.duration_spin = QSpinBox()
        self.duration_spin.setRange(0, 3600)
        self.duration_spin.setSpecialValueText("Unlimited")
        self.duration_spin.setValue(0)
        settings_row.addWidget(self.duration_spin)
        layout.addLayout(settings_row)

        self.dimension_label = QLabel("No region selected")
        self.dimension_label.setObjectName("dimensionLabel")
        layout.addWidget(self.dimension_label)

        hint_label = QLabel("Drag border to move · drag dots to resize")
        hint_label.setObjectName("hintLabel")
        layout.addWidget(hint_label)

        self.status_label = QLabel("Ready.")
        self.status_label.setObjectName("statusLabel")
        layout.addWidget(self.status_label)

        self.resize(360, 180)

    def _update_button_states(self):
        has_region = self.overlay is not None
        is_recording = self.capture_worker is not None and self.capture_worker.isRunning()
        self.record_btn.setEnabled(has_region and not is_recording)
        self.stop_btn.setEnabled(is_recording)
        self.select_region_btn.setEnabled(not is_recording)

    # ---- region selection -------------------------------------------------

    def _on_select_region(self):
        if self.overlay is None:
            self.overlay = OverlayWindow(border_color=self.settings.get("overlay_border_color", "#26c6da"))
            self.overlay.geometry_changed.connect(self._on_overlay_geometry_changed)
        self.overlay.show()
        self._on_overlay_geometry_changed(self.overlay.capture_rect_global())
        self._update_button_states()

    def _on_overlay_geometry_changed(self, rect):
        self.dimension_label.setText(f"Region: {rect.width()} x {rect.height()} @ ({rect.x()}, {rect.y()})")

    # ---- recording -----------------------------------------------------

    def _on_record(self):
        if self.overlay is None:
            return
        rect = self.overlay.capture_rect_global()
        if rect.width() <= 0 or rect.height() <= 0:
            self.status_label.setText("Invalid region.")
            return

        # Hide the overlay's own border from the capture: the recorded rect
        # is the inner hole only, so leaving the overlay visible is fine —
        # the border pixels sit outside (rect is inner hole, not outer frame).
        fps = self.fps_spin.value()
        duration = self.duration_spin.value()

        self.capture_worker = CaptureWorker(
            (rect.x(), rect.y(), rect.width(), rect.height()),
            fps=fps,
            max_duration=duration,
        )
        self.capture_worker.frame_captured.connect(self._on_frame_captured)
        self.capture_worker.capture_finished.connect(self._on_capture_finished)
        self.capture_worker.start()
        self.overlay.set_locked(True)
        self.status_label.setText("Recording...")
        self._update_button_states()

    def _on_frame_captured(self, count):
        self.status_label.setText(f"Recording... {count} frames")

    def _on_stop(self):
        if self.capture_worker:
            self.capture_worker.stop()

    def _on_capture_finished(self, frames, actual_fps):
        self.status_label.setText(f"Captured {len(frames)} frames at {actual_fps:.1f} fps actual.")
        self._update_button_states()

        if self.overlay:
            self.overlay.set_locked(False)
            self.overlay.hide()

        if frames:
            self.editor_window = EditorWindow(frames, self.fps_spin.value(), self.settings)
            self.editor_window.show()

        self.capture_worker = None

    def closeEvent(self, event):
        config.save(self.settings)
        if self.overlay:
            self.overlay.close()
        super().closeEvent(event)
