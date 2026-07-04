"""Audit-log helper. Every important change routes through ``record`` so the trail is uniform."""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from ..models import AuditLog


def record(
    db: Session,
    *,
    actor_id: int | None,
    table_name: str,
    record_id: Any = None,
    action: str,
    old: Any = None,
    new: Any = None,
    reason: str | None = None,
    commit: bool = True,
) -> AuditLog:
    entry = AuditLog(
        actor_id=actor_id,
        table_name=table_name,
        record_id=str(record_id) if record_id is not None else None,
        action=action,
        old_value_json=json.dumps(old, default=str) if old is not None else None,
        new_value_json=json.dumps(new, default=str) if new is not None else None,
        reason=reason,
    )
    db.add(entry)
    if commit:
        db.commit()
    return entry
