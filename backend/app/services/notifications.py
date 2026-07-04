"""In-app notification helper. Mirrors Atrium's graceful posture — always records, never crashes."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..constants import ADMIN_ROLES, NOTIF_ANNOUNCEMENT
from ..models import Notification, User


def notify(
    db: Session,
    *,
    user_id: int,
    type: str,
    title: str,
    body: str | None = None,
    link: str | None = None,
    commit: bool = True,
) -> Notification:
    n = Notification(user_id=user_id, type=type, title=title, body=body, link=link)
    db.add(n)
    if commit:
        db.commit()
    return n


def notify_managers(
    db: Session,
    *,
    type: str,
    title: str,
    body: str | None = None,
    link: str | None = None,
    team_id: int | None = None,
    commit: bool = True,
) -> None:
    """Fan a notification out to admins + (optionally) the team lead of ``team_id``."""
    targets: set[int] = set()
    for u in db.execute(select(User).where(User.role.in_(ADMIN_ROLES))).scalars():
        targets.add(u.id)
    if team_id is not None:
        for u in db.execute(
            select(User).where(User.role == "team_lead", User.team_id == team_id)
        ).scalars():
            targets.add(u.id)
    for uid in targets:
        db.add(Notification(user_id=uid, type=type, title=title, body=body, link=link))
    if commit:
        db.commit()


def broadcast(db: Session, *, title: str, body: str | None, link: str | None = None) -> int:
    """Admin announcement to every active user. Returns the count sent."""
    users = db.execute(select(User).where(User.is_active.is_(True))).scalars().all()
    for u in users:
        db.add(Notification(user_id=u.id, type=NOTIF_ANNOUNCEMENT, title=title, body=body, link=link))
    db.commit()
    return len(users)
