import pytest

from conftest import FakeHttp, resp
from valo_settings import applier
from valo_settings.applier import Applier
from valo_settings.errors import BackupFailed, ProfileError
from valo_settings.preferences import SETTINGS_PATH
from valo_settings.profiles import Profile
from valo_settings.riot_client import IDENTITY_PATH


@pytest.fixture
def make_applier(store, lockfile_path, settings):
    store.save(Profile(name="Main", source_riot_id="Other#EU", source_puuid="p-0", captured_at="t", settings=settings))

    def _make(*responses):
        http = FakeHttp(*responses)
        return http, Applier(http, store, lockfile_path=lockfile_path, is_valorant_running=lambda: False)

    return _make


CURRENT = {"old": True}


def test_apply_order_backup_then_put_then_verify(make_applier, identity, settings, store):
    http, a = make_applier(
        resp(200, identity), resp(200, CURRENT), resp(200, identity), resp(200), resp(200, identity), resp(200, settings)
    )
    result = a.apply("Main", "p-1")
    assert http.methods == [
        ("GET", IDENTITY_PATH), ("GET", SETTINGS_PATH), ("GET", IDENTITY_PATH),
        ("PUT", SETTINGS_PATH), ("GET", IDENTITY_PATH), ("GET", SETTINGS_PATH),
    ]
    assert result.verified is True and result.target_riot_id == "Pigeon#NA1"
    assert result.backup_path.exists()
    assert store.latest_backup("p-1").settings == CURRENT


def test_apply_aborts_if_backup_fails(make_applier, identity, store, monkeypatch):
    def boom(*a, **k):
        raise BackupFailed()

    monkeypatch.setattr(store, "write_backup", boom)
    http, a = make_applier(resp(200, identity), resp(200, CURRENT))
    with pytest.raises(BackupFailed):
        a.apply("Main", "p-1")
    assert not any(m == "PUT" for m, _ in http.methods)


def test_apply_aborts_if_account_changed(make_applier, identity):
    http, a = make_applier(resp(200, {**identity, "puuid": "p-2"}))
    with pytest.raises(ProfileError):
        a.apply("Main", "p-1")
    assert not any(m == "PUT" for m, _ in http.methods)


def test_apply_reports_unverified_on_mismatch(make_applier, identity, settings):
    _, a = make_applier(resp(200, identity), resp(200, CURRENT), resp(200, identity), resp(200), resp(200, identity), resp(200, {**settings, "extra": 1}))
    assert a.apply("Main", "p-1").verified is False


def test_verify_ignores_volatile_keys(make_applier, identity, settings, monkeypatch):
    monkeypatch.setattr(applier, "VOLATILE_KEYS", frozenset({"ts"}))
    _, a = make_applier(resp(200, identity), resp(200, CURRENT), resp(200, identity), resp(200), resp(200, identity), resp(200, {**settings, "ts": 999}))
    assert a.apply("Main", "p-1").verified is True


def _backups(store, puuid="p-1"):
    return list((store.backups_dir / puuid).glob("*.json"))


def test_auth_expired_on_put_retries_once(make_applier, identity, settings, store):
    http, a = make_applier(
        resp(200, identity), resp(200, CURRENT),
        resp(200, identity), resp(401),
        resp(200, identity), resp(200),
        resp(200, identity), resp(200, settings),
    )
    assert a.apply("Main", "p-1").verified is True
    assert [m for m, _ in http.methods].count("PUT") == 2
    assert len(_backups(store)) == 1


def test_401_after_put_does_not_overwrite_backup(make_applier, identity, settings, store):
    http, a = make_applier(
        resp(200, identity), resp(200, CURRENT),
        resp(200, identity), resp(200),
        resp(200, identity), resp(401),
        resp(200, identity), resp(200, settings),
    )
    assert a.apply("Main", "p-1").verified is True
    assert len(_backups(store)) == 1
    assert store.latest_backup("p-1").settings == CURRENT != settings


def test_identity_401_is_retried(make_applier, identity, settings):
    _, a = make_applier(
        resp(401), resp(200, identity), resp(200, CURRENT),
        resp(200, identity), resp(200), resp(200, identity), resp(200, settings),
    )
    assert a.apply("Main", "p-1").verified is True


def test_restore_applies_latest_backup(make_applier, identity, store):
    b = {"restored": True}
    store.write_backup("p-1", "Pigeon#NA1", b)
    http, a = make_applier(
        resp(200, identity), resp(200, {"current": "C"}),
        resp(200, identity), resp(200),
        resp(200, identity), resp(200, b),
    )
    assert a.restore_latest("p-1").verified is True
    puts = [kw for m, _, kw in http.calls if m == "PUT"]
    assert len(puts) == 1 and puts[0]["json"] == b


def test_restore_without_backup_raises(make_applier):
    http, a = make_applier()
    with pytest.raises(ProfileError):
        a.restore_latest("p-1")
    assert http.calls == []
