"""Local development starter. Live execution is deployed to the cloud."""
import os
from pathlib import Path
from dotenv import dotenv_values
import uvicorn


def main():
    allowed = {
        "MONGODB_URI", "MONGODB_DATABASE", "CHECKPOINT_DB_NAME", "GEMINI_API_KEY", "GOOGLE_API_KEY",
        "ONTARA_GENERATION_PROVIDER", "ONTARA_GENERATION_MODEL", "GENERATION_PROVIDER", "GENERATION_MODEL",
        "ONTARA_INTERNAL_TOKEN", "BACKEND_BASE_URL", "EXECUTOR_BASE_URL", "PORTALS_BASE_URL", "ALLOWED_PORTAL_HOSTS",
        "ONTARA_RUNTIME_MODE", "ONTARA_ENABLE_DEMO_FAULTS", "AGENT_ENGINE_CLIENT_ID", "AGENT_ENGINE_CLIENT_SECRET",
        "AGENT_ENGINE_PROJECT_ID", "AGENT_ENGINE_WORKSPACE_ID",
    }
    for name in ("mongodb.env", "gemini.env", "runtime.env"):
        path = Path.home() / ".config" / "ontara" / name
        if path.exists():
            for key, value in dotenv_values(path).items():
                if value is not None and key in allowed:
                    os.environ.setdefault(key, value)
    if os.environ.get("ONTARA_GENERATION_PROVIDER"):
        os.environ.setdefault("GENERATION_PROVIDER", os.environ["ONTARA_GENERATION_PROVIDER"])
    if os.environ.get("ONTARA_GENERATION_MODEL"):
        os.environ.setdefault("GENERATION_MODEL", os.environ["ONTARA_GENERATION_MODEL"])
    if os.environ.get("GEMINI_API_KEY"):
        os.environ.setdefault("GOOGLE_API_KEY", os.environ["GEMINI_API_KEY"])
    uvicorn.run("ontara_executor.main:app", host="127.0.0.1", port=int(os.environ.get("PORT", "8003")), access_log=False)


if __name__ == "__main__":
    main()
