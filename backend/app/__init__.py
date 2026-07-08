"""Executes on every import of the `app` package - the one place guaranteed
to run before any agent code, regardless of entry point (uvicorn CLI,
run_backend.py, or pytest). Adds backend/vendor/ to sys.path so the
unmodified, teammate-contributed agent packages under it (algo_agent,
risk_agent, technical_analyst_agent, ...) stay importable by their own
original top-level names (e.g. `from risk_agent.models import ...`) without
touching a single line of vendored code."""

import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))
