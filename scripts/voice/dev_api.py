"""Loopback-only voice test API using the existing Atlas case backend.

Mail and dispatch are explicitly disabled. This harness cannot approve a report
on its own; the text smoke creates one synthetic, unapproved case.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/api"))

from dotenv import dotenv_values
import uvicorn

from app.config import Settings
from app.main import create_app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--voice-env-file", type=Path, default=Path.home() / ".config/ontara/elevenlabs.env")
    parser.add_argument("--port", type=int, default=8027)
    args = parser.parse_args()
    private = dotenv_values(args.voice_env_file)
    for key in ("ELEVENLABS_API_KEY", "ELEVENLABS_AGENT_ID", "ONTARA_VOICE_ENABLED"):
        if private.get(key):
            os.environ[key] = private[key]
    os.environ["ONTARA_MAIL_ENABLED"] = "false"
    settings = replace(Settings.load(), cookie_secure=False, dispatch_url="",
                       allowed_origins=("http://localhost:3027", "http://127.0.0.1:3027"))
    app = create_app(settings)
    uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False, log_level="warning")


if __name__ == "__main__":
    main()
