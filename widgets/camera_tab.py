"""Camera tab with live view and basic controls."""

import math

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from services.camera_service import CameraService
from widgets.camera_view import CameraView


class CameraTab(QWidget):
    """Widget that displays the camera feed with exposure and gain sliders."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._service = CameraService()
        self._setup_ui()
        self._connect_signals()
        self._service.start()

    # ------------------------------------------------------------------
    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        self._view = CameraView()
        layout.addWidget(self._view)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Exposure"))
        self.exposure_slider = QSlider(Qt.Horizontal)
        controls.addWidget(self.exposure_slider)
        controls.addWidget(QLabel("Gain"))
        self.gain_slider = QSlider(Qt.Horizontal)
        controls.addWidget(self.gain_slider)
        layout.addLayout(controls)

    # ------------------------------------------------------------------
    def _connect_signals(self) -> None:
        self._service.frame_received.connect(self._view.update_image)
        self._service.error_occurred.connect(self._show_error)
        self._service.camera_ready.connect(self._apply_ranges)

    # ------------------------------------------------------------------
    def _apply_ranges(
        self, exp_min: float, exp_max: float, gain_min: float, gain_max: float
    ) -> None:
        exp_min_i = math.ceil(exp_min)
        exp_max_i = math.floor(exp_max)
        gain_min_i = math.ceil(gain_min)
        gain_max_i = math.floor(gain_max)

        self.exposure_slider.setRange(exp_min_i, exp_max_i)
        self.gain_slider.setRange(gain_min_i, gain_max_i)

        self.exposure_slider.setValue(exp_min_i)
        self.gain_slider.setValue(gain_min_i)

        self.exposure_slider.valueChanged.connect(self._service.set_exposure)
        self.gain_slider.valueChanged.connect(self._service.set_gain)

    # ------------------------------------------------------------------
    def _show_error(self, message: str) -> None:
        QMessageBox.critical(self, "Camera Error", message)

    # ------------------------------------------------------------------
    def closeEvent(self, event):  # pragma: no cover - GUI callback
        self._service.stop()
        super().closeEvent(event)
