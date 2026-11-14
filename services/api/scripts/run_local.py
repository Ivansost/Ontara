#!/usr/bin/env python3
"""Load private configuration as data and start the API; never source secrets."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import dotenv_values

parser = argparse.ArgumentParser()
parser.add_argument("--port", type=int, default=8001)
args = parser.parse_args()
private_dir = Path.home() / ".config" / "ontara"
for filename in ("mongodb.env", "runtime.env", "agentmail.env"):
    path = private_dir / filename
    if path.is_file():
        for key, value in dotenv_values(path).items():
            if value is not None:
                os.environ.setdefault(key, value)
api_dir = str(Path(__file__).resolve().parents[1])
os.execv(sys.executable, [sys.executable, "-m", "uvicorn", "app.main:app", "--app-dir", api_dir, "--host", "127.0.0.1", "--port", str(args.port)])
