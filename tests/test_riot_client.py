import pytest
import requests

from conftest import FakeHttp, resp
from valo_settings.errors import ClientNotReady, ClientNotRunning, ClientUnreachable
from valo_settings.riot_client import IDENTITY_PATH, get_session, read_lockfile


def test_parses_lockfile(lockfile_path):
    lf = read_lockfile(lockfile_path)
    assert (lf.name, lf.pid, lf.port, lf.password, lf.protocol) == ("Riot Client", 1234, 55555, "secret", "https")
    assert lf.base_url == "https://127.0.0.1:55555"
    assert "secret" not in repr(lf)


def test_parses_bom_and_newline(tmp_path):
    p = tmp_path / "lockfile"
    p.write_bytes("﻿Riot Client:1:2:pw:https\r\n".encode("utf-8"))
    lf = read_lockfile(p)
    assert lf.port == 2 and lf.protocol == "https"


def test_missing_and_malformed_lockfile(tmp_path):
    with pytest.raises(ClientNotRunning):
        read_lockfile(tmp_path / "nope")
    bad = tmp_path / "bad"
    bad.write_text("Riot Client:abc:2:pw", encoding="utf-8")
    with pytest.raises(ClientNotReady):
        read_lockfile(bad)


def test_get_session(lockfile_path, identity):
    http = FakeHttp(resp(200, identity))
    s = get_session(http, lockfile_path)
    assert s.riot_id == "Pigeon#NA1" and s.puuid == "p-1"
    method, url, kwargs = http.calls[0]
    assert method == "GET" and url == "https://127.0.0.1:55555" + IDENTITY_PATH
    assert kwargs["auth"] == ("riot", "secret") and kwargs["verify"] is False


def test_connection_refused_raises_unreachable(lockfile_path):
    http = FakeHttp(requests.ConnectionError("refused"))
    with pytest.raises(ClientUnreachable):
        get_session(http, lockfile_path)


def test_local_request_bypasses_proxy(lockfile_path, identity):
    http = FakeHttp(resp(200, identity))
    get_session(http, lockfile_path)
    assert http.calls[0][2]["proxies"] == {"http": None, "https": None}
