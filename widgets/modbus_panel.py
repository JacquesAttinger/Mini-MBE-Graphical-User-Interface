from __future__ import annotations

import datetime
import json
from typing import Dict

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QScrollArea,
)


class _CommandBox(QGroupBox):
    """Display the last command for a specific action."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(title, parent)
        layout = QVBoxLayout(self)
        self.desc_label = QLabel("-")
        self.desc_label.setWordWrap(True)
        self.raw_label = QLabel("")
        self.raw_label.setWordWrap(True)
        self.raw_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.desc_label)
        layout.addWidget(self.raw_label)

    def update_content(self, desc: str, raw: str) -> None:
        self.desc_label.setText(desc)
        self.raw_label.setText(raw)


class ModbusPanel(QWidget):
    """Panel showing recent Modbus traffic grouped by axis and command."""

    COMMANDS = [
        "move_absolute",
        "move_relative",
        "read_position",
        "emergency_stop",
        "clear_error",
        "set_backlash",
        "get_backlash",
        "read_error_code",
    ]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._log: list[Dict[str, str]] = []

        layout = QVBoxLayout(self)
        # Save button
        self.save_btn = QPushButton("Save Log")
        self.save_btn.clicked.connect(self._save_log)
        layout.addWidget(self.save_btn)

    # ------------------------------------------------------------------
    def log_event(self, axis: str, action: str, description: str, raw: str) -> None:
        entry = {
            "time": datetime.datetime.now().isoformat(),
            "axis": axis,
            "action": action,
            "description": description,
            "raw": raw,
        }
        self._log.append(entry)
        if boxes and action in boxes:
            boxes[action].update_content(description, raw)

    def log_error(self, axis: str, message: str) -> None:
        entry = {
            "time": datetime.datetime.now().isoformat(),
            "axis": axis,
            "error": message,
        }
        self._log.append(entry)
        label = QLabel(f"{axis.upper()}: {message}")
        label.setWordWrap(True)
        self._error_layout.insertWidget(self._error_layout.count() - 1, label)

    # ------------------------------------------------------------------
    def _save_log(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Modbus Log", "modbus_log.json", "JSON Files (*.json)"
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self._log, fh, indent=2)

