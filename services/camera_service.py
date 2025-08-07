"""Asynchronous camera service using VmbPy."""

from __future__ import annotations

import threading
import time
from typing import Optional

from PySide6.QtCore import QObject, Signal

try:  # pragma: no cover - dependent on optional hardware
    from vmbpy import VmbSystem, FrameStatus, PixelFormat
except Exception:  # pragma: no cover - handled at runtime
    VmbSystem = None  # type: ignore
    FrameStatus = None  # type: ignore
    PixelFormat = None  # type: ignore


class CameraService(QObject):
    """Background service that streams frames from the first available camera."""

    frame_received = Signal(object)
    error_occurred = Signal(str)
    camera_ready = Signal(float, float, float, float)

    def __init__(self) -> None:
        super().__init__()
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._cam = None
        self._exp_feat = None
        self._gain_feat = None

    # ------------------------------------------------------------------
    def start(self) -> None:
        """Start the camera streaming in a background thread."""
        if self._thread:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    # ------------------------------------------------------------------
    def stop(self) -> None:
        """Stop streaming and close the camera."""
        self._running = False
        if self._thread:
            self._thread.join()
            self._thread = None

    # ------------------------------------------------------------------
    def _run(self) -> None:  # pragma: no cover - hardware interaction
        if VmbSystem is None:
            self.error_occurred.emit("vmbpy library not available")
            return
        try:
            with VmbSystem.get_instance() as system:
                cams = system.get_all_cameras()
                if not cams:
                    self.error_occurred.emit("No cameras found")
                    return
                self._cam = cams[0]
                self._cam._open()

                try:
                    exp_feat = self._cam.get_feature_by_name("ExposureTime")
                    exp_min, exp_max = exp_feat.get_range()
                    self._exp_feat = exp_feat
                except Exception:
                    exp_min, exp_max = 0.0, 100.0

                try:
                    gain_feat = self._cam.get_feature_by_name("Gain")
                    gain_min, gain_max = gain_feat.get_range()
                    self._gain_feat = gain_feat
                except Exception:
                    gain_min, gain_max = 0.0, 100.0

                self.camera_ready.emit(exp_min, exp_max, gain_min, gain_max)

                self._cam.start_streaming(handler=self._frame_handler, buffer_count=5)
                while self._running:
                    time.sleep(0.01)
                self._cam.stop_streaming()
                self._cam._close()
        except Exception as exc:
            self.error_occurred.emit(str(exc))

    # ------------------------------------------------------------------
    def _frame_handler(self, cam, stream, frame):  # pragma: no cover - hardware interaction
        if FrameStatus and frame.get_status() == FrameStatus.Complete:
            try:
                if frame.get_pixel_format() != PixelFormat.Bgr8:
                    frame.convert_pixel_format(PixelFormat.Bgr8)
            except Exception:
                pass
            self.frame_received.emit(frame.as_numpy_ndarray())
        cam.queue_frame(frame)

    # ------------------------------------------------------------------
    def set_exposure(self, value: int) -> None:
        if self._cam and self._exp_feat:
            try:
                self._exp_feat.set(value)
            except Exception as exc:
                self.error_occurred.emit(f"Failed to set exposure: {exc}")

    # ------------------------------------------------------------------
    def set_gain(self, value: int) -> None:
        if self._cam and self._gain_feat:
            try:
                self._gain_feat.set(value)
            except Exception as exc:
                self.error_occurred.emit(f"Failed to set gain: {exc}")
