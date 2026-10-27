"""Keep portable application state beside the bundled executable."""

import os
from pathlib import Path
import sys


portable_home = Path(sys.executable).resolve().parent / "data"
portable_home.mkdir(parents=True, exist_ok=True)
# Programs started from the app (the game, for measuring) need the real profile.
for name in ("USERPROFILE", "HOME"):
    os.environ.setdefault(f"BEAMNG_INFOGEN_ORIGINAL_{name}", os.environ.get(name, ""))
os.environ["USERPROFILE"] = str(portable_home)
os.environ["HOME"] = str(portable_home)
