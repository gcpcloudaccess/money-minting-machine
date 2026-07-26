from __future__ import annotations

from app.db.models import AuditLog
from app.db.session import DbSession as Session


def log_event(db: Session, event_type: str, payload: dict) -> None:
    db.add(AuditLog(event_type=event_type, payload_json=payload))
    db.commit()
