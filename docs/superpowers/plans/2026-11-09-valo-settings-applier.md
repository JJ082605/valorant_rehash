# Valorant Settings Applier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Windows desktop app that captures a signed-in Riot account's `Ares.PlayerSettings` into named profiles and applies them to another signed-in account, with automatic backups.

**Architecture:** Talk only to the running Riot Client's local API (lockfile → basic auth on 127.0.0.1). Small single-purpose modules (`riot_client`, `preferences`, `profiles`, `applier`) with injected I/O so everything except the UI is unit-tested on macOS with fakes. `app.py` is a thin CustomTkinter shell over `applier`.

**Tech Stack:** Python 3.11+, `requests`, `customtkinter`, `psutil`, `pytest`, PyInstaller, GitHub Actions.

**Spec:** [docs/superpowers/specs/2026-11-09-valo-settings-applier-design.md](../specs/2026-11-09-valo-settings-applier-design.md)

## Global Constraints

- Python **3.11+** (`requires-python = ">=3.11"`). The Mac's system Python is 3.9 — install 3.11+ (python.org or Homebrew) and use a venv.
- Never accept, request, or store a Riot password. No login UI of any kind.
- The lockfile password lives in memory only; never written to disk; redacted in `log.txt`.
- TLS verification disabled **only** for `127.0.0.1` requests.
- All Riot URLs/paths in one constants block per module (`riot_client.py`, `preferences.py`).
- Every Apply/Restore: backup first; if backup fails, abort with no changes.
- Backups: newest **10** kept per PUUID.
- Data dir: Windows `%APPDATA%\ValoSettings\`; macOS `~/Library/Application Support/ValoSettings/` (dev only).
- User-facing errors are plain English (copy from the spec's error table); no tracebacks in the UI.
- Package: `src/valo_settings/`, src layout, tests in `tests/`.

## Review Focus

1. **Profile names with path characters** (`../x`, `a/b`, `con`, `:`): must be rejected with a clear message, never write outside `profiles/`. → Task 3 `test_rejects_unsafe_names`.
2. **Stale lockfile** (Riot Client closed but file left behind → connection refused): must show "Couldn't talk to the Riot Client", not crash. → Task 2 `test_connection_refused_raises_unreachable`.
3. **Account switched between confirm and apply**: applier must re-check the PUUID right before writing and abort if it changed. → Task 4 `test_apply_aborts_if_account_changed`.
4. **Lockfile with trailing newline / UTF-8 BOM**: must parse. → Task 1 `test_parses_bom_and_newline`.
5. **Server adds/changes volatile fields on save** (verification false-negative): compare ignoring keys in `VOLATILE_KEYS` (empty until Task 0 finds any). → Task 4 `test_verify_ignores_volatile_keys`.

---

### Task 0: Verification spike (manual, needs a signed-in Riot Client)

**Files:**
- Create: `scripts/probe.py` (read-only; GET requests only)
- Create: `tests/fixtures/player_settings.json` (scrubbed real response)
- Modify: spec "Approach" + `claude.md` "Open items" with findings

- [ ] **Step 1:** Write `scripts/probe.py`: read lockfile (try Windows path and candidate macOS paths `~/Library/Application Support/Riot Games/Riot Client/Config/lockfile`, `~/Library/Application Support/Riot Games/Riot Client/Data/lockfile`), print port/protocol (never the password), then GET with basic auth `riot:<password>`, `verify=False`:
  - `/player-preferences/v1/data-json/Ares.PlayerSettings`
  - `/chat/v1/session`
  - `/riot-client-auth/v1/userinfo` (fallback identity candidate)
  Print status codes and top-level keys; save the settings body to `scripts/out/settings.json` (gitignored).
- [ ] **Step 2:** Run on Windows (and on the Mac with League's Riot Client signed in). Record: lockfile path per OS, settings endpoint status, identity endpoint + field names for PUUID / game name / tag.
- [ ] **Step 3:** Manually PUT the same settings body back unchanged (one-off `requests.put` in a REPL), then GET again; note any keys that changed → `VOLATILE_KEYS`.
- [ ] **Step 4:** Copy the settings body to `tests/fixtures/player_settings.json`, removing anything identifying. Update spec + `claude.md` with findings.

**Gate:** If the local settings endpoint does not work, stop and revisit the spec (remote fallback + codec) before Task 2.

---

### Task 1: Project scaffold + `riot_client`

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `src/valo_settings/__init__.py`, `src/valo_settings/errors.py`, `src/valo_settings/riot_client.py`
- Test: `tests/test_riot_client.py`

**Interfaces:**
- Produces (`errors.py`): `class ValoError(Exception)` with `user_message: str`; subclasses `ClientNotRunning`, `ClientNotReady`, `ClientUnreachable`, `AuthExpired`, `InvalidSettings`, `BackupFailed`, `ProfileError`. Each subclass has a default `user_message` from the spec table.
- Produces (`riot_client.py`):
  - `@dataclass(frozen=True) class Lockfile: name: str; pid: int; port: int; password: str; protocol: str` with `base_url -> str` (`f"{protocol}://127.0.0.1:{port}"`) and `__repr__` that hides `password`.
  - `@dataclass(frozen=True) class Session: lockfile: Lockfile; puuid: str; riot_id: str`
  - `def default_lockfile_path() -> Path` (per `sys.platform`; macOS value from Task 0)
  - `def read_lockfile(path: Path | None = None) -> Lockfile` → raises `ClientNotRunning` if missing, `ClientNotReady` if malformed
  - `def get_session(http, path: Path | None = None) -> Session` — `http` is a `requests.Session`-like object (`.get(url, auth=, verify=, timeout=)`); calls the identity endpoint confirmed in Task 0.
  - Constant `IDENTITY_PATH` and field-name constants at module top.

- [ ] **Step 1:** `pyproject.toml`: setuptools src layout, `requires-python=">=3.11"`, deps `requests`, `customtkinter`, `psutil`; optional `dev = ["pytest", "pyinstaller"]`; `[project.scripts] valo-settings = "valo_settings.__main__:main"`; pytest `testpaths=["tests"]`. `.gitignore`: venv, `__pycache__`, `dist/`, `build/`, `scripts/out/`. Then `git init`.
- [ ] **Step 2: Failing tests** in `tests/test_riot_client.py`:
  - `test_parses_lockfile`: file `"Riot Client:1234:55555:secret:https"` → `Lockfile(name="Riot Client", pid=1234, port=55555, password="secret", protocol="https")`, `base_url == "https://127.0.0.1:55555"`.
  - `test_parses_bom_and_newline`: same content prefixed `﻿`, suffixed `\n` → same result.
  - `test_missing_lockfile_raises_not_running`: nonexistent path → `ClientNotRunning`.
  - `test_malformed_lockfile_raises_not_ready`: `"garbage"` → `ClientNotReady`.
  - `test_repr_hides_password`: `"secret" not in repr(lockfile)`.
  - `test_get_session_reads_identity`: fake http returning the Task 0 identity JSON → `Session.puuid`, `Session.riot_id == "Name#TAG"`; asserts the request used `auth=("riot","secret")` and `verify=False`.
  - `test_get_session_401_raises_auth_expired`, `test_get_session_connection_error_raises_unreachable`.
- [ ] **Step 3:** Run `pytest tests/test_riot_client.py -v` → FAIL (import errors).
- [ ] **Step 4:** Implement `errors.py` and `riot_client.py`. Read with `encoding="utf-8-sig"`, `.strip()`, `split(":")` expecting exactly 5 parts. Map `requests.ConnectionError` → `ClientUnreachable`, 401/403 → `AuthExpired`, other non-2xx → `ClientNotReady`. Timeout 5s.
- [ ] **Step 5:** `pytest tests/test_riot_client.py -v` → PASS.
- [ ] **Step 6:** Commit `feat: scaffold project and riot client lockfile/session`.

---

### Task 2: `preferences`

**Files:**
- Create: `src/valo_settings/preferences.py`
- Test: `tests/test_preferences.py`

**Interfaces:**
- Consumes: `Session`, `Lockfile.base_url`, errors from Task 1.
- Produces:
  - `SETTINGS_PATH = "/player-preferences/v1/data-json/Ares.PlayerSettings"`
  - `def fetch_settings(http, session: Session) -> dict` — raises `InvalidSettings` if body isn't a non-empty dict.
  - `def save_settings(http, session: Session, settings: dict) -> None` — PUT JSON body.

- [ ] **Step 1: Failing tests** (fake http records calls; fixture from Task 0):
  - `test_fetch_returns_json_dict`: returns fixture dict; GET to `base_url + SETTINGS_PATH` with basic auth, `verify=False`.
  - `test_fetch_empty_raises_invalid`: `{}` → `InvalidSettings`; non-JSON body → `InvalidSettings`.
  - `test_save_puts_json`: PUT with `json=settings`.
  - `test_401_raises_auth_expired`, `test_5xx_raises_unreachable`.
  - `test_connection_refused_raises_unreachable` (Review Focus 2).
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement. Share a private `_request(http, method, session, path, **kw)` helper with the same status→error mapping as Task 1 (move mapping into `errors.py` as `raise_for_status(resp)` so both modules use it).
- [ ] **Step 4:** `pytest -v` → PASS.
- [ ] **Step 5:** Commit `feat: fetch and save player settings via local client`.

---

### Task 3: `profiles`

**Files:**
- Create: `src/valo_settings/profiles.py`, `src/valo_settings/paths.py`
- Test: `tests/test_profiles.py`

**Interfaces:**
- Produces (`paths.py`): `def data_dir() -> Path` (per Global Constraints; creates it).
- Produces (`profiles.py`):
  - `@dataclass class Profile: name: str; source_riot_id: str; source_puuid: str; captured_at: str; settings: dict` (`captured_at` ISO-8601 UTC).
  - `class ProfileStore(base: Path)`:
    - `save(profile: Profile, overwrite: bool = False) -> None` — raises `ProfileError` if exists and not `overwrite`, or name unsafe.
    - `load(name: str) -> Profile`, `delete(name: str) -> None`, `exists(name: str) -> bool`
    - `list() -> tuple[list[Profile], list[str]]` — (valid profiles sorted by name, names of corrupt files skipped)
    - `write_backup(puuid: str, riot_id: str, settings: dict) -> Path` — raises `BackupFailed` on any OS error.
    - `latest_backup(puuid: str) -> Profile | None`
    - `MAX_BACKUPS = 10`

- [ ] **Step 1: Failing tests** (use `tmp_path`):
  - `test_save_and_load_roundtrip`, `test_list_sorted_and_skips_corrupt` (write `bad.json` = `"{"` → appears in second list), `test_delete`.
  - `test_save_existing_without_overwrite_raises`, `test_save_existing_with_overwrite_ok`.
  - `test_rejects_unsafe_names` (Review Focus 1): `"../x"`, `"a/b"`, `"a\\b"`, `""`, `"   "`, `"con"`, `"x:y"` → `ProfileError`. Allowed: letters, digits, space, `-`, `_`, `#`, `.` (not leading), max 64 chars.
  - `test_backup_prunes_to_10`: write 12 → 10 files remain, oldest 2 gone; `latest_backup` returns the 12th.
  - `test_backup_failure_raises`: base dir is a file → `BackupFailed`.
  - `test_backups_isolated_per_puuid`.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement. Profiles at `base/profiles/<name>.json`; backups at `base/backups/<puuid>/<timestamp>.json` with filename-safe timestamp (`%Y%m%dT%H%M%S%fZ`). Write atomically (temp file + `os.replace`).
- [ ] **Step 4:** `pytest -v` → PASS.
- [ ] **Step 5:** Commit `feat: profile store with backups`.

---

### Task 4: `applier`

**Files:**
- Create: `src/valo_settings/applier.py`
- Test: `tests/test_applier.py`

**Interfaces:**
- Consumes: `get_session`, `fetch_settings`, `save_settings`, `ProfileStore`.
- Produces:
  - `VOLATILE_KEYS: frozenset[str]` (from Task 0; may be empty)
  - `@dataclass class ApplyResult: verified: bool; backup_path: Path; target_riot_id: str`
  - `class Applier(http, store: ProfileStore, lockfile_path: Path | None = None, is_valorant_running: Callable[[], bool] = default)`:
    - `current_session() -> Session`
    - `capture(name: str, overwrite: bool = False) -> Profile`
    - `apply(profile_name: str, expected_puuid: str) -> ApplyResult`
    - `restore_latest(expected_puuid: str) -> ApplyResult`
    - `valorant_running() -> bool`
  - `def default_is_valorant_running() -> bool` — `psutil` scan for `VALORANT-Win64-Shipping.exe`.

`expected_puuid` is the account shown in the confirm dialog; `apply` fetches a fresh session and raises `ProfileError("The signed-in account changed. Refresh and try again.")` if it differs.

Retry rule: any `AuthExpired` from the local API → re-read lockfile, retry the operation once, then re-raise.

- [ ] **Step 1: Failing tests** with fakes for http (scripted responses, call log) and `tmp_path` store:
  - `test_capture_saves_profile_with_source`: profile has `source_riot_id`, `source_puuid`, settings == fixture.
  - `test_capture_invalid_settings_saves_nothing`.
  - `test_apply_order_backup_then_put_then_verify`: call log shows GET identity → GET settings → backup file exists → PUT → GET settings; `result.verified is True`.
  - `test_apply_aborts_if_backup_fails`: store whose `write_backup` raises → `BackupFailed`; no PUT in call log.
  - `test_apply_aborts_if_account_changed` (Review Focus 3).
  - `test_apply_reports_unverified_on_mismatch`: re-fetch returns different dict → `verified is False`.
  - `test_verify_ignores_volatile_keys` (Review Focus 5): monkeypatch `VOLATILE_KEYS={"ts"}`; re-fetch differs only in `ts` → `verified is True`.
  - `test_auth_expired_retries_once`: first PUT 401, second 200 → success; two 401s → `AuthExpired`.
  - `test_restore_uses_latest_backup_and_backs_up_first`; `test_restore_without_backup_raises` (`ProfileError("No backup for this account yet.")`).
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement `Applier`. Restore reuses the apply path with the backup's settings.
- [ ] **Step 4:** `pytest -v` → PASS (all suites).
- [ ] **Step 5:** Commit `feat: applier orchestrates capture/apply/restore`.

---

### Task 5: UI + entry point + logging

**Files:**
- Create: `src/valo_settings/app.py`, `src/valo_settings/__main__.py`, `src/valo_settings/logging_setup.py`
- Test: `tests/test_logging_setup.py`

**Interfaces:**
- Consumes: `Applier`, `ProfileStore`, `data_dir()`, `ValoError.user_message`.
- Produces: `def main() -> None` in `__main__.py`; `def setup_logging(path: Path) -> None` with a filter that replaces any registered secret with `***`; `def register_secret(s: str) -> None`.

- [ ] **Step 1: Failing test** `test_log_redacts_secret`: register `"hunter2"`, log `"pw=hunter2"` → file contains `pw=***`.
- [ ] **Step 2:** Run → FAIL; implement `logging_setup.py`; `riot_client.read_lockfile` calls `register_secret(password)`. Run → PASS.
- [ ] **Step 3:** Build `app.py` (CustomTkinter, single window) per spec "UI": status line + Refresh; profile list (show `name — from Riot#ID`, plus a warning line if any corrupt files); buttons Capture / Apply / Restore last backup / Delete profile; inline result label (✅/❌). Capture prompts for name (default `session.riot_id`) via `CTkInputDialog`; ask before overwrite. Apply/Restore: if `valorant_running()` show the spec warning and let the user continue; confirm dialog text exactly `Apply '<profile>' to <Name#TAG>? Current settings will be backed up.`; pass the shown PUUID as `expected_puuid`. Catch `ValoError` → show `user_message`; catch anything else → log traceback, show "Something went wrong — see log.txt". Run network calls on a worker thread and marshal results back with `after()` so the window doesn't freeze.
- [ ] **Step 4: Manual check** (Mac): `python -m valo_settings` opens the window; with no Riot Client it shows "Open the Riot Client and sign in." and buttons that need a session are disabled.
- [ ] **Step 5:** Commit `feat: CustomTkinter UI`.

---

### Task 6: README, CI, packaging, release checklist

**Files:**
- Create: `README.md`, `.github/workflows/ci.yml`, `valo-settings.spec` (or a documented PyInstaller command), `docs/release-checklist.md`

- [ ] **Step 1:** `README.md`: what it does; how it authenticates (lockfile, never a password — link the two source files that do it); unofficial-API / Riot ToS caveat; Windows-only; install from Releases or build from source; antivirus false-positive note; where data is stored.
- [ ] **Step 2:** `ci.yml`: on push/PR, matrix `ubuntu-latest` + `windows-latest`, Python 3.11 + 3.12, `pip install -e .[dev]`, `pytest -v`.
- [ ] **Step 3:** PyInstaller: `pyinstaller --onefile --windowed --name ValoSettings --collect-data customtkinter src/valo_settings/__main__.py`. Document in README; add a CI job on tags that builds on `windows-latest` and uploads the `.exe` artifact.
- [ ] **Step 4:** `docs/release-checklist.md` (Windows, two accounts): capture A → switch to B → apply → ✅ → launch Valorant and check crosshair/sensitivity/keybinds → restore → confirm B's original settings back.
- [ ] **Step 5:** Push branch, confirm CI green. Commit `docs: readme, ci, packaging`.

---

## Commands (once Task 1 lands)

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -v                                   # all tests
pytest tests/test_applier.py::test_apply_order_backup_then_put_then_verify -v   # one test
python -m valo_settings                     # run the app
```
