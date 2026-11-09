# Valorant Settings Applier — Design

**Date:** 2026-11-09
**Status:** Approved

## Goal

A Windows desktop tool that copies Valorant account settings (sensitivity, crosshair, keybinds, HUD — everything in Riot's account-synced `Ares.PlayerSettings`) from one Riot account to another on the same PC. Built for personal use and published as a public GitHub repo.

**Success criteria**
- A user can capture settings from account A, switch to account B in the Riot Client, and apply them, with a verified result.
- The tool never asks for, sees, or stores a Riot password or token on disk.
- Any apply can be undone via an automatic backup.
- Code is small and readable enough that a stranger can audit it.

## Non-goals (v1)

- Username/password login of any kind (direct API login is captcha-blocked and risks account flags).
- Embedded Riot login webview (possible v2 if requested).
- Partial apply (only crosshair / only keybinds) — deferred to v2.
- Import/export or sharing profiles.
- Local graphics/video settings (`GameUserSettings.ini`) — already machine-wide, shared across accounts.

## Approach

Talk only to the **running Riot Client's local API**. The client writes a lockfile with a local port and a random per-session password; the tool uses that to read and write the signed-in account's settings. No Riot password, no remote access token.

1. Read the lockfile → `name:pid:port:password:protocol`.
   - Windows: `%LOCALAPPDATA%\Riot Games\Riot Client\Config\lockfile`
   - macOS: unknown — find during verification.
2. All local requests: `{protocol}://127.0.0.1:{port}`, basic auth `riot:{password}`, self-signed cert (TLS verify disabled for 127.0.0.1 only).
3. **Settings (primary):** `GET` / `PUT` `/player-preferences/v1/data-json/Ares.PlayerSettings`. GET returns plain JSON; PUT takes the same JSON as the body. (Source: ValorantCC `Processor.cs`.)
4. **Identity:** PUUID and Riot ID (`Name#TAG`) from a local endpoint — likely `/chat/v1/session`; confirm during verification.

**Fallback (only if verification shows the local settings endpoint doesn't work):** remote `https://playerpreferences.riotgames.com/playerPref/v3/getPreference/Ares.PlayerSettings` and `PUT .../playerPref/v3/savePreference` with body `{ "type": "Ares.PlayerSettings", "data": <compressed blob> }`, using a token from local `/entitlements/v1/token`. This needs `codec.py` for the compression format, which is not yet confirmed. Not built unless needed.

**Step 0 of implementation — verification spike** on a machine with the Riot Client signed in: confirm lockfile path (incl. macOS), the local settings GET/PUT, the identity endpoint and its field names, and save a real sample response (with personal data removed) as a test fixture.

**Risk:** endpoints are unofficial and undocumented by Riot. All paths live in one constants block in `preferences.py` / `riot_client.py` so they are easy to update. README states the ToS/unofficial-API caveat plainly.

References: [ValorantCC](https://github.com/weedeej/ValorantCC/blob/master/ValorantCC/src/Processor.cs), [techchrism valorant-api-docs](https://techchrism.github.io/valorant-api-docs/common-components.html) (moved to valapidocs.techchrism.me), [valorant-exporter](https://pkg.go.dev/github.com/Andosius/valorant-exporter/cfg).

## Architecture

Python 3.11+, CustomTkinter UI, packaged as a single `.exe` via PyInstaller.

```
valo-settings/
├── src/valo_settings/
│   ├── riot_client.py   # lockfile parsing + identity → Session(port, password, protocol, puuid, riot_id)
│   ├── preferences.py   # fetch_settings(session) -> dict; save_settings(session, dict)
│   ├── profiles.py      # ProfileStore: save/list/load/delete profiles; write/list/prune backups
│   ├── applier.py       # capture / apply / restore orchestration (backup → write → verify)
│   ├── app.py           # CustomTkinter window; calls applier only, no logic
│   └── __main__.py
├── tests/
├── README.md
└── pyproject.toml
```

Units and boundaries:
- **riot_client** — reads the lockfile and identity. Lockfile path injectable for tests.
- **preferences** — the only module that reads/writes settings. HTTP client injectable for tests.
- **profiles** — filesystem only; base directory injectable.
- **applier** — orchestrates the above; all flow logic lives here so it is unit-testable without a UI.
- **app** — presentation only.

(`applier.py` was added during spec writing to keep the Apply flow testable outside the UI.)

## Storage

Base dir: `%APPDATA%\ValoSettings\`

- `profiles/<name>.json` — `{ "name", "source_riot_id", "source_puuid", "captured_at", "settings": <JSON object> }`
- `backups/<puuid>/<ISO-timestamp>.json` — same shape; newest 10 kept per PUUID.

The lockfile password is held in memory only and re-read for every operation.

## UI

Single window:
- Status line: `Signed in as Name#TAG` / `Riot Client not running` (Refresh button).
- Profile list.
- Buttons: **Capture**, **Apply**, **Restore last backup**, **Delete profile**.
- Result messages shown inline (✅ / ❌ with plain-English text).

## Flows

**Capture**
1. Get session from lockfile.
2. Fetch settings.
3. Validate (non-empty JSON object); refuse to save otherwise.
4. Prompt for profile name (default: Riot ID); refuse to overwrite an existing name without confirmation.
5. Save profile.

**Apply** (selected profile → currently signed-in account)
1. Get fresh session.
2. Confirm dialog: "Apply '<profile>' to <Name#TAG>? Current settings will be backed up."
3. Fetch current settings and write backup. **If backup fails, abort with no changes.**
4. Save profile settings.
5. Re-fetch and compare to the profile; report ✅ or ❌.

**Restore last backup** — newest backup for the current PUUID, applied through the same steps as Apply (including taking a backup of the current state first).

## Error handling

| Condition | Behavior |
|---|---|
| Lockfile missing | "Open the Riot Client and sign in." |
| Local API refuses / identity request fails | "Riot Client isn't signed in yet — try again in a few seconds." |
| `VALORANT-Win64-Shipping.exe` running | Warning before Apply/Restore: "Close Valorant first or it may overwrite these settings." User may proceed. |
| 401 from local API (client restarted, new lockfile) | Re-read lockfile, retry once, then error. |
| Connection error / 5xx | "Couldn't talk to the Riot Client." No state changed. |
| Corrupt profile/backup file | Skipped in list with a warning; never applied. |
| Not running on Windows | Best-effort macOS support for development: lockfile path resolved per-OS (macOS path found in Step 0). If no lockfile is found, the same "Open the Riot Client" message applies. |

No raw tracebacks shown to the user; full errors logged to `%APPDATA%\ValoSettings\log.txt` (tokens redacted).

## Testing

- Unit tests (pytest), runnable on macOS/Linux:
  - lockfile parsing (valid, missing, malformed).
  - ProfileStore save/load/list/delete, backup pruning to 10.
  - applier ordering: backup → save → verify; abort if backup fails; retry on 401.
- Riot client and HTTP mocked via injected fakes.
- GitHub Actions runs tests on every push (ubuntu + windows runners).
- macOS dev testing: the UI and all mocked tests run on a Mac. If the Riot Client (installed with League of Legends) is signed in on the Mac, Capture/Apply against real accounts may also work, because the settings live on Riot's servers. Checked in Step 0.
- Manual release checklist on a real Windows PC with two accounts: capture, apply, verify in-game, restore.

## Distribution

- Public GitHub repo
- README: what it does, how it authenticates (no password, lockfile explanation), unofficial-API/ToS caveat, build instructions.
- GitHub Releases ships the PyInstaller `.exe`; README notes possible antivirus false positives and how to build from source instead.
