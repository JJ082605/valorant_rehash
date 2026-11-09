# Release checklist (Windows PC, two accounts A and B)

- [ ] `python scripts/probe.py` → settings and identity endpoints return 200
- [ ] Sign in as A → Refresh → status shows `Signed in as A#TAG`
- [ ] Capture → profile listed as `A#TAG — from A#TAG`
- [ ] Switch to B in Riot Client → Refresh → status shows B
- [ ] Apply A's profile → ✅, backup file exists under `%APPDATA%\ValoSettings\backups\<B puuid>\`
- [ ] Launch VALORANT as B → crosshair, sensitivity, keybinds match A
- [ ] Close VALORANT → Restore last backup → ✅ → launch → B's original settings are back
- [ ] With VALORANT open, Apply → "Close Valorant first" warning appears
- [ ] Close Riot Client → Refresh → "Open the Riot Client and sign in."
- [ ] `log.txt` does not contain the lockfile password
