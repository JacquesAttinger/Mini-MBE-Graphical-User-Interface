"""CSV logger for timestamped pressure and temperature readings."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Optional, TextIO
from datetime import datetime


class DataLogger:
    """Persist pressure and temperature readings to a CSV file."""

    def __init__(self, base_dir: str | Path | None = None) -> None:
        self.base_dir = Path(base_dir) if base_dir else Path.cwd()
        self._fh: Optional[TextIO] = None
        self._writer: Optional[csv.writer] = None

    # ------------------------------------------------------------------
    def start(self, path: str | Path) -> None:
        """Open ``path`` for writing and prepare the CSV writer."""
        if self._fh is not None:
            raise RuntimeError("Logger already started")

        file_path = Path(path)
        print(Path(path))
        if not file_path.is_absolute():
            file_path = self.base_dir / file_path
        file_path.parent.mkdir(parents=True, exist_ok=True)

        self._fh = file_path.open("w", newline="", encoding="utf-8")
        self._writer = csv.writer(self._fh)
        self._writer.writerow(["timestamp", "pressure", "temperature"])

    # ------------------------------------------------------------------
    def append(self, ts: float, pressure: float, temp: float) -> None:
        """Append a timestamp/pressure/temperature row to the CSV file."""
        if self._writer is None:
            raise RuntimeError("Logger not started")
        self._writer.writerow([ts, pressure, temp])
        if self._fh:
            self._fh.flush()

    # ------------------------------------------------------------------
    def stop(self) -> None:
        """Close the file handle if it is open."""
        if self._fh is not None:
            self._fh.close()
            self._fh = None
            self._writer = None

    # ------------------------------------------------------------------
    def set_base_dir(self, base_dir: str | Path) -> None:
        """Update the base directory for relative file paths."""
        self.base_dir = Path(base_dir)

