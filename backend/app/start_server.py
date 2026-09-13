"""Render entrypoint: validate, migrate, then serve without raw access logs."""
import os
import subprocess
import sys

import uvicorn

from app.config import get_settings


def main():
    get_settings().validate_deployment()
    # Free Render services do not support pre-deploy commands. Migrations are
    # additive and run before this instance accepts requests. Capture failures
    # so database connection details can never leak into provider build logs.
    result = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                            capture_output=True, text=True)
    if result.returncode:
        raise SystemExit("Database preparation failed. Check the configured database and migration state locally.")
    uvicorn.run("app.main:app", host="0.0.0.0", port=int(os.environ.get("PORT", "10000")),
                access_log=False, proxy_headers=True)


if __name__ == "__main__":
    main()
