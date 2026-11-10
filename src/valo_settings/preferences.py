"""The only module that reads or writes VALORANT settings."""

from __future__ import annotations

import base64
import json
import logging
import zlib

import requests

from .errors import AuthExpired, ClientNotReady, InvalidSettings, SettingsServerError
from .logging_setup import register_secret
from .riot_client import Session, local_request

# --- Unofficial endpoints (source: ValorantCC Processor.cs) ---------------------
# The local /player-preferences/v1/data-json endpoint only answers the running
# game ("Unable to find caller ID for session"), so settings go through Riot's
# preferences server, signed in with tokens from the local Riot Client.
# ValorantCC uses the euc1 host for every region.
TOKEN_PATH = "/entitlements/v1/token"
PREFS_HOST = "https://player-preferences-euc1.pp.sgp.pvp.net"
GET_PATH = "/playerPref/v3/getPreference/Ares.PlayerSettings"
SAVE_PATH = "/playerPref/v3/savePreference"
SETTINGS_TYPE = "Ares.PlayerSettings"
# base64 of {"platformType": "PC", "platformOS": "Windows", ...}, as sent by ValorantCC.
CLIENT_PLATFORM = (
    "ew0KCSJwbGF0Zm9ybVR5cGUiOiAiUEMiLA0KCSJwbGF0Zm9ybU9TIjogIldpbmRvd3MiLA0KCSJwbGF0Zm9ybU9TVmVyc2lv"
    "biI6ICIxMC4wLjE5MDQyLjEuMjU2LjY0Yml0IiwNCgkicGxhdGZvcm1DaGlwc2V0IjogIlVua25vd24iDQp9"
)
TIMEOUT = 10
# ------------------------------------------------------------------------------

log = logging.getLogger(__name__)


def decode_settings(blob: str) -> dict:
    """Server format: base64 of raw-deflated JSON."""
    return json.loads(zlib.decompress(base64.b64decode(blob), -zlib.MAX_WBITS))


def encode_settings(settings: dict) -> str:
    c = zlib.compressobj(wbits=-zlib.MAX_WBITS)
    raw = json.dumps(settings, separators=(",", ":")).encode("utf-8")
    return base64.b64encode(c.compress(raw) + c.flush()).decode("ascii")


def _auth_headers(http, session: Session) -> dict:
    """Short-lived sign-in tokens from the local Riot Client (not your password)."""
    resp = local_request(http, "GET", session.lockfile, TOKEN_PATH)
    try:
        body = resp.json()
        access, entitlements = body["accessToken"], body["token"]
    except (ValueError, KeyError, TypeError):
        raise ClientNotReady() from None
    if not (access and entitlements):
        raise ClientNotReady()
    register_secret(access)
    register_secret(entitlements)
    return {
        "Authorization": f"Bearer {access}",
        "X-Riot-Entitlements-JWT": entitlements,
        "X-Riot-ClientPlatform": CLIENT_PLATFORM,
    }


def _server_request(http, method: str, headers: dict, path: str, **kwargs):
    try:
        resp = http.request(method, PREFS_HOST + path, headers=headers, timeout=TIMEOUT, **kwargs)
    except requests.RequestException as e:
        log.info("%s %s -> %s", method, path, type(e).__name__)
        raise SettingsServerError(
            "Couldn't reach Riot's settings server. Check your internet connection."
        ) from None
    log.info("%s %s -> %s", method, path, resp.status_code)
    if resp.status_code in (401, 403):
        raise AuthExpired()
    if not 200 <= resp.status_code < 300:
        raise SettingsServerError()
    return resp


def fetch_settings(http, session: Session) -> dict:
    resp = _server_request(http, "GET", _auth_headers(http, session), GET_PATH)
    try:
        settings = decode_settings(resp.json()["data"])
    except (ValueError, KeyError, TypeError, zlib.error):
        raise InvalidSettings() from None
    if not isinstance(settings, dict) or not settings:
        raise InvalidSettings()
    return settings


def save_settings(http, session: Session, settings: dict) -> None:
    if not isinstance(settings, dict) or not settings:
        raise InvalidSettings()
    body = {"type": SETTINGS_TYPE, "data": encode_settings(settings)}
    _server_request(http, "PUT", _auth_headers(http, session), SAVE_PATH, json=body)
