"""Named profiles and per-account backups, stored as JSON files."""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .errors import BackupFailed, ProfileError

MAX_BACKUPS = 10
MAX_NAME_LEN = 64
# \w is Unicode-aware, so Riot IDs like "Ñandú#ES1" work; path characters (/ \ : * ? " < > |) don't match.
_NAME_RE = re.compile(r"^[\w \-#][\w \-#.]*$")
_WINDOWS_RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}


@dataclass
class Profile:
    name: str
    source_riot_id: str
    source_puuid: str
    captured_at: str
    settings: dict


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_name(name: str) -> str:
    name = name.strip()
    if (
        not name
        or len(name) > MAX_NAME_LEN
        or not _NAME_RE.match(name)
        or name.split(".")[0].lower() in _WINDOWS_RESERVED
        or name.endswith(".")
    ):
        raise ProfileError(
            "Profile names can use letters, numbers, spaces, - _ # and . (max 64 characters)."
        )
    return name


def _write_json_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _read_profile(path: Path) -> Profile:
    data = json.loads(path.read_text(encoding="utf-8"))
    p = Profile(**data)
    if not isinstance(p.settings, dict) or not p.settings:
        raise ValueError("empty settings")
    return p


class ProfileStore:
    def __init__(self, base: Path):
        self.base = Path(base)
        self.profiles_dir = self.base / "profiles"
        self.backups_dir = self.base / "backups"

    def _profile_path(self, name: str) -> Path:
        return self.profiles_dir / f"{validate_name(name)}.json"

    def exists(self, name: str) -> bool:
        return self._profile_path(name).exists()

    def save(self, profile: Profile, overwrite: bool = False) -> None:
        path = self._profile_path(profile.name)
        if path.exists() and not overwrite:
            raise ProfileError(f"A profile named '{profile.name}' already exists.")
        _write_json_atomic(path, asdict(profile))

    def load(self, name: str) -> Profile:
        path = self._profile_path(name)
        try:
            return _read_profile(path)
        except FileNotFoundError:
            raise ProfileError(f"Profile '{name}' not found.") from None
        except (ValueError, TypeError):
            raise ProfileError(f"Profile '{name}' is corrupt and can't be used.") from None

    def delete(self, name: str) -> None:
        self._profile_path(name).unlink(missing_ok=True)

    def list(self) -> tuple[list[Profile], list[str]]:
        good: list[Profile] = []
        bad: list[str] = []
        if not self.profiles_dir.is_dir():
            return good, bad
        for path in sorted(self.profiles_dir.glob("*.json")):
            try:
                good.append(_read_profile(path))
            except (OSError, ValueError, TypeError):
                bad.append(path.stem)
        good.sort(key=lambda p: p.name.lower())
        return good, bad

    def write_backup(self, puuid: str, riot_id: str, settings: dict) -> Path:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        folder = self.backups_dir / puuid
        path = folder / f"{stamp}.json"
        profile = Profile(
            name=f"backup {stamp}",
            source_riot_id=riot_id,
            source_puuid=puuid,
            captured_at=now_iso(),
            settings=settings,
        )
        try:
            _write_json_atomic(path, asdict(profile))
            for old in sorted(folder.glob("*.json"))[:-MAX_BACKUPS]:
                old.unlink(missing_ok=True)
        except OSError:
            raise BackupFailed() from None
        return path

    def latest_backup(self, puuid: str) -> Profile | None:
        folder = self.backups_dir / puuid
        for path in sorted(folder.glob("*.json"), reverse=True):
            try:
                return _read_profile(path)
            except (OSError, ValueError, TypeError):
                continue
        return None
