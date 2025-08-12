# widgets/coordinate_checker.py
from __future__ import annotations
from typing import List, Tuple
from dataclasses import dataclass
import csv
from PySide6 import QtCore, QtWidgets
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
                               QTableWidgetItem, QPushButton, QDoubleSpinBox, QCheckBox)

Point = Tuple[float, float]

@dataclass
class CheckerResult:
    paths_mm: List[List[Point]]

class CoordinateCheckerDialog(QDialog):
    accepted_paths: List[List[Point]]

    def __init__(self, paths_mm: List[List[Point]], meta, parent=None):
        super().__init__(parent)
        self.setWindowTitle("DXF Coordinate Checker")
        self.raw_paths = [list(p) for p in paths_mm]
        self.accepted_paths = [list(p) for p in paths_mm]
        self.meta = meta

        self.table = QTableWidget(self)
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["#","X (mm)","Y (mm)","Δ from prev (mm)","Path #"])
        self.table.horizontalHeader().setStretchLastSection(True)

        # Controls
        self.flipY = QCheckBox("Flip Y")
        self.offsetX = QDoubleSpinBox(); self.offsetY = QDoubleSpinBox()
        self.offsetX.setRange(-1e6, 1e6); self.offsetY.setRange(-1e6, 1e6)
        self.offsetX.setDecimals(4); self.offsetY.setDecimals(4)
        self.offsetX.setSuffix(" mm"); self.offsetY.setSuffix(" mm")
        self.scaleBox = QDoubleSpinBox(); self.scaleBox.setRange(1e-6, 1e6); self.scaleBox.setValue(1.0)
        self.scaleBox.setDecimals(6)

        self.jumpThresh = QDoubleSpinBox(); self.jumpThresh.setRange(0.0, 1e6); self.jumpThresh.setValue(0.5)
        self.jumpThresh.setDecimals(4); self.jumpThresh.setSuffix(" mm")

        applyBtn = QPushButton("Apply transform")
        exportBtn = QPushButton("Export CSV")
        okBtn = QPushButton("Accept")
        cancelBtn = QPushButton("Cancel")

        # Layout
        top = QHBoxLayout()
        top.addWidget(QLabel(f"Units: {meta.units_name} → mm    "
                             f"Paths: {meta.path_count}    Vertices: {meta.vertex_count}    "
                             f"BBox (mm): [{meta.bbox[0]:.3f}, {meta.bbox[1]:.3f}]–[{meta.bbox[2]:.3f}, {meta.bbox[3]:.3f}]    "
                             f"Total length: {meta.total_length_mm:.3f} mm"))
        v = QVBoxLayout(self)
        v.addLayout(top)
        v.addWidget(self.table)

        ctrls = QHBoxLayout()
        ctrls.addWidget(self.flipY)
        ctrls.addWidget(QLabel("Scale:")); ctrls.addWidget(self.scaleBox)
        ctrls.addWidget(QLabel("Offset X:")); ctrls.addWidget(self.offsetX)
        ctrls.addWidget(QLabel("Offset Y:")); ctrls.addWidget(self.offsetY)
        ctrls.addWidget(QLabel("Jump warn ≥")); ctrls.addWidget(self.jumpThresh)
        v.addLayout(ctrls)

        btns = QHBoxLayout()
        for b in (applyBtn, exportBtn, okBtn, cancelBtn):
            btns.addWidget(b)
        v.addLayout(btns)

        # Wire
        applyBtn.clicked.connect(self.apply_transform)
        exportBtn.clicked.connect(self.export_csv)
        okBtn.clicked.connect(self.accept)
        cancelBtn.clicked.connect(self.reject)

        self.refresh_table()

    def refresh_table(self):
        pts = [(i, x, y, path_idx)
               for path_idx, path in enumerate(self.accepted_paths)
               for i, (x, y) in enumerate(path)]
        self.table.setRowCount(len(pts))
        jump_thresh = self.jumpThresh.value()
        prev = None
        for row, (i, x, y, path_idx) in enumerate(pts):
            d = 0.0 if prev is None else ((x - prev[0])**2 + (y - prev[1])**2) ** 0.5
            prev = (x, y)
            for col, val in enumerate([i, x, y, d, path_idx]):
                item = QTableWidgetItem(f"{val:.6f}" if isinstance(val, float) else str(val))
                if col == 3 and d >= jump_thresh:
                    item.setBackground(QtWidgets.QColor(255, 230, 200))  # highlight big jumps
                self.table.setItem(row, col, item)
        self.table.resizeColumnsToContents()

    def apply_transform(self):
        s = self.scaleBox.value()
        ox = self.offsetX.value()
        oy = self.offsetY.value()
        flip = -1.0 if self.flipY.isChecked() else 1.0
        self.accepted_paths = [[(s*x + ox, s*(y*flip) + oy) for x, y in path] for path in self.raw_paths]
        self.refresh_table()

    def export_csv(self):
        fn, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Export coordinates", "coords.csv", "CSV (*.csv)")
        if not fn:
            return
        with open(fn, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["path_index", "vertex_index", "x_mm", "y_mm"])
            for pi, path in enumerate(self.accepted_paths):
                for vi, (x, y) in enumerate(path):
                    w.writerow([pi, vi, x, y])

    def result(self) -> CheckerResult:
        return CheckerResult(paths_mm=self.accepted_paths)
