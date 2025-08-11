"""Async DXF loading utilities for the GUI."""

import threading
from PySide6.QtCore import QObject, Signal

from utils.dxf_parser import generate_recipe_from_dxf


class DxfService(QObject):
    """Service responsible for loading and parsing DXF files."""

    dxf_loaded = Signal(str, object)
    error_occurred = Signal(str)

    def load_dxf(self, filename: str, scale: float = 1.0, z_height: float | None = None):
        """Load a DXF file in a background thread.

        Parameters
        ----------
        filename:
            Path to the DXF file.
        scale:
            Scale factor applied to the parsed geometry.
        z_height:
            Constant Z height applied to all generated vertices.  If ``None`` is
            provided the recipe will default to ``0.0``.  Callers should supply
            the manipulator's current Z position to avoid unintended vertical
            motion.
        """

        def worker():
            try:
                data = generate_recipe_from_dxf(
                    filename,
                    resolution=1.0,
                    scale=scale,
                    z_height=z_height if z_height is not None else 0.0,
                )
                self.dxf_loaded.emit(filename, data)
            except Exception as exc:  # pragma: no cover - dependent on DXF file
                self.error_occurred.emit(str(exc))

        threading.Thread(target=worker, daemon=True).start()

