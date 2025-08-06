# Main window for Multi-Axis Manipulator Control GUI

import sys
import time
import threading
import logging
import numpy as np
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QDoubleSpinBox, QGroupBox, QStatusBar, QMessageBox,
    QTextEdit, QFileDialog, QFrame, QSizePolicy, QScrollArea, QTabWidget, QProgressBar
)
from PySide6.QtCore import QTimer, Signal, QObject, Qt
from PySide6.QtGui import QFont

# Local imports: controller logic, custom widgets, and DXF parser
from controllers.smcd14_controller import (
    ManipulatorController, validate_velocity, adjust_axis_velocity, calculate_velocity_components
)
from widgets.position_canvas import EnhancedPositionCanvas
from widgets.pan_controls import PanControlWidget
from services.path_service import PathService
from utils.dxf_parser import (parse_dxf, generate_recipe_from_dxf)

# Basic logging setup
logging.basicConfig()
logging.getLogger("pymodbus").setLevel(logging.ERROR)  # Silence noisy pymodbus logs

# Constants for manipulator setup
HOST = "169.254.151.255"
PORT = 502
TIMEOUT = 10
AXIS_SLAVE_MAP = {"X": 1, "Y": 2, "Z": 3}

# Define Qt signals for cross-thread communication
class ManipulatorSignals(QObject):
    status_updated = Signal(str)                  # Generic status update
    position_updated = Signal(str, float)         # Axis and position data
    error_occurred = Signal(str, str)             # Axis and error message
    dxf_loaded = Signal(int)                      # DXF path count
    connection_changed = Signal(str, bool)        # Axis and connection state
    dxf_parsed = Signal(object)  # Emits parsed geometry when ready

class MultiAxisControlApp(QMainWindow):
    def __init__(self):
        super().__init__()

        # Window setup
        self.setWindowTitle("MBE Manipulator Control System")
        self.resize(1400, 850)

        # Create controller instances for each axis
        self.controllers = {axis: ManipulatorController(HOST, PORT, TIMEOUT, AXIS_SLAVE_MAP[axis])
                            for axis in ["X", "Y", "Z"]}

        # Initial states
        self.dxf_geometry = None
        self.current_zoom = 5.0
        self.min_zoom = 0.001  #1μm view
        self.max_zoom = 20.0
        self.last_positions = {"X": 0, "Y": 0, "Z": 0}
        self.signals = ManipulatorSignals()

        # Setup UI and internal connections
        self.setup_ui()
        self.setup_connections()

        # Setup monitoring timer (calls threaded monitor function)
        self.monitoring = True
        thread = threading.Thread(target=self.monitor_loop, daemon=True)
        thread.start()

        # Attempt initial connection to all axes
        self.connect_all_axes()

    # ----------------------
    # UI Setup
    # ----------------------
    def setup_ui(self):
        # Central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # === Left Panel ===
        left_panel = QFrame()
        left_panel.setFrameShape(QFrame.StyledPanel)
        left_panel.setMinimumWidth(420)
        left_panel.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        left_layout = QVBoxLayout(left_panel)

        # Connection status display
        self.connection_status = QLabel("Disconnected")
        self.connection_status.setStyleSheet("font-weight: bold; color: #d9534f;")
        left_layout.addWidget(self.connection_status)

        # Tabs for controls
        tab_widget = QTabWidget()
        left_layout.addWidget(tab_widget)

        # --- Control Tab ---
        control_tab = QWidget()
        control_tab_layout = QVBoxLayout(control_tab)
        tab_widget.addTab(control_tab, "Control")

        self.axis_groups = {}

        # Axis control widgets
        for axis in ["X", "Y", "Z"]:
            group = QGroupBox(f"{axis} Axis Control")
            group_layout = QVBoxLayout()

            # Position input
            pos_layout = QHBoxLayout()
            pos_layout.addWidget(QLabel("Position (mm):"))
            pos_spin = QDoubleSpinBox()
            pos_spin.setRange(-1000, 1000)
            pos_spin.setDecimals(4)
            pos_spin.setSingleStep(0.1)
            pos_layout.addWidget(pos_spin)

            # Velocity input
            vel_layout = QHBoxLayout()
            vel_layout.addWidget(QLabel("Velocity (mm/s):"))
            vel_spin = QDoubleSpinBox()
            vel_spin.setRange(0.1, 100)
            vel_spin.setValue(1)
            vel_spin.setDecimals(2)
            vel_spin.setSingleStep(1)
            vel_layout.addWidget(vel_spin)

            # Action buttons
            btn_layout = QHBoxLayout()
            move_btn = QPushButton("Move")
            move_btn.setStyleSheet("background-color: #5cb85c; color: white;")
            move_btn.clicked.connect(lambda _, a=axis, p=pos_spin, v=vel_spin: self.move_axis(a, p.value(), v.value()))
            stop_btn = QPushButton("Stop")
            stop_btn.setStyleSheet("background-color: #d9534f; color: white;")
            stop_btn.clicked.connect(lambda _, a=axis: self.emergency_stop(a))
            home_btn = QPushButton("Home")
            home_btn.clicked.connect(lambda _, a=axis: self.home_axis(a))
            btn_layout.addWidget(move_btn)
            btn_layout.addWidget(stop_btn)
            btn_layout.addWidget(home_btn)

            # Assemble group layout
            group_layout.addLayout(pos_layout)
            group_layout.addLayout(vel_layout)
            group_layout.addLayout(btn_layout)
            group.setLayout(group_layout)

            # Store references for later use
            self.axis_groups[axis] = {
                'pos_spin': pos_spin,
                'vel_spin': vel_spin,
                'move_btn': move_btn,
                'stop_btn': stop_btn,
                'home_btn': home_btn
            }
            control_tab_layout.addWidget(group)

        # --- DXF Import ---
        dxf_group = QGroupBox("Pattern Import")
        dxf_layout = QVBoxLayout()

        upload_btn = QPushButton("Load DXF File")
        upload_btn.setStyleSheet("background-color: #5bc0de; color: white;")
        upload_btn.clicked.connect(self.upload_dxf)

        scale_layout = QHBoxLayout()
        scale_layout.addWidget(QLabel("Scale Factor:"))
        self.dxf_scale = QDoubleSpinBox()
        self.dxf_scale.setValue(1.0)
        self.dxf_scale.setDecimals(4)
        self.dxf_scale.setSingleStep(0.1)
        scale_layout.addWidget(self.dxf_scale)

        self.dxf_info = QLabel("No file loaded")
        self.dxf_info.setStyleSheet("font-style: italic; color: #777;")

        dxf_layout.addWidget(upload_btn)
        dxf_layout.addLayout(scale_layout)
        dxf_layout.addWidget(self.dxf_info)
        dxf_group.setLayout(dxf_layout)

        control_tab_layout.addWidget(dxf_group)

        # --- Log Panel ---
        log_group = QGroupBox("System Log")
        log_layout = QVBoxLayout()

        self.status_log = QTextEdit()
        self.status_log.setReadOnly(True)
        self.status_log.setFont(QFont("Consolas", 9))

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(self.status_log)

        log_layout.addWidget(scroll_area)
        log_group.setLayout(log_layout)
        left_layout.addWidget(log_group)

        # === Middle Panel ===
        mid_panel = QFrame()
        mid_panel.setFrameShape(QFrame.StyledPanel)
        mid_layout = QVBoxLayout(mid_panel)

        # Position canvas (visualization)
        self.position_canvas = EnhancedPositionCanvas()
        mid_layout.addWidget(self.position_canvas, stretch=1)
        
        # Pan Controls (bottom right)
        self.setup_pan_controls(mid_layout)

        # Path Controls (embark, pause, progress bar)
        # === Right Panel ===
        right_panel = QFrame()
        right_panel.setFrameShape(QFrame.StyledPanel)
        right_layout = QVBoxLayout(right_panel)

        # Tabs for controls
        tab_widget_right = QTabWidget()
        right_layout.addWidget(tab_widget_right)

        pattern_tab = QWidget()
        pattern_layout = QVBoxLayout(pattern_tab)
        tab_widget_right.addTab(pattern_tab, "Path Control")

        # --- Path Panel ---
        path_panel = QGroupBox("Path Following")
        path_layout1 = self.setup_path_controls()
        path_panel.setLayout(path_layout1)
        pattern_layout.addWidget(path_panel)

        # Zoom and position display
        control_layout = QHBoxLayout()
        zoom_layout = QHBoxLayout()

        zoom_in_btn = QPushButton("Zoom In")
        zoom_in_btn.clicked.connect(self.zoom_in)
        zoom_out_btn = QPushButton("Zoom Out")
        zoom_out_btn.clicked.connect(self.zoom_out)
        zoom_layout.addWidget(zoom_in_btn)
        zoom_layout.addWidget(zoom_out_btn)

        self.position_readout = QLabel("Current Position: X: --, Y: --, Z: --")
        self.position_readout.setStyleSheet("font-weight: bold;")

        control_layout.addLayout(zoom_layout)
        control_layout.addStretch()
        control_layout.addWidget(self.position_readout)
        mid_layout.addLayout(control_layout)

        # Add panels to main layout
        main_layout.addWidget(left_panel)
        main_layout.addWidget(mid_panel)
        main_layout.addWidget(right_panel)

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        ######
        
    # ----------------------
    # Signal Connections
    # ----------------------
    def setup_connections(self):
        # Connect signals to their corresponding slots
        self.signals.status_updated.connect(self.log_status)
        self.signals.position_updated.connect(self.update_position_display)
        self.signals.error_occurred.connect(self.show_error)
        self.signals.dxf_loaded.connect(self.on_dxf_loaded)
        self.signals.connection_changed.connect(self.update_connection_status)
        self.signals.dxf_parsed.connect(self.on_dxf_parsed)

    # ----------------------
    # Pan controls (for position canvas)
    # ----------------------

    def setup_pan_controls(self, layout):
        """Create compact pan controls at bottom right of canvas"""
        # Create container widget for right alignment
        pan_container = QWidget()
        pan_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        
        # Use horizontal layout with right alignment
        hbox = QHBoxLayout(pan_container)
        hbox.setContentsMargins(0, 0, 0, 0)
        hbox.addStretch()  # Pushes everything to right
        
        # Create the pan controls
        self.pan_controls = PanControlWidget(self.position_canvas)
        self.pan_controls.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        
        # Style to be more compact
        self.pan_controls.setStyleSheet("""
            QPushButton {
                min-width: 25px;
                max-width: 25px;
                min-height: 25px;
                max-height: 25px;
                font-size: 12px;
                margin: 0;
                padding: 0;
            }
        """)
        
        hbox.addWidget(self.pan_controls)
        
        # Add to your existing layout (assuming VBox layout)
        layout.addWidget(pan_container, alignment=Qt.AlignLeft)

    def keyPressEvent(self, event):
        """Add keyboard panning controls"""
        if self.position_canvas.hasFocus():
            if event.key() == Qt.Key_Up:
                self.position_canvas.pan_up(0.5)
            elif event.key() == Qt.Key_Down:
                self.position_canvas.pan_down(0.5)
            elif event.key() == Qt.Key_Left:
                self.position_canvas.pan_left(0.5)
            elif event.key() == Qt.Key_Right:
                self.position_canvas.pan_right(0.5)
            elif event.key() == Qt.Key_Home:
                self.position_canvas.reset_view()
        else:
            super().keyPressEvent(event)

    # ----------------------
    # Monitor function (threaded)
    # ----------------------

    def monitor_loop(self):
        while self.monitoring:
            for axis, ctrl in self.controllers.items():
                if not ctrl.client:
                    continue
                try:
                    pos = ctrl.read_position()
                    self.signals.position_updated.emit(axis, pos)
                    status_val = ctrl._read_status()
                    err = ctrl.read_error_code()
                    if err != 0:
                        error_msg = self.get_error_message(err)
                        self.signals.error_occurred.emit(axis, error_msg)
                except Exception as e:
                    self.signals.error_occurred.emit(axis, f"Monitor error: {str(e)}")

            time.sleep(0.3)  # sleep for 300 ms

    # ----------------------
    # Connect all axes at startup
    # ----------------------
    def connect_all_axes(self):
        for axis, ctrl in self.controllers.items():
            try:
                if ctrl.connect():
                    self.signals.connection_changed.emit(axis, True)
                    self.log_status(f"{axis} axis connected successfully")
                else:
                    self.log_status(f"Failed to connect {axis} axis")
            except Exception as e:
                self.log_status(f"Connection error ({axis}): {str(e)}")

    # ----------------------
    # UI Update: Connection status indicator
    # ----------------------
    def update_connection_status(self, axis, connected):
        if connected:
            self.connection_status.setText("Connected")
            self.connection_status.setStyleSheet("font-weight: bold; color: #5cb85c;")
        else:
            self.connection_status.setText("Disconnected")
            self.connection_status.setStyleSheet("font-weight: bold; color: #d9534f;")

    # ----------------------
    # Logging helper
    # ----------------------
    def log_status(self, message):
        timestamp = time.strftime("%H:%M:%S", time.localtime())
        self.status_log.append(f"[{timestamp}] {message}")
        self.status_bar.showMessage(message, 3000)  # Show message in status bar for 3 sec

    # ----------------------
    # Error display
    # ----------------------
    def show_error(self, axis, message):
        full_msg = f"[{axis}] ERROR: {message}"
        self.log_status(full_msg)
        QMessageBox.critical(self, f"{axis} Axis Error", message)

    # ----------------------
    # UI Update: Position readout and canvas
    # ----------------------
    def update_position_display(self, axis, position):
        self.last_positions[axis] = position
        x = self.last_positions.get("X", 0)
        y = self.last_positions.get("Y", 0)
        z = self.last_positions.get("Z", 0)

        self.position_readout.setText(f"Current Position: X: {x:.3f}, Y: {y:.3f}, Z: {z:.3f} mm")
        self.position_canvas.update_position(x, y)

    # ----------------------
    # DXF load signal handler
    # ----------------------
    def _debug_dxf_geometry(self, geometry):
        """Log DXF structure for troubleshooting."""
        if isinstance(geometry, dict) and 'display' in geometry:
            paths = geometry['display']['paths']
        else:
            paths = geometry
        
        for i, path in enumerate(paths):
            self.log_status(f"Path {i}: {len(path)} points")
            for j, pt in enumerate(path):
                self.log_status(f"  Point {j}: {pt[0]:.6f}, {pt[1]:.6f}")

    def on_dxf_loaded(self, path_count):
        self.dxf_info.setText(f"Loaded DXF with {path_count} paths")

    # def on_dxf_parsed(self, data):
    #     filename, geometry = data
    #     self.dxf_geometry = geometry
    #     scale_factor = self.dxf_scale.value()
    #     self.position_canvas.update_dxf(self.dxf_geometry, scale_factor)
    #     self.dxf_info.setText(f"Loaded: {filename.split('/')[-1]} ({len(self.dxf_geometry)} paths)")
    #     self.log_status(f"Loaded DXF with {len(self.dxf_geometry)} paths")

    def setup_path_controls(self):
        # Path Control Panel
        # path_panel = QGroupBox("Path Following")
        # layout = QHBoxLayout()
        path_layout = QVBoxLayout()
         # Initialize path service
        self.path_service = PathService(self.controllers)
        self.path_service.progress_updated.connect(self.update_position_display)
        self.path_service.path_completed.connect(self.on_path_completed)
        self.path_service.paused.connect(self.on_path_paused)


        # Embark Button
        start_stop_layout = QHBoxLayout()
        self.embark_button = QPushButton("Embark")
        self.embark_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                padding: 5px;
            }
            QPushButton:disabled {
                background-color: #CCCCCC;
            }
        """)
        self.embark_button.clicked.connect(self.start_path_following)
        
        # Pause/Resume Button
        self.pause_button = QPushButton("Pause")
        self.pause_button.setStyleSheet("""
            QPushButton {
                background-color: #FFC107;
                color: black;
                font-weight: bold;
                padding: 5px;
            }
        """)
        self.pause_button.clicked.connect(self.toggle_pause)
        self.pause_button.setEnabled(False)

        start_stop_layout.addWidget(self.embark_button)
        start_stop_layout.addWidget(self.pause_button)
        
        # Progress Display
        self.progress_label = QLabel("Ready")
        self.progress_bar = QProgressBar()
        
        path_layout.addLayout(start_stop_layout)
        path_layout.addWidget(self.progress_label)
        path_layout.addWidget(self.progress_bar)
        # path_panel.setLayout(layout)
        
        return path_layout
        # return path_panel


    # ----------------------
    # Modified DXF Loading Section
    # ----------------------
    
    def upload_dxf(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Select DXF File", "", "DXF Files (*.dxf)")
        if not filename:
            return

        def parse_thread():
            try:
                # Get both display and movement data
                dxf_data = generate_recipe_from_dxf(
                    filename,
                    resolution=1.0,
                    scale=self.dxf_scale.value(),
                    z_height=0.0
                )
                self.signals.dxf_parsed.emit((filename, dxf_data))
            except Exception as e:
                self.signals.error_occurred.emit("SYSTEM", f"Error loading DXF: {str(e)}")

        thread = threading.Thread(target=parse_thread, daemon=True)
        thread.start()

    def start_path_following(self):
        self.embark_button.setEnabled(False)
        self.pause_button.setEnabled(True)
        self.pause_button.setText("Pause")
        self.path_service.embark()

    def toggle_pause(self):
        if self.path_service.is_paused:
            self.path_service.resume()
            self.pause_button.setText("Pause")
        else:
            self.path_service.pause()
            self.pause_button.setText("Resume")

    def on_path_completed(self):
        self.embark_button.setEnabled(True)
        self.pause_button.setEnabled(False)
        self.statusBar().showMessage("Path completed successfully")

    def on_path_paused(self):
        self.pause_button.setText("Resume")
        self.pause_button.clicked.disconnect()
        self.pause_button.clicked.connect(self.resume_path_following)

    def resume_path_following(self):
        self.pause_button.setText("Pause")
        self.pause_button.clicked.disconnect()
        self.pause_button.clicked.connect(self.pause_path_following)
        self.path_service.resume()

    def update_progress_display(self):
        progress = self.path_service.get_progress() * 100
        self.progress_bar.setValue(int(progress))
        
        if self.path_service.current_path:
            current_seg = self.path_service.get_current_segment()
            total_segs = len(self.path_service.current_path) - 1
            self.progress_label.setText(
                f"Segment {current_seg}/{total_segs} | "
                f"{self.path_service.path_metadata['total_length']:.1f}mm total"
            )

    # ----------------------
    # Enhanced DXF Signal Handler
    # ----------------------

    def on_dxf_parsed(self, data):
        filename, dxf_data = data
        try:
            # Update canvas with display data
            self.position_canvas.update_dxf(dxf_data, self.dxf_scale.value())
            
            # Update path service with movement data
            self.path_service.load_path({
                'vertices': dxf_data['movement']['vertices'],
                'segments': dxf_data['movement']['segments'],
                'metadata': dxf_data['metadata']
            })
            
            # UI updates
            self.dxf_info.setText(f"Loaded: {filename.split('/')[-1]}")
            self.log_status(f"Loaded DXF with {dxf_data['metadata']['original_path_count']} paths")
            self.embark_button.setEnabled(True)
            #################################Debugging
            # print(dxf_data['movement']['vertices']) 
            print('metadata', dxf_data['metadata'])
            
        except Exception as e:
            self.show_error("DXF Error", f"Failed to process DXF: {str(e)}")
        
        self._debug_dxf_geometry(dxf_data)  # Log coordinates for debugging

    # ----------------------
    # Axis movement command
    # ----------------------
    def move_axis(self, axis, position, velocity):
        def move_thread():
            ctrl = self.controllers[axis]
            try:
                # Ensure connection
                if not ctrl.client:
                    if not ctrl.connect():
                        self.signals.error_occurred.emit(axis, "Connect failed")
                        return

                ctrl.motor_on()  # Energize motor
                ctrl.move_absolute(position=position, velocity=velocity)  # Issue move command

                # Wait until movement completes or timeout
                if ctrl.wait_until_in_position(timeout=15):
                    self.signals.status_updated.emit(f"[{axis}] Reached target position")
                else:
                    self.signals.error_occurred.emit(axis, "Timeout waiting for target position")

                # Final position and error check
                pos_actual = ctrl.read_position()
                self.signals.status_updated.emit(f"[{axis}] Actual position: {pos_actual:.3f} mm")
                err = ctrl.read_error_code()
                if err != 0:
                    self.signals.error_occurred.emit(axis, f"Error code: {err}")

            except Exception as e:
                self.signals.error_occurred.emit(axis, f"Move error: {str(e)}")

        # Start in daemon thread
        thread = threading.Thread(target=move_thread, daemon=True)
        thread.start()

    # ----------------------
    # Manipulator move to point command
    # ----------------------

    def move_to_point(self, target_pos, velocity):
        """
        Public method with velocity validation and user feedback
        """
        if not self.controllers["X"].client or not self.controllers["Y"].client or not self.controllers["Z"].client:
            # If no controller is connected, show error message
            print("Error: No controller connected")
            return False
            
        # Get current position from controllers
        try:
            current_pos = (
                self.last_positions["X"],
                self.last_positions["Y"],
                self.last_positions["Z"]
            )
            vx, vy, vz = calculate_velocity_components(current_pos, target_pos, velocity)
        except Exception as e:
            print(f"Position read error: {e}")
            # self.pause()
            return
        
        self.move_axis("X", target_pos[0], vx)
        self.move_axis("Y", target_pos[1], vy)
        self.move_axis("Z", target_pos[2], vz)

        # try:
        #     current_pos = self.get_current_position()
        #     success = self.controllers.move_to_point(current_pos, target_pos, velocity)
            
        #     if not success:
        #         print("Movement failed due to velocity constraints")
        #         return False
                
        #     return True
            
        # except ValueError as e:
        #     print(f"Movement error: {e}")
        #     # You could show this error in the GUI status bar
        #     self.statusBar().showMessage(str(e))
        #     return False

    # ----------------------
    # Emergency stop command
    # ----------------------
    def emergency_stop(self, axis):
        def stop_thread():
            ctrl = self.controllers[axis]
            try:
                if not ctrl.client:
                    if not ctrl.connect():
                        self.signals.error_occurred.emit(axis, "Connect failed for stop")
                        return

                ctrl.emergency_stop()
                self.signals.status_updated.emit(f"[{axis}] Emergency stop executed")

            except Exception as e:
                self.signals.error_occurred.emit(axis, f"Stop error: {str(e)}")

        thread = threading.Thread(target=stop_thread, daemon=True)
        thread.start()

    # ----------------------
    # Homing procedure (placeholder)
    # ----------------------
    def home_axis(self, axis):
        def home_thread():
            ctrl = self.controllers[axis]
            try:
                if not ctrl.client:
                    if not ctrl.connect():
                        self.signals.error_occurred.emit(axis, "Connect failed for homing")
                        return

                ctrl.motor_on()
                # 🚧 NOTE: Implement homing here if supported by controller
                self.signals.status_updated.emit(f"[{axis}] Homing procedure started")

            except Exception as e:
                self.signals.error_occurred.emit(axis, f"Homing error: {str(e)}")

        thread = threading.Thread(target=home_thread, daemon=True)
        thread.start()

    # ----------------------
    # Zoom controls
    # ----------------------
    def zoom_in(self):
        new_zoom = self.current_zoom / 1.5
        if new_zoom >= self.min_zoom:
            self.current_zoom = new_zoom
            self.position_canvas.update_plot(self.current_zoom)

    def zoom_out(self):
        new_zoom = self.current_zoom * 1.5
        if new_zoom <= self.max_zoom:
            self.current_zoom = new_zoom
            self.position_canvas.update_plot(self.current_zoom)

    # ----------------------
    # Error code helper
    # ----------------------
    def get_error_message(self, error_code):
        error_messages = {
            20: "Position error - motor may have lost steps",
            30: "Both limit switches active - check connections",
            40: "Axis not enabled - check enable signal",
            50: "Axis not homed - perform homing procedure",
            60: "Motor is off - energize motor first"
        }
        return error_messages.get(error_code, f"Unknown error code: {error_code}")

    # ----------------------
    # Graceful exit handling
    # ----------------------
    def closeEvent(self, event):
        # Stop monitoring loop thread
        self.monitoring = False

        # Check if any controllers are still connected
        connected = any(ctrl.client for ctrl in self.controllers.values())
        if connected:
            reply = QMessageBox.question(
                self,
                "Confirm Exit",
                "Some axes are still connected. Are you sure you want to quit?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.No:
                event.ignore()
                return

        # Disconnect all controllers
        for axis, ctrl in self.controllers.items():
            try:
                ctrl.disconnect()
            except:
                pass

        event.accept()

# ----------------------
# Application entry point
# ----------------------
def main():
    app = QApplication(sys.argv)
    window = MultiAxisControlApp()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()