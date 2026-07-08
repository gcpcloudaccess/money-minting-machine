"""Launcher that chdir's into backend/ (so .env, SQLite file, and relative
data/report paths resolve correctly) before starting uvicorn."""

import os
import sys

BACKEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend")
os.chdir(BACKEND_DIR)
sys.path.insert(0, BACKEND_DIR)

import uvicorn  # noqa: E402

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)
