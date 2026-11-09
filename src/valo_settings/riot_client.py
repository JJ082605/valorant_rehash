"""Reads the Riot Client lockfile and the signed-in account's identity.

The lockfile is written by the running Riot Client and holds a local port and a
random per-session password. That password only works against 127.0.0.1 — it is
NOT your Riot account password. It is kept in memory only.
"""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

import requests

from .errors import ClientNotReady, ClientNotRunning, ClientUnreachable, raise_for_status
from .logging_setup import register_secret

# --- Unofficial endpoints (verify with scripts/probe.py) -----------------------
IDENTITY_PATH = "/chat/v1/session"
FIELD_PUUID = "puuid"
FIELD_GAME_NAME = "game_name"
FIELD_GAME_TAG = "game_tag"
TIMEOUT = 5
NO_PROXY = {"http": None, "https": None}
# ------------------------------------------------------------------------------

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Lockfile:
    name: str
    pid: int
    port: int
    password: str = field(repr=False)
    protocol: str

    @property
    def base_url(self) -> str:
        return f"{self.protocol}://127.0.0.1:{self.port}"

    @property
    def auth(self) -> tuple[str, str]:
        return ("riot", self.password)


@dataclass(frozen=True)
class Session:
    lockfile: Lockfile
    puuid: str
    riot_id: str


def default_lockfile_path() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    else:
        # macOS: unverified, see spec "Step 0".
        base = Path.home() / "Library/Application Support"
    return base / "Riot Games" / "Riot Client" / "Config" / "lockfile"


def read_lockfile(path: Path | None = None) -> Lockfile:
    path = path or default_lockfile_path()
    try:
        text = path.read_text(encoding="utf-8-sig").strip()
    except FileNotFoundError:
        raise ClientNotRunning() from None
    except OSError:
        raise ClientNotReady() from None
    parts = text.split(":")
    if len(parts) != 5:
        raise ClientNotReady()
    name, pid, port, password, protocol = parts
    try:
        lf = Lockfile(name=name, pid=int(pid), port=int(port), password=password, protocol=protocol)
    except ValueError:
        raise ClientNotReady() from None
    register_secret(password)
    return lf


def local_request(http, method: str, lockfile: Lockfile, path: str, **kwargs):
    """Send one request to the local Riot Client and map failures to ValoErrors."""
    try:
        resp = http.request(
            method,
            lockfile.base_url + path,
            auth=lockfile.auth,
            verify=False,  # self-signed cert, 127.0.0.1 only
            timeout=TIMEOUT,
            proxies=NO_PROXY,  # never send the lockfile password through a system proxy
            **kwargs,
        )
    except requests.RequestException as e:
        log.info("%s %s -> %s", method, path, type(e).__name__)
        raise ClientUnreachable() from None
    log.info("%s %s -> %s", method, path, resp.status_code)
    raise_for_status(resp)
    return resp


def get_session(http, path: Path | None = None) -> Session:
    lf = read_lockfile(path)
    resp = local_request(http, "GET", lf, IDENTITY_PATH)
    try:
        body = resp.json()
        puuid = body[FIELD_PUUID]
        name = body.get(FIELD_GAME_NAME) or ""
        tag = body.get(FIELD_GAME_TAG) or ""
    except (ValueError, KeyError, TypeError, AttributeError):
        raise ClientNotReady() from None
    if not puuid:
        raise ClientNotReady()
    riot_id = f"{name}#{tag}" if name else puuid[:8]
    return Session(lockfile=lf, puuid=puuid, riot_id=riot_id)
