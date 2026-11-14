"""Start a single receiver process; never log URL query capabilities."""
import os
from pathlib import Path

from dotenv import dotenv_values
import uvicorn


private_path = Path(os.environ.get("ONTARA_PORTALS_ENV_FILE", "~/.config/ontara/portals.env")).expanduser()
if private_path.is_file():
    for key, value in dotenv_values(private_path).items():
        if key in {"DEMO_PORTAL_ADMIN_TOKEN", "DEMO_PORTAL_RECEIPT_SECRET", "PORTALS_PUBLIC_BASE_URL", "PORT"} and value:
            os.environ.setdefault(key, value)

uvicorn.run("ontara_portals.main:app", host="0.0.0.0", port=int(os.environ.get("PORT", "8002")), workers=1, access_log=False, proxy_headers=False)
