"""CaptureWorker: grabs frames from a screen region on a timer, in its own thread."""
import time

import mss
from PIL import Image
from PySide6.QtCore import QThread, Signal


class CaptureWorker(QThread):
    """Captures the given (x, y, w, h) screen rect at the requested fps.

    Runs until `stop()` is called or `max_duration` seconds elapse.
    Emits `frame_captured(count)` after each frame (for a live counter/
    preview) and `capture_finished(frames, actual_fps)` when done.
    """

    frame_captured = Signal(int)
    capture_finished = Signal(list, float)

    def __init__(self, rect: tuple, fps: int = 15, max_duration: float = 0, parent=None):
        super().__init__(parent)
        self.x, self.y, self.w, self.h = rect
        self.fps = max(1, fps)
        self.max_duration = max_duration  # 0 = unlimited, stopped manually
        self._running = False

    def stop(self):
        self._running = False

    def run(self):
        self._running = True
        frames = []
        timestamps = []
        interval = 1.0 / self.fps
        region = {"left": self.x, "top": self.y, "width": self.w, "height": self.h}

        start = time.monotonic()
        next_frame_at = start

        with mss.mss() as sct:
            while self._running:
                now = time.monotonic()
                if self.max_duration and (now - start) >= self.max_duration:
                    break

                if now < next_frame_at:
                    time.sleep(min(next_frame_at - now, interval))
                    continue

                raw = sct.grab(region)
                img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
                frames.append(img)
                timestamps.append(now)
                self.frame_captured.emit(len(frames))

                next_frame_at += interval
                # If we've fallen far behind (system under load), resync
                # instead of trying to burn through a backlog of frames.
                if next_frame_at < now:
                    next_frame_at = now + interval

        elapsed = time.monotonic() - start
        actual_fps = (len(frames) - 1) / elapsed if len(frames) > 1 and elapsed > 0 else float(self.fps)
        self.capture_finished.emit(frames, actual_fps)
