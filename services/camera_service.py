"""Service for streaming images from a VmbPy compatible camera."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

try:  # pragma: no cover - optional dependency
    from vmbpy import FrameStatus, PixelFormat, VmbSystem
except Exception:  # pragma: no cover - library may be missing on dev machines
    VmbSystem = None
    FrameStatus = None
    PixelFormat = None


class CameraService(QObject):
    """Thin wrapper around the VmbPy API emitting frames as numpy arrays."""

    frame_received = Signal(object)
    error_occurred = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._system = None
        self._camera = None

    # ------------------------------------------------------------------
    def start(self) -> None:
        """Open the first available camera and begin streaming."""

        if VmbSystem is None:
            self.error_occurred.emit("VmbPy SDK not available")
            return
        try:
            self._system = VmbSystem.get_instance()
            self._system.__enter__()
            cameras = self._system.get_all_cameras()
            if not cameras:
                raise RuntimeError("No camera detected")
            self._camera = cameras[0]
            self._camera.open()
            self._camera.start_streaming(handler=self._frame_handler, buffer_count=5)
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
            if self._system is not None:
                self._system.__exit__(None, None, None)
            self._camera = None
            self._system = None

    # ------------------------------------------------------------------
    def _frame_handler(self, cam, stream, frame) -> None:  # pragma: no cover - callback
        """Handle frames from the camera and emit as numpy arrays."""

        try:
            if FrameStatus is None or frame.get_status() == FrameStatus.Complete:
                try:
                    display = (
                        frame if PixelFormat is None or frame.get_pixel_format() == PixelFormat.Bgr8
                        else frame.convert_pixel_format(PixelFormat.Bgr8)
                    )
                except Exception:
                    display = frame
                img = display.as_numpy_ndarray()
                self.frame_received.emit(img)
        finally:
            cam.queue_frame(frame)

