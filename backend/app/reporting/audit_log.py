from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import AuditLog


def log_event(db: Session, event_type: str, payload: dict) -> None:
    db.add(AuditLog(event_type=event_type, payload_json=payload))
    db.commit()
