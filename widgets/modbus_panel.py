from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Dict

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGroupBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QScrollArea,
    QCheckBox,
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
        self._logging_active = False
        self._auto_logging = False

        layout = QVBoxLayout(self)

        # Start/Stop log button
        self.log_btn = QPushButton("Start Log")
        self.log_btn.clicked.connect(self._toggle_logging)
        layout.addWidget(self.log_btn)

        # Filter which actions are recorded
        self._action_enabled: dict[str, bool] = {cmd: True for cmd in self.COMMANDS}
        filter_group = QGroupBox("Recorded Actions")
        filter_layout = QVBoxLayout(filter_group)
        for cmd in self.COMMANDS:
            cb = QCheckBox(cmd)
            cb.setChecked(True)
            cb.stateChanged.connect(
                lambda state, c=cmd: self._update_action_visibility(
                    c, state == Qt.Checked
                )
            )
            filter_layout.addWidget(cb)
        layout.addWidget(filter_group)

        # Container for command boxes grouped by axis
        self._boxes: dict[str, dict[str, _CommandBox]] = {}

        self._scroll_widget = QWidget()
        self._scroll_layout = QVBoxLayout(self._scroll_widget)
        self._scroll_layout.setAlignment(Qt.AlignTop)

        # Error section at bottom of scroll area
        self._error_group = QGroupBox("Errors")
        self._error_layout = QVBoxLayout(self._error_group)
        self._error_layout.addStretch()

        self._scroll_layout.addWidget(self._error_group)
        self._scroll_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._scroll_widget)
        layout.addWidget(scroll)

    # ------------------------------------------------------------------
    def log_event(self, axis: str, action: str, description: str, raw: str) -> None:
        if not self._action_enabled.get(action, True):
            return
        boxes = self._ensure_axis(axis)
        if action in boxes:
            boxes[action].update_content(description, raw)
        if not self._logging_active:
            return
        entry = {
            "time": datetime.datetime.now().isoformat(),
            "axis": axis,
            "action": action,
            "description": description,
            "raw": raw,
        }
        self._log.append(entry)

    def log_error(self, axis: str, message: str) -> None:
        entry = {
            "time": datetime.datetime.now().isoformat(),
            "axis": axis,
            "error": message,
        }
        if self._logging_active:
            self._log.append(entry)
        label = QLabel(f"{axis.upper()}: {message}")
        label.setWordWrap(True)
        self._error_layout.insertWidget(self._error_layout.count() - 1, label)

    # ------------------------------------------------------------------
    def _ensure_axis(self, axis: str) -> dict[str, _CommandBox]:
        """Create command boxes for ``axis`` if they do not yet exist."""
        if axis not in self._boxes:
            group = QGroupBox(axis.upper())
            layout = QVBoxLayout(group)
            cmd_boxes: dict[str, _CommandBox] = {}
            for cmd in self.COMMANDS:
                box = _CommandBox(cmd)
                box.setVisible(self._action_enabled.get(cmd, True))
                layout.addWidget(box)
                cmd_boxes[cmd] = box
            self._scroll_layout.insertWidget(
                self._scroll_layout.indexOf(self._error_group), group
            )
            self._boxes[axis] = cmd_boxes
        return self._boxes[axis]
    
    def _update_action_visibility(self, action: str, enabled: bool) -> None:
        """Enable/disable logging and visibility for ``action``."""
        self._action_enabled[action] = enabled
        for axis_boxes in self._boxes.values():
            if action in axis_boxes:
                axis_boxes[action].setVisible(enabled)

    # ------------------------------------------------------------------
    def _toggle_logging(self) -> None:
        if self._logging_active:
            self.stop_log()
        else:
            self.start_log()

    def start_log(self, auto: bool = False) -> None:
        """Begin capturing Modbus events."""
        self._log = []
        self._logging_active = True
        self._auto_logging = auto
        self.log_btn.setText("Stop Log")

    def stop_log(self) -> None:
        """Stop logging and save collected events to disk."""
        if not self._logging_active:
            return
        self._logging_active = False
        self.log_btn.setText("Start Log")

        log_dir = Path("modbus logs")
        log_dir.mkdir(exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        mode = "auto" if self._auto_logging else "manual"
        path = log_dir / f"modbus_log_{mode}_{ts}.json"

        data = [
            e
            for e in self._log
            if e.get("action") is None or self._action_enabled.get(e.get("action"), True)
        ]
        with path.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        self._auto_logging = False

    @property
    def logging_active(self) -> bool:
        return self._logging_active

    @property
    def auto_logging_active(self) -> bool:
        return self._logging_active and self._auto_logging

