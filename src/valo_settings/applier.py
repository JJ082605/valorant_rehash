"""Capture / apply / restore. All flow logic lives here so it can be tested without a UI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import preferences
from .errors import AuthExpired, ProfileError
from .profiles import Profile, ProfileStore, now_iso, validate_name
from .riot_client import Session, get_session

# Keys the server may change on save; ignored when verifying. Fill in from Step 0.
VOLATILE_KEYS: frozenset[str] = frozenset()

VALORANT_PROCESS = "VALORANT-Win64-Shipping.exe"


def default_is_valorant_running() -> bool:
    import psutil

    for proc in psutil.process_iter(["name"]):
        if (proc.info.get("name") or "").lower() == VALORANT_PROCESS.lower():
            return True
    return False


def _comparable(settings: dict) -> dict:
    return {k: v for k, v in settings.items() if k not in VOLATILE_KEYS}


@dataclass
class ApplyResult:
    verified: bool
    backup_path: Path
    target_riot_id: str


class Applier:
    def __init__(
        self,
        http,
        store: ProfileStore,
        lockfile_path: Path | None = None,
        is_valorant_running: Callable[[], bool] = default_is_valorant_running,
    ):
        self.http = http
        self.store = store
        self.lockfile_path = lockfile_path
        self._is_valorant_running = is_valorant_running

    def current_session(self) -> Session:
        return get_session(self.http, self.lockfile_path)

    def valorant_running(self) -> bool:
        return self._is_valorant_running()

    def _call(self, fn: Callable[[Session], object], expected_puuid: str | None = None):
        """Run ONE operation with a fresh session, re-checking the account first.

        On AuthExpired (anywhere, including the identity request) re-read the
        lockfile and retry this single call once. Retries never repeat earlier
        steps, so a backup is written exactly once per apply.
        """
        for attempt in (1, 2):
            try:
                session = self.current_session()
                if expected_puuid is not None and session.puuid != expected_puuid:
                    raise ProfileError("The signed-in account changed. Refresh and try again.")
                return fn(session)
            except AuthExpired:
                if attempt == 2:
                    raise

    def capture(self, name: str, overwrite: bool = False) -> Profile:
        name = validate_name(name)
        if self.store.exists(name) and not overwrite:
            raise ProfileError(f"A profile named '{name}' already exists.")

        def run(session: Session) -> Profile:
            settings = preferences.fetch_settings(self.http, session)
            profile = Profile(
                name=name,
                source_riot_id=session.riot_id,
                source_puuid=session.puuid,
                captured_at=now_iso(),
                settings=settings,
            )
            self.store.save(profile, overwrite=overwrite)
            return profile

        return self._call(run)

    def _apply_settings(self, settings: dict, expected_puuid: str) -> ApplyResult:
        fetch = lambda s: (s, preferences.fetch_settings(self.http, s))  # noqa: E731
        session, current = self._call(fetch, expected_puuid)
        backup_path = self.store.write_backup(session.puuid, session.riot_id, current)
        self._call(lambda s: preferences.save_settings(self.http, s, settings), expected_puuid)
        session, after = self._call(fetch, expected_puuid)
        return ApplyResult(
            verified=_comparable(after) == _comparable(settings),
            backup_path=backup_path,
            target_riot_id=session.riot_id,
        )

    def apply(self, profile_name: str, expected_puuid: str) -> ApplyResult:
        profile = self.store.load(profile_name)
        return self._apply_settings(profile.settings, expected_puuid)

    def restore_latest(self, expected_puuid: str) -> ApplyResult:
        backup = self.store.latest_backup(expected_puuid)
        if backup is None:
            raise ProfileError("No backup for this account yet.")
        return self._apply_settings(backup.settings, expected_puuid)
