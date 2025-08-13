"""Main application window for the miniMBE GUI."""

import os
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QFileDialog,
    QMessageBox,
    QTabWidget,
    QDoubleSpinBox,
    QLabel,
    QDialog,
    QTableWidget,
    QTableWidgetItem,
    QInputDialog,
)
from PySide6.QtGui import QColor
from PySide6.QtCore import Qt

from widgets.axis_control import AxisControlWidget
from widgets.position_canvas import EnhancedPositionCanvas as PositionCanvas
from widgets.status_panel import StatusPanel
from widgets.camera_tab import CameraTab
from widgets.modbus_panel import ModbusPanel

from math import hypot

# Manipulator workspace bounds in millimeters
X_MIN_MM, X_MAX_MM = -50.0, 50.0
Y_MIN_MM, Y_MAX_MM = -50.0, 50.0

class CoordinateCheckerDialog(QDialog):
    """
    Coordinate checker that tolerates various vertex formats:
      - (x, y)
      - (x, y, z, ...)
      - {'x': x, 'y': y, ...}
      - nested lists/tuples of any of the above
    It projects everything to (x_mm, y_mm) in the original order.
    """

    def __init__(self, vertices, speed=0.0, jump_warn_mm=0.5, parent=None):
        super().__init__(parent)
        self.setWindowTitle("DXF Coordinate Checker")
        self.vertices, self._dropped = self._coerce_xy(vertices)
        self.jump_warn_mm = float(jump_warn_mm)
        self.speed = float(speed)

        layout = QVBoxLayout(self)

        # Stats header
        stats = self._stats_text(self.vertices, self._dropped)
        self.stats_label = QLabel(stats)
        self.stats_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.stats_label)

        # Table of coordinates
        self.table = QTableWidget(self)
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "Index",
            "X (mm)",
            "Y (mm)",
            "Δ from prev (mm)",
            "Vx (mm/s)",
            "Vy (mm/s)",
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self.table)
        self._populate_table()

        # Buttons
        btn_row = QHBoxLayout()
        self.accept_btn = QPushButton("Accept")
        self.cancel_btn = QPushButton("Cancel")
        btn_row.addStretch(1)
        btn_row.addWidget(self.accept_btn)
        btn_row.addWidget(self.cancel_btn)
        layout.addLayout(btn_row)

        self.accept_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)

        self.resize(800, 500)

    # ---------- helpers ----------
    def _coerce_xy(self, vertices):
        """Return (xy_list, dropped_count). Accepts nested/heterogeneous inputs."""
        xy = []
        dropped = 0

        def add_one(v):
            nonlocal dropped
            if v is None:
                dropped += 1
                return
            # dict-like
            if isinstance(v, dict):
                if 'x' in v and 'y' in v:
                    xy.append((float(v['x']), float(v['y'])))
                elif 'X' in v and 'Y' in v:
                    xy.append((float(v['X']), float(v['Y'])))
                else:
                    dropped += 1
                return
            # list/tuple
            if isinstance(v, (list, tuple)):
                if v and isinstance(v[0], (list, tuple, dict)):
                    for sub in v:
                        add_one(sub)
                elif len(v) >= 2:
                    try:
                        xy.append((float(v[0]), float(v[1])))
                    except Exception:
                        dropped += 1
                else:
                    dropped += 1
                return
            # anything else
            dropped += 1

        # top-level may already be a path list or a flat list
        add_one(vertices) if isinstance(vertices, (list, tuple)) and vertices and isinstance(vertices[0], (list, tuple, dict)) else None
        if not xy:
            # treat as flat sequence
            for v in (vertices if isinstance(vertices, (list, tuple)) else [vertices]):
                add_one(v)

        return xy, dropped

    def _populate_table(self):
        vs = self.vertices
        self.table.setRowCount(len(vs))
        prev = None
        for i, (x, y) in enumerate(vs):
            self.table.setItem(i, 0, QTableWidgetItem(str(i)))
            self.table.setItem(i, 1, QTableWidgetItem(f"{x:.6f}"))
            self.table.setItem(i, 2, QTableWidgetItem(f"{y:.6f}"))
            d = 0.0 if prev is None else hypot(x - prev[0], y - prev[1])
            dist_itm = QTableWidgetItem(f"{d:.6f}")
            if d >= self.jump_warn_mm and i > 0:
                dist_itm.setBackground(QColor(255, 230, 200))  # highlight big jumps
            self.table.setItem(i, 3, dist_itm)

            if prev is None or d == 0.0:
                vx = vy = 0.0
            else:
                vx = self.speed * (x - prev[0]) / d
                vy = self.speed * (y - prev[1]) / d
            self.table.setItem(i, 4, QTableWidgetItem(f"{vx:.6f}"))
            self.table.setItem(i, 5, QTableWidgetItem(f"{vy:.6f}"))
            prev = (x, y)

        self.table.resizeColumnsToContents()

    @staticmethod
    def _stats_text(vertices, dropped):
        if not vertices:
            return "No vertices."
        xs = [p[0] for p in vertices]
        ys = [p[1] for p in vertices]
        minx, maxx = min(xs), max(xs)
        miny, maxy = min(ys), max(ys)
        w = maxx - minx
        h = maxy - miny
        dropped_txt = f"   |   Dropped: {dropped}" if dropped else ""
        return (f"Vertices: {len(vertices)}{dropped_txt}    "
                f"BBox (mm): [{minx:.3f}, {miny:.3f}] – [{maxx:.3f}, {maxy:.3f}]    "
                f"Size: {w:.3f} × {h:.3f} mm    "
                f"Units assumed: mm")

def _almost_equal(a, b, eps=1e-6):
    return hypot(a[0]-b[0], a[1]-b[1]) <= eps

class MainWindow(QMainWindow):
    """Top-level window coordinating UI widgets with backend services."""

    def __init__(self, manager, dxf_service, initial_status, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.dxf_service = dxf_service
        self.controllers = manager.controllers
        self._positions = {"x": 0.0, "y": 0.0, "z": 0.0}
        # Store both 3D vertices for motion and 2D vertices for display/checks
        self._vertices = []      # list[(x_mm, y_mm, z_mm)] used for execution
        self._vertices_xy = []   # list[(x_mm, y_mm)] for plotting and preflight
        self._segments = []      # whatever your service provides; kept for canvas drawing
        self._setup_ui()
        self._update_initial_connection_status(initial_status)
        self._connect_signals()

    # --- helpers -------------------------------------------------------
    def _sanitize_vertices(self, verts, eps=1e-6, close_path=True):
        """
        1) Coerce to (x, y)
        2) Drop consecutive duplicates
        3) Optionally append first vertex to close the loop
        4) Remove true backtracks A->B->A, but DO NOT remove the final 'A' if it closes the loop
        """
        # 1) coerce
        coerced = []
        for v in verts or []:
            if isinstance(v, dict):
                x = float(v.get("x", v.get("X")))
                y = float(v.get("y", v.get("Y")))
            else:
                x, y = float(v[0]), float(v[1])
            coerced.append((x, y))
        if not coerced:
            return []

        # 2) drop consecutive duplicates
        dedup = []
        for p in coerced:
            if not dedup or not _almost_equal(dedup[-1], p, eps):
                dedup.append(p)

        # 3) close the loop if requested
        if close_path and not _almost_equal(dedup[0], dedup[-1], eps):
            dedup.append(dedup[0])

        # 4) remove true backtracks A->B->A, but preserve final closing vertex
        cleaned = []
        for idx, p in enumerate(dedup):
            if len(cleaned) >= 2 and _almost_equal(cleaned[-2], p, eps):
                is_final_closing = (idx == len(dedup) - 1) and _almost_equal(p, dedup[0], eps)
                if not is_final_closing:
                    # pattern A,B,A -> drop B and skip this A
                    cleaned.pop()
                    continue
            cleaned.append(p)

        return cleaned

    def _preflight_path(self, verts, max_jump_mm=2.0):
        issues = []
        for i in range(1, len(verts)):
            d = hypot(verts[i][0]-verts[i-1][0], verts[i][1]-verts[i-1][1])
            if d > max_jump_mm:
                issues.append((i-1, i, d))
        return issues

    def _preflight_path(self, verts, max_jump_mm=2.0):
        """Return list of (i-1, i, distance_mm) for big jumps."""
        issues = []
        for i in range(1, len(verts)):
            d = hypot(verts[i][0]-verts[i-1][0], verts[i][1]-verts[i-1][1])
            if d > max_jump_mm:
                issues.append((i-1, i, d))
        return issues

    def _ensure_connected(self):
        """Make sure all axes have an active Modbus client before starting."""
        missing = []
        for axis, ctrl in self.manager.controllers.items():
            if getattr(ctrl, "client", None) is None:
                missing.append(axis.upper())
        if missing:
            QMessageBox.critical(
                self, "Connection Error",
                f"The following axes are not connected: {', '.join(missing)}.\n"
                "Connect before starting a pattern."
            )
            return False
        return True
    
    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------
    def _setup_ui(self):
        tabs = QTabWidget()
        self.setCentralWidget(tabs)

        # ------------------------------------------------------------------
        # Main control tab
        # ------------------------------------------------------------------
        main_tab = QWidget()
        tabs.addTab(main_tab, "Main")
        main_layout = QHBoxLayout(main_tab)

        # Left panel - axis controls
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        for axis in ["x", "y", "z"]:
            axis_control = AxisControlWidget(axis.upper(), self.controllers[axis])
            axis_control.move_requested.connect(
                lambda pos, vel, a=axis: self.manager.move_axis(a, pos, vel)
            )
            axis_control.stop_requested.connect(
                lambda a=axis: self.manager.emergency_stop(a)
            )
            axis_control.home_btn.clicked.connect(
                lambda _, a=axis: self.manager.home_axis(a)
            )
            left_layout.addWidget(axis_control)

        # Right panel - visualization + status
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        # Position canvas
        self.position_canvas = PositionCanvas()
        right_layout.addWidget(self.position_canvas, stretch=1)

        canvas_controls = QHBoxLayout()
        self.zoom_in_btn = QPushButton("Zoom In")
        self.zoom_out_btn = QPushButton("Zoom Out")
        self.center_pos_btn = QPushButton("Center Manipulator")
        canvas_controls.addWidget(self.zoom_in_btn)
        canvas_controls.addWidget(self.zoom_out_btn)
        canvas_controls.addWidget(self.center_pos_btn)
        right_layout.addLayout(canvas_controls)

        # DXF load button
        self.load_dxf_btn = QPushButton("Load DXF")
        right_layout.addWidget(self.load_dxf_btn)

        # Pattern controls
        self.nozzle_input = QDoubleSpinBox()
        self.nozzle_input.setPrefix("Nozzle Ø ")
        self.nozzle_input.setSuffix(" µm")
        self.nozzle_input.setRange(1.0, 1000.0)
        self.nozzle_input.setValue(12.0)
        right_layout.addWidget(self.nozzle_input)

        self.speed_input = QDoubleSpinBox()
        self.speed_input.setPrefix("Speed ")
        self.speed_input.setSuffix(" mm/s")
        self.speed_input.setDecimals(4)
        self.speed_input.setRange(0.0001, 2.0)
        self.speed_input.setValue(0.1)
        right_layout.addWidget(self.speed_input)

        self.start_pattern_btn = QPushButton("Start Pattern")
        self.start_pattern_btn.setEnabled(False)
        right_layout.addWidget(self.start_pattern_btn)

        self.pause_pattern_btn = QPushButton("Pause Pattern")
        self.pause_pattern_btn.setEnabled(False)
        right_layout.addWidget(self.pause_pattern_btn)

        self.progress_label = QLabel("Pattern progress: 0%")
        right_layout.addWidget(self.progress_label)

        # Status panel
        self.status_panel = StatusPanel()
        right_layout.addWidget(self.status_panel)

        main_layout.addWidget(left_panel)
        main_layout.addWidget(right_panel, stretch=3)
        self.modbus_panel = ModbusPanel()
        main_layout.addWidget(self.modbus_panel, stretch=1)

        # ------------------------------------------------------------------
        # Camera tab
        # ------------------------------------------------------------------
        self.camera_tab = CameraTab()
        tabs.addTab(self.camera_tab, "Camera")

        self.setWindowTitle("MBE Manipulator Control")
        self.resize(1200, 800)

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------
    def _connect_signals(self):
        self.manager.status_updated.connect(self.status_panel.log_message)
        self.manager.position_updated.connect(self._handle_position_update)
        self.manager.error_occurred.connect(self._handle_error)
        self.manager.connection_changed.connect(self._handle_connection_change)
        self.manager.modbus_event.connect(self.modbus_panel.log_event)
        self.manager.error_occurred.connect(self.modbus_panel.log_error)

        self.load_dxf_btn.clicked.connect(self._on_load_dxf)
        self.dxf_service.dxf_loaded.connect(self._handle_dxf_loaded)
        self.dxf_service.error_occurred.connect(
            lambda msg: self._handle_error("DXF", msg)
        )
        self.start_pattern_btn.clicked.connect(self._on_start_pattern)
        self.pause_pattern_btn.clicked.connect(self._toggle_pause_pattern)
        self.zoom_in_btn.clicked.connect(self.position_canvas.zoom_in)
        self.zoom_out_btn.clicked.connect(self.position_canvas.zoom_out)
        self.center_pos_btn.clicked.connect(
            self.position_canvas.center_on_position
        )
        self.manager.pattern_progress.connect(self._update_pattern_progress)
        self.manager.pattern_completed.connect(self._handle_pattern_completed)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------
    def _update_initial_connection_status(self, status):
        all_connected = all(status.values())
        self.status_panel.update_connection_status(all_connected)
        for axis, is_connected in status.items():
            state = "Connected" if is_connected else "Disconnected"
            self.status_panel.log_message(f"{axis.upper()} axis: {state}")

    def _handle_connection_change(self, axis, connected):
        all_connected = all(
            ctrl.client for ctrl in self.manager.controllers.values()
        )
        self.status_panel.update_connection_status(all_connected)
        state = "Connected" if connected else "Disconnected"
        self.status_panel.log_message(f"{axis.upper()} axis: {state}")

    def _handle_position_update(self, axis, position):
        previous = self._positions.get(axis)
        self._positions[axis] = position
        self.position_canvas.update_position(
            self._positions["x"],
            self._positions["y"],
        )
        self.status_panel.update_positions(
            self._positions["x"],
            self._positions["y"],
            self._positions["z"],
        )
        if previous is None or abs(position - previous) >= 0.01:
            self.status_panel.log_message(
                f"{axis.upper()} position: {position:.3f} mm"
            )

    def _handle_error(self, axis, message):
        self.status_panel.log_message(f"{axis} ERROR: {message}")
        QMessageBox.critical(self, f"{axis} Error", message)
        if self.modbus_panel.auto_logging_active:
            self.modbus_panel.stop_log()

    def _on_load_dxf(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "Select DXF File", "", "DXF Files (*.dxf)"
        )
        if filename:
            try:
                z_pos = self.manager.controllers['z'].read_position()
            except Exception:
                z_pos = self._positions.get('z', 0.0)
            # Query desired origin placement
            x_off, ok = QInputDialog.getDouble(
                self, "DXF Origin", "X coordinate (mm):", 0.0
            )
            if not ok:
                x_off = 0.0
            y_off, ok = QInputDialog.getDouble(
                self, "DXF Origin", "Y coordinate (mm):", 0.0
            )
            if not ok:
                y_off = 0.0
            # Let the existing service parse & build geometry
            self.dxf_service.load_dxf(
                filename, scale=1.0, z_height=z_pos, origin=(x_off, y_off)
            )

    def _handle_dxf_loaded(self, filename, geometry):
        self.position_canvas.update_dxf(geometry, scale_factor=1.0)

        raw_vertices = geometry['movement']['vertices'] or []
        # Determine Z height; recipes currently keep a constant Z
        z_val = raw_vertices[0][2] if raw_vertices and len(raw_vertices[0]) > 2 else 0.0

        # Clean path for display/preflight (2D) and build 3D path for motion
        self._vertices_xy = self._sanitize_vertices(raw_vertices, eps=1e-6, close_path=True)
        self._vertices = [(x, y, z_val) for x, y in self._vertices_xy]
        self._segments = geometry['movement'].get('segments', [])

        if not self._vertices_xy:
            self.start_pattern_btn.setEnabled(False)
            self.status_panel.log_message("DXF loaded, but no vertices found.")
            QMessageBox.warning(self, "Coordinate Checker", "No drawable vertices found.")
            return

        # Check workspace bounds
        oob = [
            (x, y) for x, y in self._vertices_xy
            if not (X_MIN_MM <= x <= X_MAX_MM and Y_MIN_MM <= y <= Y_MAX_MM)
        ]
        if oob:
            self.start_pattern_btn.setEnabled(False)
            self.status_panel.log_message("DXF rejected due to out-of-bounds vertices.")
            first_x, first_y = oob[0]
            QMessageBox.warning(
                self,
                "Coordinate Checker",
                (
                    "Pattern contains vertices outside manipulator bounds\n"
                    f"X: [{X_MIN_MM}, {X_MAX_MM}] mm, Y: [{Y_MIN_MM}, {Y_MAX_MM}] mm.\n"
                    f"First offending vertex: ({first_x:.3f}, {first_y:.3f})"
                ),
            )
            return

        checker = CoordinateCheckerDialog(
            self._vertices_xy,
            speed=self.speed_input.value(),
            jump_warn_mm=0.5,
            parent=self,
        )
        if checker.exec() == QDialog.Accepted:
            issues = self._preflight_path(self._vertices_xy, max_jump_mm=2.0)
            if issues:
                msg = "\n".join([f"{i}->{j}: {d:.3f} mm" for (i, j, d) in issues[:8]])
                proceed = QMessageBox.question(
                    self, "Large Jumps Detected",
                    "Found large moves in the path:\n"
                    f"{msg}\n\nProceed anyway?",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No
                )
                if proceed != QMessageBox.Yes:
                    self.start_pattern_btn.setEnabled(False)
                    self.status_panel.log_message("DXF rejected due to large jumps.")
                    return

            self.start_pattern_btn.setEnabled(True)
            self.status_panel.log_message(
                f"Loaded DXF: {os.path.basename(filename)} | Vertices (clean/closed): {len(self._vertices_xy)}"
            )
        else:
            self.start_pattern_btn.setEnabled(False)
            self.status_panel.log_message("DXF rejected by user after coordinate check.")

    def _on_start_pattern(self):
        if not self._vertices:
            return
        if not self._ensure_connected():
            return

        # Disable to prevent double-starts; reset UI
        self.start_pattern_btn.setEnabled(False)
        self.progress_label.setText("Pattern progress: 0%")
        self.pause_pattern_btn.setEnabled(False)
        self.pause_pattern_btn.setText("Pause Pattern")

        speed = self.speed_input.value()

        if hasattr(self.manager, "reset_path_state"):
            self.manager.reset_path_state()

        first = self._vertices[0]

        if not self.modbus_panel.logging_active:
            self.modbus_panel.start_log(auto=True)

        def _after_start(_target):
            self.manager.point_reached.disconnect(_after_start)
            reply = QMessageBox.question(
                self,
                "Starting Position",
                "Starting position achieved. Ready to begin printing?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if reply == QMessageBox.Yes:
                self.pause_pattern_btn.setEnabled(True)
                try:
                    is_closed = _almost_equal(self._vertices[0], self._vertices[-1])
                    path = self._vertices[1:-1] if is_closed else self._vertices[1:]
                    self._closing_leg = self._vertices[0] if is_closed else None
                    self._closing_speed = speed
                    self.manager.execute_path(path, speed)
                except Exception as exc:
                    self.start_pattern_btn.setEnabled(True)
                    self.pause_pattern_btn.setEnabled(False)
                    self._handle_error("PATH", str(exc))
            else:
                self.start_pattern_btn.setEnabled(True)
                self.pause_pattern_btn.setEnabled(False)
                self.status_panel.log_message("Pattern start cancelled")
                if self.modbus_panel.auto_logging_active:
                    self.modbus_panel.stop_log()

        self.manager.point_reached.connect(_after_start)
        self.manager.move_to_point(first, speed)

    def _toggle_pause_pattern(self):
        if self.pause_pattern_btn.text().startswith("Pause"):
            self.manager.pause_path()
            self.pause_pattern_btn.setText("Resume Pattern")
            self.status_panel.log_message("Pattern paused")
        else:
            self.manager.resume_path()
            self.pause_pattern_btn.setText("Pause Pattern")
            self.status_panel.log_message("Pattern resumed")

    def _update_pattern_progress(self, index, pct, remaining):
        self.position_canvas.draw_path_progress(index, self._vertices_xy, self._segments)
        self.progress_label.setText(
            f"Pattern progress: {pct*100:.1f}% | {remaining:.1f}s remaining"
        )

    def _handle_pattern_completed(self):
        self.progress_label.setText("Pattern progress: 100% | 0.0s remaining")

        def _finalize():
            self.status_panel.log_message("Pattern completed")
            self.start_pattern_btn.setEnabled(True)
            self.pause_pattern_btn.setEnabled(False)
            self.pause_pattern_btn.setText("Pause Pattern")
            if self.modbus_panel.auto_logging_active:
                self.modbus_panel.stop_log()
            try:
                self.manager.point_reached.disconnect(_finalize)
            except TypeError:
                pass

        if getattr(self, "_closing_leg", None) is not None:
            self.manager.point_reached.connect(_finalize)
            self.manager.move_to_point(
                self._closing_leg, getattr(self, "_closing_speed", 0.0)
            )
            self._closing_leg = None
        else:
            _finalize()

    # ------------------------------------------------------------------
    # Qt events
    # ------------------------------------------------------------------
    def closeEvent(self, event):  # pragma: no cover - GUI callback
        self.manager.disconnect_all()
        super().closeEvent(event)
