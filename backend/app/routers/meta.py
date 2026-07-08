"""Reference data for the frontend: teams, clients, and the enum vocabularies used in dropdowns."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..constants import (
    ALL_ROLES,
    APPROVAL_OUTCOMES,
    BALL_WITH,
    BOX_STAGES,
    CADENCES,
    GYM_DAY_TYPES,
    PRIORITIES,
    RECON_STATUSES,
    RECON_TRIGGERS,
    ROLE_LABELS,
    SERVICE_LINES,
    SET_TYPES,
    TASK_LABELS,
    TASK_STATUSES,
)
from ..database import get_db
from ..models import Client, Team, User
from ..security import get_current_user, require_roles
from ..serializers import client_dict, team_dict

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/teams")
def teams(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [team_dict(t) for t in db.execute(select(Team).order_by(Team.name)).scalars().all()]


@router.get("/clients")
def clients(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [client_dict(c) for c in db.execute(select(Client).order_by(Client.name)).scalars().all()]


CLIENT_EDITORS = ("account_manager", "admin", "super_admin")


@router.post("/clients", dependencies=[Depends(require_roles(*CLIENT_EDITORS))])
def create_client(payload: dict, db: Session = Depends(get_db)):
    name = (payload or {}).get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Client name is required")
    if db.execute(select(Client).where(Client.name == name)).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="A client with that name already exists")
    c = Client(
        name=name,
        contact_email=payload.get("contact_email") or None,
        atrium_client_id=payload.get("atrium_client_id") or None,
        color=payload.get("color") or None,
    )
    db.add(c)
    db.commit()
    return client_dict(c)


@router.patch("/clients/{client_id}", dependencies=[Depends(require_roles(*CLIENT_EDITORS))])
def update_client(client_id: int, payload: dict, db: Session = Depends(get_db)):
    c = db.get(Client, client_id)
    if not c:
        raise HTTPException(status_code=404, detail="Client not found")
    if "name" in payload:
        name = (payload.get("name") or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="Client name cannot be empty")
        clash = db.execute(select(Client).where(Client.name == name, Client.id != client_id)).scalar_one_or_none()
        if clash:
            raise HTTPException(status_code=409, detail="A client with that name already exists")
        c.name = name
    if "contact_email" in payload:
        c.contact_email = payload.get("contact_email") or None
    if "atrium_client_id" in payload:
        c.atrium_client_id = payload.get("atrium_client_id") or None
    if "color" in payload:
        c.color = payload.get("color") or None
    db.commit()
    return client_dict(c)


@router.delete("/clients/{client_id}", dependencies=[Depends(require_roles(*CLIENT_EDITORS))])
def delete_client(client_id: int, db: Session = Depends(get_db)):
    from ..models import ServiceBox, Task

    c = db.get(Client, client_id)
    if not c:
        raise HTTPException(status_code=404, detail="Client not found")
    # Detach single tasks, then remove the client's service boxes (cascades to their sub-objects).
    db.query(Task).filter(Task.client_id == client_id).update(
        {Task.client_id: None, Task.service_box_id: None}, synchronize_session=False
    )
    for box in db.execute(select(ServiceBox).where(ServiceBox.client_id == client_id)).scalars().all():
        db.delete(box)
    db.delete(c)
    db.commit()
    return {"ok": True}


@router.get("/vocab")
def vocab(user: User = Depends(get_current_user)):
    """All enum vocabularies in one shot — labels, statuses, priorities, day types, etc."""
    return {
        "roles": [{"value": r, "label": ROLE_LABELS[r]} for r in ALL_ROLES],
        "task_statuses": TASK_STATUSES,
        "priorities": PRIORITIES,
        "task_labels": TASK_LABELS,
        "gym_day_types": GYM_DAY_TYPES,
        "set_types": SET_TYPES,
        # Task Tracker v0.3
        "service_lines": SERVICE_LINES,
        "box_stages": BOX_STAGES,
        "cadences": CADENCES,
        "recon_triggers": RECON_TRIGGERS,
        "recon_statuses": RECON_STATUSES,
        "approval_outcomes": APPROVAL_OUTCOMES,
        "ball_with": BALL_WITH,
    }
