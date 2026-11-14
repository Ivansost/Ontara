"""The optional path supports testing isolated team worktrees before integration."""
import os

import app

if os.environ.get("ONTARA_TEST_BACKEND_APP_PATH"):
    app.__path__.append(os.environ["ONTARA_TEST_BACKEND_APP_PATH"])
