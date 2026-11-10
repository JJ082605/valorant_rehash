"""PyInstaller entry point.

PyInstaller runs its entry file as a plain script, so the relative imports in
valo_settings/__main__.py would fail. Importing the package absolutely fixes that.
"""

from valo_settings.__main__ import main

main()
