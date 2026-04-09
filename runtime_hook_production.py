"""PyInstaller runtime hook — mark packaged builds as production."""
import os

os.environ["FALL_IN_PRODUCTION"] = "1"
