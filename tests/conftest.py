import json
from pathlib import Path

import pytest

from valo_settings.profiles import ProfileStore

FIXTURES = Path(__file__).parent / "fixtures"


class FakeResponse:
    def __init__(self, status_code=200, body=None, is_json=True):
        self.status_code = status_code
        self._body = body
        self._is_json = is_json

    def json(self):
        if not self._is_json:
            raise ValueError("not JSON")
        return self._body


def resp(status_code=200, body=None, is_json=True):
    return FakeResponse(status_code, body, is_json)


class FakeHttp:
    """Returns scripted responses in order and records every call.

    A scripted item that is an Exception instance is raised instead of returned.
    """

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if not self.responses:
            raise AssertionError(f"unexpected request: {method} {url}")
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    @property
    def methods(self):
        return [(m, url.split("127.0.0.1:55555", 1)[-1]) for m, url, _ in self.calls]


@pytest.fixture
def lockfile_path(tmp_path):
    p = tmp_path / "lockfile"
    p.write_text("Riot Client:1234:55555:secret:https", encoding="utf-8")
    return p


@pytest.fixture
def identity():
    return {"puuid": "p-1", "game_name": "Pigeon", "game_tag": "NA1"}


@pytest.fixture
def settings():
    return json.loads((FIXTURES / "player_settings.json").read_text(encoding="utf-8"))


@pytest.fixture
def store(tmp_path):
    return ProfileStore(tmp_path / "data")


