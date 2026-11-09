from datetime import datetime, timedelta, timezone

import pytest

from valo_settings import profiles
from valo_settings.errors import ProfileError
from valo_settings.profiles import Profile


def make(name, settings):
    return Profile(name=name, source_riot_id="Pigeon#NA1", source_puuid="p-1", captured_at="t", settings=settings)


def test_save_and_load_roundtrip(store, settings):
    store.save(make("Main", settings))
    assert store.load("Main") == make("Main", settings)


def test_list_skips_corrupt(store, settings):
    store.save(make("b", settings))
    store.save(make("A", settings))
    (store.profiles_dir / "bad.json").write_text("{", encoding="utf-8")
    good, bad = store.list()
    assert [p.name for p in good] == ["A", "b"]
    assert bad == ["bad"]


def test_overwrite_rejected_without_flag(store, settings):
    store.save(make("Main", settings))
    with pytest.raises(ProfileError):
        store.save(make("Main", {"x": 1}))
    store.save(make("Main", {"x": 1}), overwrite=True)
    assert store.load("Main").settings == {"x": 1}


@pytest.mark.parametrize("name", ["../x", "a/b", "a\\b", "", "   ", "con", "x:y"])
def test_rejects_unsafe_names(store, settings, name):
    with pytest.raises(ProfileError):
        store.save(make(name, settings))
    assert not store.profiles_dir.exists() or list(store.profiles_dir.iterdir()) == []


def test_backup_prunes_to_10(store, monkeypatch):
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    ticks = iter(range(1000))

    class FakeDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return base + timedelta(seconds=next(ticks))

    monkeypatch.setattr(profiles, "datetime", FakeDatetime)
    paths = [store.write_backup("p-1", "Pigeon#NA1", {"n": i}) for i in range(12)]
    remaining = sorted((store.backups_dir / "p-1").glob("*.json"))
    assert len(remaining) == 10
    assert not paths[0].exists() and not paths[1].exists()
    assert store.latest_backup("p-1").settings == {"n": 11}


@pytest.mark.parametrize("name", ["Pigeon#NA1", "Ñandú#ES1", "ピジョン#JP1", "Голубь#RU1"])
def test_unicode_names_allowed(store, settings, name):
    store.save(make(name, settings))
    assert store.load(name).settings == settings
