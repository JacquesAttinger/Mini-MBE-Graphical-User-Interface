from PySide6.QtWidgets import (QGroupBox, QVBoxLayout, QHBoxLayout,
                              QLabel, QDoubleSpinBox, QPushButton)
from PySide6.QtCore import Signal

from utils.speed import MIN_AXIS_SPEED

class AxisControlWidget(QGroupBox):
    """Widget for controlling a single axis"""

    # Signals
    move_requested = Signal(float, float)  # position, speed
    stop_requested = Signal()
    
    def __init__(self, axis_name: str, controller, parent=None):
        super().__init__(f"{axis_name} Axis Control", parent)
        self.controller = controller
        self._setup_ui()
        
    def _setup_ui(self):
        layout = QVBoxLayout()
        
        # Position control
        pos_layout = QHBoxLayout()
        pos_layout.addWidget(QLabel("Position (mm):"))
        self.pos_spin = QDoubleSpinBox()
        self.pos_spin.setRange(-1000, 1000)
        self.pos_spin.setDecimals(4)
        pos_layout.addWidget(self.pos_spin)
        
        # Speed control
        speed_layout = QHBoxLayout()
        speed_layout.addWidget(QLabel("Speed (mm/s):"))
        self.speed_spin = QDoubleSpinBox()
        self.speed_spin.setDecimals(6)
        self.speed_spin.setRange(MIN_AXIS_SPEED, 10)
        self.speed_spin.setSingleStep(MIN_AXIS_SPEED)
        self.speed_spin.setValue(0.1)
        speed_layout.addWidget(self.speed_spin)
        
        # Buttons
        btn_layout = QHBoxLayout()
        self.move_btn = QPushButton("Move")
        self.move_btn.setStyleSheet("background-color: #5cb85c; color: white;")
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setStyleSheet("background-color: #d9534f; color: white;")
        self.home_btn = QPushButton("Home")
        
        btn_layout.addWidget(self.move_btn)
        btn_layout.addWidget(self.stop_btn)
        btn_layout.addWidget(self.home_btn)
        
        # Connect signals
        self.move_btn.clicked.connect(self._on_move)
        self.stop_btn.clicked.connect(self._on_stop)
        
        # Add to layout
        layout.addLayout(pos_layout)
        layout.addLayout(speed_layout)
        layout.addLayout(btn_layout)
        self.setLayout(layout)
    
    def _on_move(self):
        """Handle move button click"""
        position = self.pos_spin.value()
        speed = self.speed_spin.value()
        self.move_requested.emit(position, speed)
    
    def _on_stop(self):
        """Handle stop button click"""
        self.stop_requested.emit()
