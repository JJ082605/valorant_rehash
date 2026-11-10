import pytest
import requests

from conftest import TOKENS, FakeHttp, resp, server_settings
from valo_settings.errors import AuthExpired, ClientNotReady, InvalidSettings, SettingsServerError
from valo_settings.logging_setup import redact
from valo_settings.preferences import (
    GET_PATH,
    PREFS_HOST,
    SAVE_PATH,
    TOKEN_PATH,
    decode_settings,
    encode_settings,
    fetch_settings,
    save_settings,
)
from valo_settings.riot_client import Session, read_lockfile


@pytest.fixture
def session(lockfile_path):
    return Session(lockfile=read_lockfile(lockfile_path), puuid="p-1", riot_id="Pigeon#NA1")


def test_codec_round_trip(settings):
    assert decode_settings(encode_settings(settings)) == settings


def test_fetch_uses_local_tokens_then_server(session, settings):
    http = FakeHttp(resp(200, TOKENS), server_settings(settings))
    assert fetch_settings(http, session) == settings
    assert http.methods == [("GET", TOKEN_PATH), ("GET", GET_PATH)]
    _, url, kwargs = http.calls[1]
    assert url == PREFS_HOST + GET_PATH
    assert kwargs["headers"]["Authorization"] == "Bearer access-tok"
    assert kwargs["headers"]["X-Riot-Entitlements-JWT"] == "entitlement-tok"
    assert "auth" not in kwargs  # the lockfile password never leaves 127.0.0.1


def test_fetch_rejects_empty_or_unreadable(session):
    for bad in (server_settings({}), resp(200, {"data": "not base64!"}), resp(200, {}), resp(200, is_json=False)):
        with pytest.raises(InvalidSettings):
            fetch_settings(FakeHttp(resp(200, TOKENS), bad), session)


def test_save_puts_compressed_blob(session, settings):
    http = FakeHttp(resp(200, TOKENS), resp(200))
    save_settings(http, session, settings)
    method, url, kwargs = http.calls[1]
    assert method == "PUT" and url == PREFS_HOST + SAVE_PATH
    assert kwargs["json"]["type"] == "Ares.PlayerSettings"
    assert decode_settings(kwargs["json"]["data"]) == settings


def test_401_raises_auth_expired(session, settings):
    with pytest.raises(AuthExpired):
        save_settings(FakeHttp(resp(200, TOKENS), resp(401)), session, settings)


def test_server_errors(session):
    with pytest.raises(SettingsServerError):
        fetch_settings(FakeHttp(resp(200, TOKENS), resp(500)), session)
    with pytest.raises(SettingsServerError):
        fetch_settings(FakeHttp(resp(200, TOKENS), requests.ConnectionError()), session)


def test_missing_tokens_means_not_ready(session):
    with pytest.raises(ClientNotReady):
        fetch_settings(FakeHttp(resp(200, {"accessToken": "a"})), session)


def test_tokens_are_redacted_from_logs(session, settings):
    fetch_settings(FakeHttp(resp(200, TOKENS), server_settings(settings)), session)
    assert redact("Bearer access-tok entitlement-tok") == "Bearer *** ***"
