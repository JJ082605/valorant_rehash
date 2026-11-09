from __future__ import annotations

import sys


def main() -> None:
    import requests
    import urllib3

    from .applier import Applier
    from .logging_setup import setup_logging
    from .paths import data_dir
    from .profiles import ProfileStore

    # Only 127.0.0.1 requests use verify=False (Riot Client's self-signed cert).
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    base = data_dir()
    setup_logging(base / "log.txt")

    if sys.platform != "win32":
        print("Note: VALORANT is Windows-only; running in development mode.", file=sys.stderr)

    try:
        from .app import App
    except ImportError as e:  # usually: this Python was built without Tk
        print(f"Can't start the window ({e}). Use a Python build with Tk.", file=sys.stderr)
        sys.exit(1)

    http = requests.Session()
    http.trust_env = False  # ignore system proxies; we only ever talk to 127.0.0.1
    App(Applier(http, ProfileStore(base))).mainloop()


if __name__ == "__main__":
    main()
