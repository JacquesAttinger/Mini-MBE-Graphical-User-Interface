"""Async DXF loading utilities for the GUI."""

import os
import threading
from PySide6.QtCore import QObject, Signal

from utils.dxf_parser import generate_recipe_from_dxf


class DxfService(QObject):
    """Service responsible for loading and parsing DXF files."""

    dxf_loaded = Signal(str, object)
    error_occurred = Signal(str)

    def load_dxf(self, filename: str, scale: float = 1.0):
        """Load a DXF file in a background thread."""
        def worker():
            try:
                data = generate_recipe_from_dxf(
                    filename,
                    resolution=1.0,
                    scale=scale,
                    z_height=0.0,
                )
                self.dxf_loaded.emit(filename, data)
            except Exception as exc:  # pragma: no cover - dependent on DXF file
                self.error_occurred.emit(str(exc))

        threading.Thread(target=worker, daemon=True).start()

