"""Window for displaying the live camera feed."""

from PySide6.QtWidgets import QMainWindow, QMessageBox, QVBoxLayout, QWidget

from services.camera_service import CameraService
from widgets.camera_view import CameraView


class CameraWindow(QMainWindow):
    """Dedicated window that shows frames from the camera service."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Camera")
        self._service = CameraService()
        self._setup_ui()
        self._connect_signals()
        self._service.start()

    # ------------------------------------------------------------------
    def _setup_ui(self) -> None:
        central = QWidget()
        layout = QVBoxLayout(central)
        self._view = CameraView()
        layout.addWidget(self._view)
        self.setCentralWidget(central)

    # ------------------------------------------------------------------
    def _connect_signals(self) -> None:
        self._service.frame_received.connect(self._view.update_image)
        self._service.error_occurred.connect(self._show_error)

    # ------------------------------------------------------------------
    def _show_error(self, message: str) -> None:
        QMessageBox.critical(self, "Camera Error", message)

    # ------------------------------------------------------------------
    def closeEvent(self, event):  # pragma: no cover - GUI callback
        self._service.stop()
        super().closeEvent(event)

