"""Helpers for configuring low-pressure alert emails."""

from __future__ import annotations

import configparser
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

ALERT_SECTION = "alerts"
ENV_SENDER = "MINIMBE_ALERT_SENDER"
ENV_RECIPIENT = "MINIMBE_ALERT_RECIPIENT"
ENV_PASSWORD = "MINIMBE_ALERT_PASSWORD"
ENV_CONFIG_FILE = "MINIMBE_ALERT_CONFIG"


@dataclass
class AlertConfig:
    """Email alert configuration loaded from environment or disk."""

    sender: str = ""
    recipient: str = ""
    password: str = ""

    def is_complete(self) -> bool:
        """Return ``True`` when all required fields are present."""

        return all(value for value in (self.sender, self.recipient, self.password))

    def copy(self) -> "AlertConfig":
        """Return a shallow copy of the configuration."""

        return AlertConfig(self.sender, self.recipient, self.password)


def load_alert_config(config_path: Optional[str | Path] = None) -> Optional[AlertConfig]:
    """Load the alert configuration from environment variables or a config file.

    Environment variables take precedence over the config file. The recognised
    variables are :data:`ENV_SENDER`, :data:`ENV_RECIPIENT`, and
    :data:`ENV_PASSWORD`. A config file path can be supplied either via the
    ``config_path`` argument or the :data:`ENV_CONFIG_FILE` environment
    variable. The config file must contain an ``[alerts]`` section with
    ``sender``, ``recipient``, and ``password`` fields.

    The function returns ``None`` when no configuration details are available at
    all. Otherwise an :class:`AlertConfig` instance is returned. Call
    :meth:`AlertConfig.is_complete` to determine whether the configuration is
    usable for sending alerts.
    """

    sender = _clean(os.getenv(ENV_SENDER))
    recipient = _clean(os.getenv(ENV_RECIPIENT))
    password = _clean(os.getenv(ENV_PASSWORD))

    cfg_file = config_path or os.getenv(ENV_CONFIG_FILE)
    if cfg_file:
        file_values = _read_config_file(Path(cfg_file))
        sender = sender or file_values.get("sender", "")
        recipient = recipient or file_values.get("recipient", "")
        password = password or file_values.get("password", "")

    if not any((sender, recipient, password)):
        return None

    return AlertConfig(sender=sender, recipient=recipient, password=password)


def _read_config_file(path: Path) -> dict[str, str]:
    """Return alert settings from ``path`` if the file exists."""

    parser = configparser.ConfigParser()
    try:
        with path.expanduser().resolve(strict=False).open("r", encoding="utf-8") as fh:
            parser.read_file(fh)
    except FileNotFoundError:
        return {}

    if ALERT_SECTION not in parser:
        return {}

    section = parser[ALERT_SECTION]
    return {
        "sender": _clean(section.get("sender")),
        "recipient": _clean(section.get("recipient")),
        "password": _clean(section.get("password")),
    }


def _clean(value: Optional[str]) -> str:
    """Return ``value`` stripped of whitespace or ``""`` if ``None``."""

    if value is None:
        return ""
    return value.strip()


__all__ = [
    "AlertConfig",
    "load_alert_config",
    "ALERT_SECTION",
    "ENV_CONFIG_FILE",
    "ENV_PASSWORD",
    "ENV_RECIPIENT",
    "ENV_SENDER",
]
