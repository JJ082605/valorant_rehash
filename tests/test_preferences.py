import pytest

from conftest import FakeHttp, resp
from valo_settings.errors import AuthExpired, InvalidSettings
from valo_settings.preferences import fetch_settings, save_settings
from valo_settings.riot_client import Session, read_lockfile


@pytest.fixture
def session(lockfile_path):
    return Session(lockfile=read_lockfile(lockfile_path), puuid="p-1", riot_id="Pigeon#NA1")


def test_fetch_returns_dict_and_rejects_empty(session, settings):
    assert fetch_settings(FakeHttp(resp(200, settings)), session) == settings
    with pytest.raises(InvalidSettings):
        fetch_settings(FakeHttp(resp(200, {})), session)
    with pytest.raises(InvalidSettings):
        fetch_settings(FakeHttp(resp(200, is_json=False)), session)


def test_save_puts_json(session, settings):
    http = FakeHttp(resp(200))
    save_settings(http, session, settings)
    method, _, kwargs = http.calls[0]
    assert method == "PUT" and kwargs["json"] == settings


def test_401_raises_auth_expired(session, settings):
    with pytest.raises(AuthExpired):
        save_settings(FakeHttp(resp(401)), session, settings)
