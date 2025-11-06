"""CSV logger for timestamped pressure and temperature readings."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Optional, TextIO
from datetime import date, datetime, timedelta


class DataLogger:
    """Persist pressure and temperature readings to a CSV file."""

    def __init__(self, base_dir: str | Path | None = None) -> None:
        if base_dir is None:
            base_dir = Path(__file__).resolve().parents[1] / "logs" / "temperature_pressure"
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._fh: Optional[TextIO] = None
        self._writer: Optional[csv.writer] = None
        self._current_date: Optional[date] = None
        self._current_path: Optional[Path] = None

        # Immediately prepare today's log file so no manual setup is required.
        self.ensure_current_day()

    # ------------------------------------------------------------------
    def ensure_current_day(self) -> Path:
        """Make sure today's CSV file is ready for logging.

        Returns the path to the active log file.
        """

        today = date.today()
        self._ensure_writer(today)
        assert self._current_path is not None
        return self._current_path

    # ------------------------------------------------------------------
    def append(self, ts: str, pressure: float, temp: float) -> None:
        """Append a timestamp/pressure/temperature row to the CSV file."""
        timestamp_str = str(ts)
        try:
            ts_datetime = datetime.fromisoformat(timestamp_str)
        except ValueError:
            ts_datetime = datetime.now()

        self._ensure_writer(ts_datetime.date())
        if self._writer is None or self._fh is None:
            raise RuntimeError("Logger not initialised")

        self._fh.seek(0, 2)
        self._writer.writerow([timestamp_str, pressure, temp])
        self._fh.flush()

    # ------------------------------------------------------------------
    def stop(self) -> None:
        """Close the file handle if it is open."""
        if self._fh is not None:
            self._fh.close()
            self._fh = None
            self._writer = None
            self._current_date = None
            self._current_path = None

    # ------------------------------------------------------------------
    def set_base_dir(self, base_dir: str | Path) -> None:
        """Update the base directory for relative file paths."""
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    def trim_older_than(self, max_age_seconds: float) -> None:
        """Drop log rows older than ``max_age_seconds`` from the current file."""
        if self._fh is None or self._writer is None:
            return
        if max_age_seconds <= 0:
            return

        cutoff = datetime.now() - timedelta(seconds=max_age_seconds)

        self._fh.flush()
        self._fh.seek(0)
        reader = csv.reader(self._fh)
        try:
            header = next(reader)
        except StopIteration:
            self._fh.seek(0, 2)
            return

        rows_to_keep = []
        trimmed = False
        for row in reader:
            if not row:
                continue
            timestamp_str = row[0]
            try:
                row_time = datetime.fromisoformat(str(timestamp_str))
            except ValueError:
                # If timestamp parsing fails, keep the row to avoid data loss
                rows_to_keep.append(row)
                continue
            if row_time < cutoff:
                trimmed = True
                continue
            rows_to_keep.append(row)

        if not trimmed:
            # nothing trimmed; ensure pointer at end and exit
            self._fh.seek(0, 2)
            return

        self._fh.seek(0)
        writer = csv.writer(self._fh)
        writer.writerow(header)
        writer.writerows(rows_to_keep)
        self._fh.truncate()
        self._fh.flush()
        self._fh.seek(0, 2)

    # ------------------------------------------------------------------
    def _ensure_writer(self, target_date: date) -> None:
        """Open (or reopen) the CSV writer for ``target_date``."""

        if (
            self._writer is not None
            and self._fh is not None
            and self._current_date == target_date
        ):
            return

        if self._fh is not None:
            self._fh.close()

        filename = f"{target_date.isoformat()}.csv"
        file_path = self.base_dir / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)

        self._fh = file_path.open("a+", newline="", encoding="utf-8")
        self._fh.seek(0, 2)
        need_header = self._fh.tell() == 0
        self._writer = csv.writer(self._fh)
        if need_header:
            self._writer.writerow(["timestamp", "pressure", "temperature"])
            self._fh.flush()

        self._current_date = target_date
        self._current_path = file_path

    # ------------------------------------------------------------------
    @property
    def current_file_path(self) -> Optional[Path]:
        """Return the path of the active log file, if any."""

        return self._current_path

