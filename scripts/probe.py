"""Read-only probe of the local Riot Client API (Task 0 / spec "Step 0").

Run with the Riot Client open and signed in:
    python scripts/probe.py

Prints ports, status codes and top-level keys. Never prints the lockfile
password. Saves the raw settings response to scripts/out/settings.json
(gitignored) so it can be scrubbed into tests/fixtures/.
Only sends GET requests — it never changes anything.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

CANDIDATES = [
    Path(os.environ.get("LOCALAPPDATA", "")) / "Riot Games/Riot Client/Config/lockfile",
    Path.home() / "Library/Application Support/Riot Games/Riot Client/Config/lockfile",
    Path.home() / "Library/Application Support/Riot Games/Riot Client/Data/lockfile",
]

PATHS = [
    "/player-preferences/v1/data-json/Ares.PlayerSettings",
    "/chat/v1/session",
    "/riot-client-auth/v1/userinfo",
    "/player-account/aliases/v1/active",
]


def main() -> int:
    lockfile = next((p for p in CANDIDATES if p.is_file()), None)
    if lockfile is None:
        print("No lockfile found. Tried:")
        for p in CANDIDATES:
            print("  ", p)
        return 1
    name, pid, port, password, protocol = lockfile.read_text("utf-8-sig").strip().split(":")
    print(f"lockfile: {lockfile}\n  name={name} pid={pid} port={port} protocol={protocol}")

    out = Path(__file__).parent / "out"
    out.mkdir(exist_ok=True)
    for path in PATHS:
        url = f"{protocol}://127.0.0.1:{port}{path}"
        try:
            r = requests.get(url, auth=("riot", password), verify=False, timeout=5)
        except requests.RequestException as e:
            print(f"\nGET {path} -> ERROR {e}")
            continue
        print(f"\nGET {path} -> {r.status_code}")
        try:
            body = r.json()
        except ValueError:
            print("  (not JSON)", r.text[:200])
            continue
        if isinstance(body, dict):
            print("  keys:", sorted(body.keys()))
        if path.endswith("Ares.PlayerSettings") and r.ok:
            (out / "settings.json").write_text(json.dumps(body, indent=2))
            print("  saved to scripts/out/settings.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
