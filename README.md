# miniMBE GUI

A comprehensive graphical interface for controlling and monitoring a Molecular Beam Epitaxy (MBE) system, featuring real-time data logging, e-beam source control, and automated alert systems.

## Features

### 🌡️ Temperature and Pressure Monitoring
The **Temperature/Pressure** tab provides real-time monitoring and logging capabilities:
- **Live Data Display**: Monitor up to 8 temperature channels and 2 pressure gauges simultaneously
- **Data Logging**: Automatically saves timestamped readings to CSV files for analysis
- **Automated Alerts**: Configure low-pressure alerts via email to prevent system failures
- **Visualization**: Plot and analyze historical temperature and pressure trends
- **Configurable Sampling**: Adjust data collection intervals to match your experimental needs

### ⚡ E-Beam Source Control
The **E-Beam** tab offers precise control over electron beam evaporation sources:
- **Multi-Source Support**: Control multiple e-beam sources independently
- **Real-Time Flux Monitoring**: Track deposition rates with integrated flux sensor readings
- **Data Logging**: Record flux measurements with timestamps for process documentation
- **Safety Features**: Built-in monitoring to ensure safe operation
- **Calibration Support**: Easy configuration for different evaporant materials

### 🎯 3-Axis Manipulator Control
The **Main** tab provides comprehensive control over the XYZ manipulator system:
- **Individual Axis Control**: Independent control widgets for X, Y, and Z axes
- **Real-Time Position Tracking**: Live position updates displayed on visual canvas and status panel
- **Manual Positioning**: Move axes to specific coordinates at configurable speeds
- **Emergency Stop**: Immediate halt functionality for each axis
- **Homing Operations**: Automated homing sequences for axis calibration
- **Connection Monitoring**: Real-time Modbus connection status for each stepper motor
- **Workspace Visualization**: 2D canvas showing current manipulator position and loaded patterns

### 📐 DXF Pattern Execution
Advanced pattern execution system for automated deposition:
- **DXF File Import**: Load complex deposition patterns from CAD-generated DXF files
- **Coordinate Validation**: Automatic workspace bounds checking to prevent out-of-range movements
- **Path Optimization**: Smart filtering to remove duplicate points and unnecessary backtracks
- **Jump Detection**: Warning system for large movements that might indicate design errors  
- **Dual Speed Control**: Separate configurable speeds for printing (deposition) vs. travel movements
- **Path Visualization**: Real-time display of loaded patterns on the position canvas
- **Progress Monitoring**: Live progress tracking with time estimates and completion predictions
- **Pause/Resume**: Ability to pause and resume pattern execution
- **Nozzle Compensation**: Configurable nozzle diameter for precise deposition control
- **Stop-and-Go Mode**: Automated hop-dwell motion for ultra-slow deposition speeds
- **Recipe System**: Command-based execution supporting both print and travel movements

### 📸 Camera Integration
Real-time visual monitoring of the MBE chamber:
- **Live Video Feed**: Continuous camera stream for process observation
- **Exposure Control**: Adjustable exposure settings via slider interface
- **Gain Control**: Real-time gain adjustment for optimal image quality
- **Camera Service**: Background thread handling for non-blocking operation
- **Error Handling**: Automatic error reporting and recovery

### 🔧 Modbus Debugging & Logging
Advanced debugging tools for system development and troubleshooting:
- **Modbus Traffic Logging**: Capture all Modbus communications for debugging
- **Event Timestamping**: Precise timestamps on all controller events
- **Automatic Logging**: Option to auto-start logging when patterns begin
- **Pattern Metadata**: Logs include DXF filename, vertex count, and bounding box information
- **Multi-Axis Coordination**: Monitors communication across all three stepper motor controllers

### 🏗️ System Architecture
The application follows a modular design with clear separation of concerns:
- **Controllers**: Low-level hardware communication (SMCD14 stepper motor controllers)
- **Services**: Business logic for cameras, sensors, data logging, and DXF parsing
- **Widgets**: Reusable UI components for each control panel and tab
- **Windows**: Top-level application window coordinating all subsystems
- **Utils**: Shared utilities for DXF parsing, speed calculations, and coordinate transformations

## Hardware Requirements

This GUI interfaces with the following hardware components:

### Required
- **SMCD14 Stepper Motor Controllers** (x3): One for each manipulator axis (X, Y, Z)
  - Communication: Modbus TCP (default: `192.168.0.100:502`)
  - Slave IDs: X=1, Y=2, Z=3
  - See `SMCD14_manual [EN].pdf` for controller documentation

### Optional
- **Pfeiffer Vacuum Gauge**: For chamber pressure monitoring
  - Communication: RS-232 serial (default: `COM4` at 9600 baud)
  - Supports Pfeiffer vacuum protocol
- **Temperature Controller/Reader**: For multi-channel temperature monitoring
  - Communication: TCP/IP (default: `192.168.111.222`)
  - Supports up to 8 temperature channels
- **Camera** (e.g., Basler or similar): For live chamber monitoring
  - Must be compatible with the camera service implementation
- **E-Beam Flux Sensor**: For deposition rate monitoring
  - Serial communication for real-time flux readings

## Development setup

1. Create and activate a virtual environment:
   ```
   python -m venv .venv && source .venv/bin/activate
   ```
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Install development dependencies to run tests:
   ```
   pip install -r requirements-dev.txt
   ```
4. Run the application:
   ```
   python app.py
   ```

## Running tests

After installing the development dependencies, run the test suite with:

```
pytest
```

## Email Alert Configuration

The **Temperature/Pressure** tab can send automated low-pressure alerts via email to help prevent system failures. To enable this feature:

### Setup Instructions

1. **Create your credentials file:**
   ```bash
   cp email_credentials.py.template email_credentials.py
   ```

2. **Generate a Gmail App Password:**
   - Go to [Google Account App Passwords](https://myaccount.google.com/apppasswords)
   - Sign in to your Google account
   - Select "Mail" as the app and your device type
   - Click "Generate" and copy the 16-character password

3. **Edit `email_credentials.py`:**
   ```python
   ALERT_RECEIVER = "your-email@gmail.com"
   GMAIL_APP_PASSWORD = "your-16-char-app-password"
   ```

4. **Save the file** - it's already in `.gitignore` and won't be committed to version control

### Security Notes

- ✅ `email_credentials.py` is excluded from Git via `.gitignore`
- ✅ Never commit actual credentials to the repository
- ✅ Use Gmail App Passwords (not your regular Gmail password)
- ✅ The template file (`email_credentials.py.template`) is safe to share
- ⚠️ If you change computers, you'll need to set up the credentials file again

### How Alerts Work

Once configured, the system will automatically send email notifications when:
- Chamber pressure exceeds safe thresholds
- Pressure readings indicate potential vacuum failures
- System requires immediate attention

You can configure alert thresholds and monitoring intervals directly from the Temperature/Pressure tab in the GUI.

## Typical Workflow

Here's how to use the system for a typical deposition experiment:

### 1. **System Startup**
   - Launch the application: `python app.py`
   - Verify all three manipulator axes show "Connected" status in the status panel
   - Check the **Camera** tab to ensure live feed is working
   - Open the **Temp/Pressure** tab to monitor chamber conditions

### 2. **Pre-Deposition Setup**
   - **Temperature Monitoring**: Start logging temperature and pressure data
   - **E-Beam Configuration**: Set up source parameters and begin flux monitoring
   - **Email Alerts**: Ensure low-pressure alerts are configured (see Email Alert Configuration above)
   - **Position Manipulator**: Use the Main tab to manually position the substrate at the starting location

### 3. **Load Deposition Pattern**
   - Click **Load DXF** in the Main tab
   - Select your DXF file (generated from CAD software)
   - Specify the origin coordinates where the pattern should be placed
   - Review the **Coordinate Checker** dialog:
     - Verify vertex count and bounding box
     - Check for any large jumps (highlighted in orange)
     - Inspect velocity calculations
   - Set print speed (deposition) and travel speed when prompted
   - Accept or cancel based on the review

### 4. **Execute Pattern**
   - Click **Start Pattern** (enabled after successful DXF load)
   - Wait while the manipulator moves to the starting position
   - Confirm "Ready to begin printing?" dialog
   - Monitor progress:
     - Progress bar shows completion percentage
     - Time remaining updates in real-time
     - Position canvas displays current location
   - Use **Pause Pattern** if needed (resumes from the same point)

### 5. **During Deposition**
   - **Temperature/Pressure Tab**: Monitor chamber conditions continuously
   - **E-Beam Tab**: Track flux measurements and adjust if needed
   - **Camera Tab**: Observe the deposition process visually
   - **Modbus Panel**: View real-time communication logs (for debugging)

### 6. **Post-Deposition**
   - Pattern completion triggers automatic logging stop
   - Review logged data in `logs/` directory:
     - Temperature/pressure CSV files
     - Flux measurement CSV files
     - Modbus communication logs (if enabled)
   - Use **Temp/Pressure** tab to plot data for analysis

### 7. **Emergency Procedures**
   - **Individual Axis Stop**: Click axis-specific stop button
   - **Pattern Abort**: Close the confirmation dialog or use Emergency Stop
   - **Pressure Alert**: System automatically emails if chamber pressure exceeds threshold
   - All safety shutdowns are logged for post-incident analysis

## Command Line Options

```bash
# Enable detailed motion logging for debugging
python app.py --motion-log
```

## Project Structure

```
miniMBE-GUI/
├── app.py                      # Application entry point
├── controllers/                # Hardware communication layer
│   ├── manipulator_manager.py  # Coordinates all 3 axes
│   └── smcd14_controller.py    # SMCD14 stepper motor driver
├── services/                   # Business logic and hardware interfaces
│   ├── camera_service.py       # Camera capture and streaming
│   ├── sensor_readers.py       # Pressure and temperature sensors
│   ├── ebeam_controller.py     # E-beam source control
│   ├── data_logger.py          # CSV logging for temp/pressure
│   ├── flux_logger.py          # CSV logging for flux data
│   └── dxf_service.py          # DXF file parsing
├── widgets/                    # UI components
│   ├── temperature_pressure_tab.py
│   ├── ebeam_tab.py
│   ├── camera_tab.py
│   ├── axis_control.py         # Individual axis control widget
│   ├── position_canvas.py      # 2D visualization canvas
│   └── modbus_panel.py         # Debugging panel
├── windows/
│   └── main_window.py          # Main application window
├── utils/                      # Shared utilities
│   └── dxf_parser.py           # DXF to recipe conversion
└── tests/                      # Unit and integration tests
```

## Contributing

This is a research project developed for the Yang Research Group at the University of Chicago. If you're using or modifying this code for your own MBE system:

1. Fork the repository
2. Create a feature branch
3. Run the test suite: `pytest`
4. Submit a pull request with a clear description of changes

## License

*[Add license information here]*

## Acknowledgments

Developed at the University of Chicago for the Yang Research Group's Mini-MBE system.

