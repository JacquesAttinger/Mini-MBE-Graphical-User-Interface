from PySide6.QtWidgets import (QGroupBox, QVBoxLayout, QHBoxLayout, 
                              QLabel, QDoubleSpinBox, QPushButton)
from PySide6.QtCore import Signal

class AxisControlWidget(QGroupBox):
    """Widget for controlling a single axis"""
    
    # Signals
    move_requested = Signal(float, float)  # position, velocity
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
        
        # Velocity control
        vel_layout = QHBoxLayout()
        vel_layout.addWidget(QLabel("Velocity (mm/s):"))
        self.vel_spin = QDoubleSpinBox()
        self.vel_spin.setRange(0.1, 100)
        self.vel_spin.setValue(10)
        vel_layout.addWidget(self.vel_spin)
        
        # Buttons
        btn_layout = QHBoxLayout()
        self.move_btn = QPushButton("Move")
        self.stop_btn = QPushButton("Stop")
        self.home_btn = QPushButton("Home")
        
        btn_layout.addWidget(self.move_btn)
        btn_layout.addWidget(self.stop_btn)
        btn_layout.addWidget(self.home_btn)
        
        # Connect signals
        self.move_btn.clicked.connect(self._on_move)
        self.stop_btn.clicked.connect(self._on_stop)
        
        # Add to layout
        layout.addLayout(pos_layout)
        layout.addLayout(vel_layout)
        layout.addLayout(btn_layout)
        self.setLayout(layout)
    
    def _on_move(self):
        """Handle move button click"""
        position = self.pos_spin.value()
        velocity = self.vel_spin.value()
        self.move_requested.emit(position, velocity)
    
    def _on_stop(self):
        """Handle stop button click"""
        self.stop_requested.emit()
