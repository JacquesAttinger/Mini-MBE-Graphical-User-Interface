"""Service for streaming images from a Vimba compatible camera."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

try:  # pragma: no cover - optional dependency
    from vimba import FrameStatus, PixelFormat, Vimba
except Exception:  # pragma: no cover - library may be missing on dev machines
    Vimba = None
    FrameStatus = None
    PixelFormat = None


class CameraService(QObject):
    """Thin wrapper around the Vimba API emitting frames as numpy arrays."""

    frame_received = Signal(object)
    error_occurred = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._vimba = None
        self._camera = None

    # ------------------------------------------------------------------
    def start(self) -> None:
        """Open the first available camera and begin streaming."""

        if Vimba is None:
            self.error_occurred.emit("Vimba SDK not available")
            return
        try:
            self._vimba = Vimba.get_instance()
            self._vimba.__enter__()
            cameras = self._vimba.get_all_cameras()
            if not cameras:
                raise RuntimeError("No camera detected")
            self._camera = cameras[0]
            self._camera.open()
            self._camera.start_streaming(self._frame_handler, buffer_count=5)
        except Exception as exc:  # pragma: no cover - hardware dependent
            self.error_occurred.emit(str(exc))

    # ------------------------------------------------------------------
    def stop(self) -> None:
        """Stop streaming and release resources."""

        try:
            if self._camera is not None:
                self._camera.stop_streaming()
                self._camera.close()
        finally:
            if self._vimba is not None:
                self._vimba.__exit__(None, None, None)
            self._camera = None
            self._vimba = None

    # ------------------------------------------------------------------
    def _frame_handler(self, cam, frame) -> None:  # pragma: no cover - callback
        """Handle frames from the camera and emit as numpy arrays."""

        try:
            if FrameStatus is None or frame.get_status() == FrameStatus.Complete:
                try:
                    if PixelFormat is not None:
                        frame.convert_pixel_format(PixelFormat.Bgr8)
                except Exception:
                    pass
                img = frame.as_numpy_ndarray()
                self.frame_received.emit(img)
        finally:
            cam.queue_frame(frame)

