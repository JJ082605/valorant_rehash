"""File logging with secret redaction (the lockfile password never hits disk)."""

from __future__ import annotations

import logging
from pathlib import Path

_secrets: set[str] = set()


def register_secret(secret: str) -> None:
    if secret:
        _secrets.add(secret)


def redact(text: str) -> str:
    for s in _secrets:
        text = text.replace(s, "***")
    return text


class _RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))


def setup_logging(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(_RedactingFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
