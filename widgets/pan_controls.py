# ui/widgets/pan_controls.py
from PySide6.QtWidgets import QWidget, QPushButton, QHBoxLayout
from PySide6.QtCore import Qt

class PanControlWidget(QWidget):
    def __init__(self, canvas, parent=None):
        super().__init__(parent)
        self.canvas = canvas
        self.setup_ui()
        
    def setup_ui(self):
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        
        # Create buttons
        self.btn_reset = QPushButton("⌂")
        self.btn_left = QPushButton("←")
        self.btn_up = QPushButton("↑")
        self.btn_down = QPushButton("↓")
        self.btn_right = QPushButton("→")
        
        # Set button properties
        for btn in [self.btn_reset, self.btn_left, self.btn_up, 
                   self.btn_down, self.btn_right]:
            btn.setFixedSize(30, 30)
            btn.setFocusPolicy(Qt.NoFocus)
        
        # Connect signals - THIS IS THE CRITICAL PART
        self.btn_reset.clicked.connect(self.canvas.reset_view)
        self.btn_up.clicked.connect(lambda: self.canvas.pan_view(0, 0.1))
        self.btn_down.clicked.connect(lambda: self.canvas.pan_view(0, -0.1))
        self.btn_left.clicked.connect(lambda: self.canvas.pan_view(-0.1, 0))
        self.btn_right.clicked.connect(lambda: self.canvas.pan_view(0.1, 0))

        # Set button tooltips
        self.btn_reset.setToolTip("Reset view to center")
        self.btn_up.setToolTip("Pan up")
        self.btn_down.setToolTip("Pan down")
        self.btn_left.setToolTip("Pan left") 
        self.btn_right.setToolTip("Pan right")
        
        # Add to layout
        layout.addWidget(self.btn_reset)
        layout.addWidget(self.btn_left)
        layout.addWidget(self.btn_up)
        layout.addWidget(self.btn_down)
        layout.addWidget(self.btn_right)
        
        self.setLayout(layout)