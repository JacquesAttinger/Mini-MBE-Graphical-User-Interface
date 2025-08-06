from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QMessageBox
from ui.widgets.axis_control import AxisControlWidget
from ui.widgets.position_canvas import PositionCanvas
from ui.widgets.status_panel import StatusPanel

class MainWindow(QMainWindow):
    """Main application window"""
    
    def __init__(self, controllers, initial_connection_status, parent=None):
        super().__init__(parent)
        self.controllers = controllers
        self._setup_ui()
        self._update_initial_connection_status(initial_connection_status)
        self._connect_signals()
        
    def _update_initial_connection_status(self, status):
        """Update UI with initial connection status"""
        all_connected = all(status.values())
        self.status_panel.update_connection_status(all_connected)
        
        for axis, is_connected in status.items():
            msg = f"{axis.upper()} axis: {'Connected' if is_connected else 'Disconnected'}"
            self.status_panel.log_message(msg)
        
    def _setup_ui(self):
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        
        # Left panel - controls
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        
        # Add axis controls
        for axis in ['x', 'y', 'z']:
            axis_control = AxisControlWidget(
                axis_name=axis.upper(),
                controller=self.controllers[axis]
            )
            left_layout.addWidget(axis_control)
        
        # Right panel - visualization
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        
        # Position canvas
        self.position_canvas = PositionCanvas()
        right_layout.addWidget(self.position_canvas, stretch=1)
        
        # Status panel
        self.status_panel = StatusPanel()
        right_layout.addWidget(self.status_panel)
        
        # Combine panels
        main_layout.addWidget(left_panel)
        main_layout.addWidget(right_panel, stretch=1)
        
        # Window properties
        self.setWindowTitle("MBE Manipulator Control")
        self.resize(1200, 800)
    
    def _connect_signals(self):
        """Connect controller signals to UI updates"""
        for axis, controller in self.controllers.items():
            controller.status_updated.connect(
                lambda msg, a=axis: self.status_panel.log_message(f"{a.upper()}: {msg}")
            )
            controller.position_updated.connect(
                lambda pos, a=axis: self._handle_position_update(a, pos)
            )
            controller.error_occurred.connect(
                lambda msg, a=axis: self._handle_error(a, msg)
            )

    def _handle_position_update(self, axis, position):
        """Update position canvas and log position"""
        self.position_canvas.update_position(
            self.controllers['x'].get_position() or 0,
            self.controllers['y'].get_position() or 0
        )
        self.status_panel.log_message(f"{axis.upper()} position: {position:.3f} mm")

    def _handle_error(self, axis, message):
        """Log and display error messages"""
        self.status_panel.log_message(f"{axis.upper()} ERROR: {message}")
        QMessageBox.critical(self, f"{axis.upper()} Axis Error", message)