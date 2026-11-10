# VALORANT Settings Applier

Copy your VALORANT settings (sensitivity, crosshair, keybinds, HUD) from one Riot account to another on the same Windows PC.

**It never asks for your password.** It uses the Riot Client that's already open and signed in on your PC.

## How it works

1. Sign in to account A in the Riot Client and click **Capture**. This saves A's settings as a named profile.
2. Switch to account B in the Riot Client and click **Refresh**.
3. Select the profile and click **Apply**. B's current settings are backed up first, then replaced. The app reads them back to check that the change worked.
4. Changed your mind? Click **Restore last backup**.

### Why no password?

While the Riot Client is running, it writes a *lockfile* to
`%LOCALAPPDATA%\Riot Games\Riot Client\Config\lockfile`. The lockfile holds a local port and a random password for that session. That password only works for connections from your own PC (`127.0.0.1`) and is **not** your Riot password. This app reads the lockfile and asks the local Riot Client who is signed in and for a short-lived sign-in token. It then uses that token to read and save the account's settings on Riot's own settings server (`player-preferences-euc1.pp.sgp.pvp.net`), the same way the game does.

You can check this yourself. All network code is in two small files:
- [`riot_client.py`](src/valo_settings/riot_client.py) reads the lockfile and the signed-in account.
- [`preferences.py`](src/valo_settings/preferences.py) reads and writes settings.

The lockfile password and tokens are kept in memory only. They're never saved, and they're removed from the log.

## ⚠ Caveats

- This uses **unofficial, undocumented** Riot Client endpoints, the same ones other open-source settings tools use. Riot could change or block them at any time. Use at your own risk, and see Riot's Terms of Service.
- Close VALORANT before applying, or the game may overwrite the new settings.
- Graphics and video settings are stored on your PC, not your account, so they're already shared between accounts and aren't touched.
- Windows only, because VALORANT is Windows only.

## Install

Download `ValoSettings.exe` from [Releases](../../releases) and run it.

Some antivirus programs flag PyInstaller-built `.exe` files by mistake. If you'd rather not trust the download, build it yourself (below).

The `.exe` isn't code-signed, so Windows may warn you:
- **"Windows protected your PC"** (SmartScreen): click **More info → Run anyway**.
- **"An Application Control policy has blocked this file"** or the app silently won't open: **Smart App Control** is on. It blocks all unsigned apps, and there's no per-app exception. Run from source instead (below).

## Build from source

Requires Python 3.11+ with Tk.

```bash
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
python -m valo_settings          # run
pytest -q                        # tests (run anywhere, no Riot Client needed)
pyinstaller --onefile --windowed --name ValoSettings --collect-data customtkinter --paths src scripts/launcher.py
```

The `.exe` is written to `dist/`.

### Checking the endpoints

`python scripts/probe.py` (with the Riot Client signed in) prints which local endpoints respond, without changing anything.

## Where data is stored

`%APPDATA%\ValoSettings\`
- `profiles\<name>.json`: your saved profiles
- `backups\<account-id>\`: automatic backups, newest 10 per account
- `log.txt`
