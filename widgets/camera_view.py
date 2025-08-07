"""Simple widget for displaying numpy image frames."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel


class CameraView(QLabel):
    """QLabel subclass that converts numpy arrays into a pixmap."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(640, 480)

    # ------------------------------------------------------------------
    def update_image(self, frame) -> None:
        """Update the label pixmap from a numpy array."""

        if frame.ndim == 2:  # Grayscale
            height, width = frame.shape
            qimg = QImage(
                frame.data, width, height, width, QImage.Format_Grayscale8
            )
        else:  # Assume BGR
            height, width, channels = frame.shape
            qimg = QImage(
                frame.data,
                width,
                height,
                channels * width,
                QImage.Format_BGR888,
            )
        self.setPixmap(QPixmap.fromImage(qimg))

