"""Keep portable application state beside the bundled executable."""

import os
from pathlib import Path
import sys


portable_home = Path(sys.executable).resolve().parent / "data"
portable_home.mkdir(parents=True, exist_ok=True)
os.environ["USERPROFILE"] = str(portable_home)
os.environ["HOME"] = str(portable_home)
