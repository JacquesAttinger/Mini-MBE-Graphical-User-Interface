from PySide6.QtWidgets import (QWidget, QVBoxLayout, QTextEdit, QLabel, 
                              QScrollArea, QHBoxLayout)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

class StatusPanel(QWidget):
    """Widget for displaying system status messages and logs"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        
    def _setup_ui(self):
        # Main layout
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Title label
        title = QLabel("System Status")
        title.setStyleSheet("font-weight: bold; font-size: 12pt;")
        layout.addWidget(title)
        
        # Create text area with scroll
        self.text_area = QTextEdit()
        self.text_area.setReadOnly(True)
        self.text_area.setFont(QFont("Consolas", 9))
        self.text_area.setLineWrapMode(QTextEdit.NoWrap)
        
        # Add scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.text_area)
        layout.addWidget(scroll)
        
        # Connection status indicator
        self.connection_status = QLabel("Disconnected")
        self.connection_status.setAlignment(Qt.AlignRight)
        self.connection_status.setStyleSheet(
            "font-weight: bold; color: #d9534f; font-size: 10pt;"
        )
        layout.addWidget(self.connection_status)
        
        self.setLayout(layout)
    
    def log_message(self, message: str):
        """Add a message to the status log"""
        self.text_area.append(message)
        # Auto-scroll to bottom
        self.text_area.verticalScrollBar().setValue(
            self.text_area.verticalScrollBar().maximum()
        )
    
    def update_connection_status(self, connected: bool):
        """Update connection status indicator"""
        if connected:
            self.connection_status.setText("Connected")
            self.connection_status.setStyleSheet(
                "font-weight: bold; color: #5cb85c; font-size: 10pt;"
            )
        else:
            self.connection_status.setText("Disconnected")
            self.connection_status.setStyleSheet(
                "font-weight: bold; color: #d9534f; font-size: 10pt;"
            )