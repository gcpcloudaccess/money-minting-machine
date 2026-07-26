"""Re-exports whichever model backend is active (SQLAlchemy+SQLite by
default, Firestore when FIRESTORE_PROJECT_ID is set - see app/config.py's
use_firestore and the two model modules' docstrings) so every consumer
file's `from app.db.models import X` keeps working unchanged no matter which
backend is selected."""

from app.config import get_settings

if get_settings().use_firestore:
    from app.db.models_firestore import (
        AgentReliability,
        AgentVote,
        AuditLog,
        Decision,
        Portfolio,
        Position,
        PositionalPick,
        ResearchNote,
        Trade,
        utcnow,
    )
else:
    from app.db.models_sqlalchemy import (
        AgentReliability,
        AgentVote,
        AuditLog,
        Decision,
        Portfolio,
        Position,
        PositionalPick,
        ResearchNote,
        Trade,
        utcnow,
    )

__all__ = [
    "AgentReliability",
    "AgentVote",
    "AuditLog",
    "Decision",
    "Portfolio",
    "Position",
    "PositionalPick",
    "ResearchNote",
    "Trade",
    "utcnow",
]
