# miniMBE GUI

A minimal graphical interface for controlling a manipulator and visualising DXF paths.

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

## Alert email configuration

The Temperature/Pressure tab can send low-pressure alerts when an SMTP
configuration is available. Provide the email addresses from the UI (Settings →
"Alert sender" / "Alert recipient") or by setting the following environment
variables before launching the application:

* `MINIMBE_ALERT_SENDER`
* `MINIMBE_ALERT_RECIPIENT`
* `MINIMBE_ALERT_PASSWORD`

Alternatively, store the details in an INI file referenced by
`MINIMBE_ALERT_CONFIG`:

```ini
[alerts]
sender = alerts@example.com
recipient = operator@example.com
password = app-password-from-provider
```

For security, the SMTP/app password is never written to disk by the
application. Distribute the secret out of band (for example, by storing it in a
password manager or provisioning it via deployment tooling) and inject it
through the environment variable or the secure config file before starting the
GUI.
