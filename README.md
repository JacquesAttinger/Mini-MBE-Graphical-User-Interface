<!-- Last edited: 2026-10-03 13:45 CDT -->
<a id="readme-top"></a>

[![Forks][forks-shield]][forks-url]
[![Stargazers][stars-shield]][stars-url]
[![Issues][issues-shield]][issues-url]
[![License][license-shield]][license-url]

<br />
<div align="center">
  <h3 align="center">miniMBE GUI</h3>

  <p align="center">
    A desktop app to run a Mini-MBE (molecular beam epitaxy) system from one window.
    <br />
    Move the sample stage, draw patterns from DXF files, and watch pressure, temperature, flux and camera feeds.
    <br />
    <br />
    <a href="https://github.com/JacquesAttinger/Mini-MBE-Graphical-User-Interface/issues/new">Report a Bug or Request a Feature</a>
  </p>
</div>

<details>
  <summary>Table of Contents</summary>
  <ol>
    <li>
      <a href="#about-the-project">About The Project</a>
      <ul>
        <li><a href="#built-with">Built With</a></li>
      </ul>
    </li>
    <li>
      <a href="#getting-started">Getting Started</a>
      <ul>
        <li><a href="#prerequisites">Prerequisites</a></li>
        <li><a href="#installation">Installation</a></li>
        <li><a href="#email-alerts">Email alerts</a></li>
      </ul>
    </li>
    <li><a href="#usage">Usage</a></li>
    <li><a href="#project-structure">Project Structure</a></li>
    <li><a href="#contributing">Contributing</a></li>
    <li><a href="#license">License</a></li>
    <li><a href="#acknowledgments">Acknowledgments</a></li>
  </ol>
</details>

## About The Project

![miniMBE GUI, Main tab][screenshot-main]

The miniMBE GUI controls the Mini-MBE system of the Yang Research Group at the University of Chicago.
It replaces the vendor's LabVIEW interface with one Python app.
The app also adds logging, alerts and pattern drawing that the vendor tool does not have.
The screenshots show the app with no hardware connected.

Main features:

* **Manipulator control.**
  Move the X, Y and Z axes, home them, stop them, and see the position on a live 2D canvas.
  The axes use three [SMCD14](SMCD14_manual%20[EN].pdf) stepper controllers over Modbus TCP.
* **DXF pattern execution.**
  Load a CAD drawing, check it in a coordinate checker (bounds, large jumps, speeds), then run it.
  You can set separate print and travel speeds, pause and resume, and see progress and time left.
  A stop-and-go mode supports very slow deposition speeds.
* **Temperature and pressure.**
  Read up to 8 temperature channels and 2 pressure gauges, log them to CSV, and plot them.
  The app can send an email when the pressure goes above a limit.
* **E-beam source.**
  Set high voltage, emission current and filament current.
  Watch the flux and log it to CSV.
* **Camera.**
  Live video of the chamber with exposure and gain sliders.
* **Modbus log.**
  Record every Modbus message with timestamps to help debug the hardware.

![miniMBE GUI, E-Beam tab][screenshot-ebeam]

<p align="right">(<a href="#readme-top">back to top</a>)</p>

### Built With

* [![Python][Python-badge]][Python-url]
* [![Qt][Qt-badge]][Qt-url]
* [![NumPy][NumPy-badge]][NumPy-url]
* [![Matplotlib][Matplotlib-badge]][Matplotlib-url]
* [ezdxf](https://github.com/mozman/ezdxf) for DXF files
* [Shapely](https://github.com/shapely/shapely) for geometry
* [pymodbus](https://github.com/pymodbus-dev/pymodbus) for the motor controllers
* [pyserial](https://github.com/pyserial/pyserial) for the vacuum gauge and e-beam supply
* [VmbPy](https://github.com/alliedvision/VmbPy) for Allied Vision cameras

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Getting Started

### Prerequisites

* Python 3.11 (the repo pins 3.11.3 in `.python-version`).
* The hardware you want to use.
  The app starts without hardware, but the related panels show "Disconnected".

| Device | How it connects | Default setting |
| --- | --- | --- |
| 3 × SMCD14 stepper controllers (X, Y, Z) | Modbus TCP | host `169.254.151.255`, port 502, slave IDs 1, 2, 3 (`controllers/manipulator_manager.py`) |
| Temperature reader | TCP/IP | `192.168.111.222` (`services/temperature_controller.py`) |
| Pfeiffer vacuum gauge | Serial (RS-232) | `COM4`, 9600 baud |
| E-beam power supply and flux sensor | Serial | `COM5` (`services/ebeam_controller.py`) |
| Allied Vision camera | VmbPy | needs the [Vimba X SDK](https://www.alliedvision.com/en/products/software/vimba-x-sdk/) |

Change the defaults in the files named above to match your setup.

### Installation

1. Clone the repo.
   ```sh
   git clone https://github.com/JacquesAttinger/Mini-MBE-Graphical-User-Interface.git
   cd Mini-MBE-Graphical-User-Interface
   ```
2. Create a virtual environment and install the packages.
   ```sh
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   ```
3. Create the email credentials file (see [Email alerts](#email-alerts)).
   The temperature tab imports it, so the app needs this file to start.
   ```sh
   cp email_credentials.py.template email_credentials.py
   ```
4. Start the app.
   ```sh
   python app.py
   ```

To run the tests, install the development packages and run `pytest`:

```sh
pip install -r requirements-dev.txt
pytest
```

### Email alerts

The Temp/Pressure tab can email you when the pressure goes above a limit.
It sends mail through Gmail with an app password.

1. Create an app password at [Google App Passwords](https://myaccount.google.com/apppasswords).
2. Fill in `email_credentials.py`:
   ```python
   ALERT_SENDER = "your-sender@gmail.com"
   ALERT_RECEIVER = "your-email@gmail.com"
   GMAIL_APP_PASSWORD = "your-16-char-app-password"
   ```
3. Never commit this file.
   It is in `.gitignore`.

If you do not want alerts, leave the placeholder values.
The app still runs, and the email step fails quietly.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Usage

A typical run looks like this:

1. **Start up.**
   Run `python app.py`.
   Check that the three axes show as connected on the Main tab.
   Open the Camera and Temp/Pressure tabs to check the chamber.
2. **Prepare.**
   Start the temperature and pressure log.
   Set the e-beam source and start the flux log.
   Move the sample to the start position on the Main tab.
3. **Load a pattern.**
   Click **Load DXF** and pick a file.
   Enter the origin where the pattern goes.
   Read the coordinate checker: vertex count, bounding box, and large jumps (shown in orange).
   Set the print speed and the travel speed, then accept.
4. **Run it.**
   Click **Start Pattern** and confirm the prompt.
   Watch the progress, time left and position.
   Click **Pause Pattern** to stop and later resume from the same point.
5. **Finish.**
   The app stops logging when the pattern ends.
   Find the logs in `logs/`: temperature and pressure CSV files, flux CSV files, and Modbus logs if you enabled them.
6. **Emergency.**
   Use the **Stop** button on an axis to stop it.
   Close the confirm dialog to abort before a pattern starts.

To log every motion command for debugging, start the app with:

```sh
python app.py --motion-log
```

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Project Structure

```
├── app.py                  # Entry point
├── controllers/            # Hardware control (SMCD14 motors, multi-axis manager)
├── services/               # Camera, sensors, e-beam, data loggers, DXF loading
├── widgets/                # UI panels for each tab
├── windows/                # Main window
├── utils/                  # DXF parsing, speed and Modbus helpers
├── SMCD14_LV2020/          # Vendor LabVIEW project for the SMCD14 (reference)
└── tests/                  # Tests and hardware test scripts
```

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Contributing

Bug reports and ideas are welcome.
Please [open an issue](https://github.com/JacquesAttinger/Mini-MBE-Graphical-User-Interface/issues/new) and describe what you saw or what you need.
This project does not take pull requests at this time.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## License

Distributed under the MIT License.
See [`LICENSE`](LICENSE) for details.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Acknowledgments

* The Yang Research Group at the University of Chicago, for the Mini-MBE system this app controls.
* The SMCD14 LabVIEW project and manual from the controller vendor.
* [Best-README-Template](https://github.com/othneildrew/Best-README-Template)

<p align="right">(<a href="#readme-top">back to top</a>)</p>

[forks-shield]: https://img.shields.io/github/forks/JacquesAttinger/Mini-MBE-Graphical-User-Interface.svg?style=for-the-badge
[forks-url]: https://github.com/JacquesAttinger/Mini-MBE-Graphical-User-Interface/network/members
[stars-shield]: https://img.shields.io/github/stars/JacquesAttinger/Mini-MBE-Graphical-User-Interface.svg?style=for-the-badge
[stars-url]: https://github.com/JacquesAttinger/Mini-MBE-Graphical-User-Interface/stargazers
[issues-shield]: https://img.shields.io/github/issues/JacquesAttinger/Mini-MBE-Graphical-User-Interface.svg?style=for-the-badge
[issues-url]: https://github.com/JacquesAttinger/Mini-MBE-Graphical-User-Interface/issues
[license-shield]: https://img.shields.io/github/license/JacquesAttinger/Mini-MBE-Graphical-User-Interface.svg?style=for-the-badge
[license-url]: https://github.com/JacquesAttinger/Mini-MBE-Graphical-User-Interface/blob/main/LICENSE
[screenshot-main]: images/screenshot-main.png
[screenshot-ebeam]: images/screenshot-ebeam.png
[Python-badge]: https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white
[Python-url]: https://www.python.org/
[Qt-badge]: https://img.shields.io/badge/Qt%20for%20Python-41CD52?style=for-the-badge&logo=qt&logoColor=white
[Qt-url]: https://doc.qt.io/qtforpython-6/
[NumPy-badge]: https://img.shields.io/badge/NumPy-013243?style=for-the-badge&logo=numpy&logoColor=white
[NumPy-url]: https://numpy.org/
[Matplotlib-badge]: https://img.shields.io/badge/Matplotlib-11557c?style=for-the-badge
[Matplotlib-url]: https://matplotlib.org/
