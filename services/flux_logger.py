"""CSV logger dedicated to flux readings."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Optional, TextIO


class FluxLogger:
    """Persist timestamped flux readings to a CSV file."""

    def __init__(self, base_dir: str | Path | None = None) -> None:
        if base_dir is None:
            base_dir = Path(__file__).resolve().parents[1] / "logs" / "flux"
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._fh: Optional[TextIO] = None
        self._writer: Optional[csv.writer] = None

    def start(self, path: str | Path) -> None:
        """Open ``path`` for writing and prepare the CSV writer."""
        if self._fh is not None:
            raise RuntimeError("Flux logger already started")

        file_path = Path(path)
        if not file_path.is_absolute():
            file_path = self.base_dir / file_path
        file_path.parent.mkdir(parents=True, exist_ok=True)

        self._fh = file_path.open("w", newline="", encoding="utf-8")
        self._writer = csv.writer(self._fh)
        self._writer.writerow(["timestamp", "flux_nA"])
        self._fh.flush()

    def append(self, timestamp: datetime, flux_nanoamps: float) -> None:
        """Append a timestamp/flux row to the CSV file."""
        if self._writer is None or self._fh is None:
            raise RuntimeError("Flux logger not started")
        self._writer.writerow([timestamp.isoformat(timespec="milliseconds"), flux_nanoamps])
        self._fh.flush()

    def stop(self) -> None:
        """Close the file handle if open."""
        if self._fh is not None:
            self._fh.close()
            self._fh = None
            self._writer = None

    def set_base_dir(self, base_dir: str | Path) -> None:
        """Update the base directory for relative file paths."""
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)


__all__ = ["FluxLogger"]
