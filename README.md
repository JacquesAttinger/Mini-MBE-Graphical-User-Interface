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

### 🎯 Additional Features
- **DXF Path Visualization**: Load and visualize deposition patterns from DXF files
- **Manipulator Control**: Precise positioning control for substrate manipulation
- **Extensible Architecture**: Modular design for easy integration of additional sensors and controls

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
