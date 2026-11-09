"""The only module that reads or writes VALORANT settings."""

from __future__ import annotations

from .errors import InvalidSettings
from .riot_client import Session, local_request

# --- Unofficial endpoint (source: ValorantCC Processor.cs) ---------------------
SETTINGS_PATH = "/player-preferences/v1/data-json/Ares.PlayerSettings"
# ------------------------------------------------------------------------------


def fetch_settings(http, session: Session) -> dict:
    resp = local_request(http, "GET", session.lockfile, SETTINGS_PATH)
    try:
        body = resp.json()
    except ValueError:
        raise InvalidSettings() from None
    if not isinstance(body, dict) or not body:
        raise InvalidSettings()
    return body


def save_settings(http, session: Session, settings: dict) -> None:
    if not isinstance(settings, dict) or not settings:
        raise InvalidSettings()
    local_request(http, "PUT", session.lockfile, SETTINGS_PATH, json=settings)
