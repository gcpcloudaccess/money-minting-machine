"""Executes on every import of the `app` package - the one place guaranteed
to run before any agent code, regardless of entry point (uvicorn CLI,
run_backend.py, or pytest). Adds backend/external_agents/ to sys.path so the
unmodified, teammate-contributed agent packages under it (algo_agent,
risk_agent, technical_analyst_agent, ...) stay importable by their own
original top-level names (e.g. `from risk_agent.models import ...`) without
touching a single line of vendored code. Named "external_agents" (not
"vendor") to keep it distinct from app/agents/, which holds our own
adapter/orchestration code."""

import sys
from pathlib import Path

_EXTERNAL_AGENTS_DIR = Path(__file__).resolve().parent.parent / "external_agents"
if str(_EXTERNAL_AGENTS_DIR) not in sys.path:
    sys.path.insert(0, str(_EXTERNAL_AGENTS_DIR))
