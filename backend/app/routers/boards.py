"""Task Tracker v0.3 — the service-box board.

Board = Client rows × Stage columns. A ServiceBox slides across the stages under manual, logged
transitions with two hard guards:
    Guard 1 — cannot reach Launched unless the box is marked paid.
    Guard 2 — cannot be Closed while any single task is unsolutioned OR any reconciliation is open.
Backward moves are allowed but require a reason and are logged as such.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..constants import (
    ADMIN_ROLES,
    APPROVAL_OUTCOMES,
    BALL_WITH,
    BOX_STAGES,
    CADENCES,
    NOTIF_RECON_OPENED,
    NOTIF_STAGE_MOVED,
    RECON_RESOLVED,
    RECON_STATUSES,
    RECON_TRIGGERS,
    ROLE_ACCOUNT_MANAGER,
    ROLE_TEAM_LEAD,
    SERVICE_LINES,
    STAGE_CLOSED,
    STAGE_FOR_LAUNCH,
    STAGE_LAUNCHED,
    TASK_COMPLETED,
)
from ..database import get_db
from ..models import (
    BoxRevision,
    Client,
    RecurringTemplate,
    ReconciliationCase,
    ServiceBox,
    StageTransition,
    Task,
    TaskOccurrence,
    User,
)
from ..schemas import (
    BoxCreateIn,
    BoxUpdateIn,
    OccurrenceCheckIn,
    ReconCreateIn,
    ReconUpdateIn,
    RecurringCreateIn,
    RecurringUpdateIn,
    RevisionCreateIn,
    RevisionUpdateIn,
    StageMoveIn,
)
from ..security import get_current_user, require_min_role
from ..serializers import (
    box_card,
    box_detail,
    client_dict,
    performance_row,
    recon_dict,
    recurring_dict,
    revision_dict,
)
from ..services import audit
from ..services import notifications as notif
from ..utils.time import today_ph, utcnow

router = APIRouter(prefix="/api/boards", tags=["boards"])

MANAGER_PLUS = {ROLE_ACCOUNT_MANAGER, "admin", "super_admin"}


def _can_edit_box(user: User, box: ServiceBox) -> bool:
    """Managers edit any box; a Team Leader edits the boxes they own."""
    if user.role in MANAGER_PLUS:
        return True
    return user.role == ROLE_TEAM_LEAD and box.team_leader_id == user.id


def _require_edit(user: User, box: ServiceBox) -> None:
    if not _can_edit_box(user, box):
        raise HTTPException(status_code=403, detail="Not permitted to edit this service box")


def _get_box(box_id: int, db: Session) -> ServiceBox:
    box = db.get(ServiceBox, box_id)
    if not box:
        raise HTTPException(status_code=404, detail="Service box not found")
    return box


# --- Matrix board ----------------------------------------------------------
@router.get("")
def board(
    client_id: int | None = Query(None),
    service_line: str | None = Query(None),
    stage: str | None = Query(None),
    team_leader_id: int | None = Query(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Everything the matrix needs: clients (rows) + their service boxes (cells)."""
    today = today_ph()
    clients = db.execute(select(Client).order_by(Client.name)).scalars().all()
    q = select(ServiceBox)
    if client_id:
        q = q.where(ServiceBox.client_id == client_id)
    if service_line:
        q = q.where(ServiceBox.service_line == service_line)
    if stage:
        q = q.where(ServiceBox.stage == stage)
    if team_leader_id:
        q = q.where(ServiceBox.team_leader_id == team_leader_id)
    boxes = db.execute(q).scalars().all()
    cards = [box_card(b, db, today) for b in boxes]
    box_counts = {c.id: 0 for c in clients}
    for b in boxes:
        box_counts[b.client_id] = box_counts.get(b.client_id, 0) + 1
    rows = []
    for c in clients:
        rows.append({
            **client_dict(c),
            "box_count": box_counts.get(c.id, 0),
            "since": _client_since(c, db),
        })
    return {"clients": rows, "boxes": cards, "stages": BOX_STAGES}


def _client_since(c: Client, db: Session) -> str | None:
    earliest = db.execute(
        select(ServiceBox.started_date)
        .where(ServiceBox.client_id == c.id, ServiceBox.started_date.is_not(None))
        .order_by(ServiceBox.started_date.asc())
    ).scalars().first()
    return earliest.isoformat() if earliest else None


@router.get("/{box_id}")
def get_box(box_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return box_detail(_get_box(box_id, db), db)


@router.post("", dependencies=[Depends(require_min_role(ROLE_TEAM_LEAD))])
def create_box(payload: BoxCreateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if payload.service_line not in SERVICE_LINES:
        raise HTTPException(status_code=400, detail="Unknown service line")
    if not db.get(Client, payload.client_id):
        raise HTTPException(status_code=404, detail="Client not found")
    box = ServiceBox(
        client_id=payload.client_id,
        service_line=payload.service_line,
        team_leader_id=payload.team_leader_id,
        run_length_days=payload.run_length_days,
        notes=payload.notes,
        started_date=today_ph(),
    )
    db.add(box)
    db.flush()
    db.add(StageTransition(box_id=box.id, from_stage=None, to_stage=box.stage, moved_by_id=user.id))
    db.commit()
    audit.record(db, actor_id=user.id, table_name="service_boxes", record_id=box.id, action="create",
                 new={"client_id": box.client_id, "service_line": box.service_line})
    return box_detail(box, db)


@router.patch("/{box_id}")
def update_box(box_id: int, payload: BoxUpdateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    box = _get_box(box_id, db)
    _require_edit(user, box)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(box, field, value)
    db.commit()
    audit.record(db, actor_id=user.id, table_name="service_boxes", record_id=box.id, action="update",
                 new=payload.model_dump(exclude_unset=True))
    return box_detail(box, db)


@router.post("/{box_id}/stage")
def move_stage(box_id: int, payload: StageMoveIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    box = _get_box(box_id, db)
    _require_edit(user, box)
    target = payload.stage
    if target not in BOX_STAGES:
        raise HTTPException(status_code=400, detail="Invalid stage")
    if target == box.stage:
        return box_detail(box, db)

    backward = BOX_STAGES.index(target) < BOX_STAGES.index(box.stage)
    if backward and not (payload.reason and payload.reason.strip()):
        raise HTTPException(status_code=400, detail="A reason is required to move a box backward")

    # Guard 1 — Launched requires paid.
    if target == STAGE_LAUNCHED and not box.is_paid:
        raise HTTPException(status_code=409, detail="Cannot move to Launched — the box is not marked paid (Guard 1)")
    # Guard 2 — Closed requires no unsolutioned work and no open reconciliation.
    if target == STAGE_CLOSED:
        unsolutioned = db.execute(
            select(Task).where(Task.service_box_id == box.id, Task.status != TASK_COMPLETED)
        ).scalars().all()
        open_recon = [r for r in box.reconciliations if r.status != RECON_RESOLVED]
        if unsolutioned or open_recon:
            raise HTTPException(
                status_code=409,
                detail=f"Cannot Close — {len(unsolutioned)} unsolutioned task(s) and "
                       f"{len(open_recon)} open reconciliation(s) remain (Guard 2)",
            )

    today = today_ph()
    if target == STAGE_FOR_LAUNCH and not box.approved_date:
        box.approved_date = today
    if target == STAGE_LAUNCHED and not box.launch_date:
        box.launch_date = today
    if target == STAGE_CLOSED:
        box.closed_date = today

    old = box.stage
    box.stage = target
    db.add(StageTransition(
        box_id=box.id, from_stage=old, to_stage=target,
        is_backward=backward, reason=payload.reason, moved_by_id=user.id,
    ))
    db.commit()
    audit.record(db, actor_id=user.id, table_name="service_boxes", record_id=box.id, action="stage",
                 old={"stage": old}, new={"stage": target}, reason=payload.reason)
    if box.team_leader_id and box.team_leader_id != user.id:
        client = db.get(Client, box.client_id)
        notif.notify(db, user_id=box.team_leader_id, type=NOTIF_STAGE_MOVED,
                     title=f"{box.service_line} · {client.name if client else 'client'} → {target}",
                     link=f"/tasks?box={box.id}")
    return box_detail(box, db)


# --- Recurring templates + occurrences -------------------------------------
@router.post("/{box_id}/recurring")
def add_recurring(box_id: int, payload: RecurringCreateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    box = _get_box(box_id, db)
    _require_edit(user, box)
    if payload.cadence not in CADENCES:
        raise HTTPException(status_code=400, detail="Invalid cadence")
    tpl = RecurringTemplate(
        box_id=box.id, title=payload.title, cadence=payload.cadence,
        assignee_id=payload.assignee_id, time_span_hours=payload.time_span_hours,
        start_date=payload.start_date, end_date=payload.end_date,
    )
    db.add(tpl)
    db.commit()
    return recurring_dict(tpl, db)


@router.patch("/recurring/{tpl_id}")
def update_recurring(tpl_id: int, payload: RecurringUpdateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    tpl = db.get(RecurringTemplate, tpl_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="Recurring task not found")
    _require_edit(user, tpl.box)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(tpl, field, value)
    db.commit()
    return recurring_dict(tpl, db)


@router.post("/recurring/{tpl_id}/occurrence")
def check_occurrence(tpl_id: int, payload: OccurrenceCheckIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Tick (or untick) one occurrence. The assignee may check off their own; managers/leader too."""
    tpl = db.get(RecurringTemplate, tpl_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="Recurring task not found")
    allowed = user.id == tpl.assignee_id or _can_edit_box(user, tpl.box)
    if not allowed:
        raise HTTPException(status_code=403, detail="Not permitted to update this occurrence")

    existing = db.execute(
        select(TaskOccurrence).where(
            TaskOccurrence.template_id == tpl.id,
            TaskOccurrence.occurrence_date == payload.occurrence_date,
        )
    ).scalar_one_or_none()
    if payload.done and not existing:
        db.add(TaskOccurrence(
            template_id=tpl.id, occurrence_date=payload.occurrence_date,
            done_by_id=user.id, done_at=utcnow(), actual_hours=payload.actual_hours,
        ))
    elif not payload.done and existing:
        db.delete(existing)
    db.commit()
    db.refresh(tpl)
    return recurring_dict(tpl, db)


# --- Reconciliation cases --------------------------------------------------
@router.post("/{box_id}/reconciliation")
def open_recon(box_id: int, payload: ReconCreateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    box = _get_box(box_id, db)
    _require_edit(user, box)
    if payload.trigger_type not in RECON_TRIGGERS:
        raise HTTPException(status_code=400, detail="Unknown trigger type")
    r = ReconciliationCase(
        box_id=box.id, trigger_type=payload.trigger_type, description=payload.description,
        owner_id=payload.owner_id or box.team_leader_id,
    )
    db.add(r)
    db.commit()
    client = db.get(Client, box.client_id)
    notif.notify_managers(db, type=NOTIF_RECON_OPENED,
                          title=f"Reconciliation opened — {box.service_line} · {client.name if client else ''}",
                          body=payload.trigger_type, link=f"/tasks?box={box.id}")
    audit.record(db, actor_id=user.id, table_name="reconciliation_cases", record_id=r.id, action="open",
                 new={"trigger": r.trigger_type})
    return recon_dict(r, db)


@router.patch("/reconciliation/{recon_id}")
def update_recon(recon_id: int, payload: ReconUpdateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = db.get(ReconciliationCase, recon_id)
    if not r:
        raise HTTPException(status_code=404, detail="Reconciliation case not found")
    _require_edit(user, r.box)
    data = payload.model_dump(exclude_unset=True)
    if "status" in data and data["status"] not in RECON_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")
    was_open = r.status != RECON_RESOLVED
    for field, value in data.items():
        setattr(r, field, value)
    if r.status == RECON_RESOLVED and was_open:
        r.resolved_at = utcnow()
    db.commit()
    return recon_dict(r, db)


# --- Approval track (revision rounds) --------------------------------------
@router.post("/{box_id}/revision")
def add_revision(box_id: int, payload: RevisionCreateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    box = _get_box(box_id, db)
    _require_edit(user, box)
    if payload.ball_with not in BALL_WITH:
        raise HTTPException(status_code=400, detail="Invalid ball_with")
    next_round = (max([r.round_no for r in box.revisions], default=0)) + 1
    r = BoxRevision(box_id=box.id, round_no=next_round, what_changed=payload.what_changed, ball_with=payload.ball_with)
    db.add(r)
    db.commit()
    return revision_dict(r)


@router.patch("/revision/{rev_id}")
def update_revision(rev_id: int, payload: RevisionUpdateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = db.get(BoxRevision, rev_id)
    if not r:
        raise HTTPException(status_code=404, detail="Revision not found")
    _require_edit(user, r.box)
    data = payload.model_dump(exclude_unset=True)
    if "approval_outcome" in data and data["approval_outcome"] not in APPROVAL_OUTCOMES:
        raise HTTPException(status_code=400, detail="Invalid approval outcome")
    if "ball_with" in data and data["ball_with"] not in BALL_WITH:
        raise HTTPException(status_code=400, detail="Invalid ball_with")
    for field, value in data.items():
        setattr(r, field, value)
    db.commit()
    return revision_dict(r)


# --- Performance & personal queue ------------------------------------------
@router.get("/perf/ranking", dependencies=[Depends(require_min_role(ROLE_TEAM_LEAD))])
def ranking(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    today = today_ph()
    users = db.execute(select(User).where(User.is_active.is_(True))).scalars().all()
    rows = [performance_row(u, db, today) for u in users if u.role not in ADMIN_ROLES]
    # Rank by score desc; personnel with no signal (score None) sort to the bottom.
    rows.sort(key=lambda r: (r["score"] is not None, r["score"] or 0), reverse=True)
    for i, r in enumerate(rows, 1):
        r["rank"] = i if r["score"] is not None else None
    return rows


@router.get("/perf/queue")
def my_queue(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """The signed-in person's due-now checklist: recurring occurrences due + open single tasks."""
    today = today_ph()
    tpls = db.execute(
        select(RecurringTemplate).where(RecurringTemplate.assignee_id == user.id, RecurringTemplate.active.is_(True))
    ).scalars().all()
    due_recurring = []
    for tpl in tpls:
        rec = recurring_dict(tpl, db, today)
        if rec["due"] and not rec["due"]["done"]:
            client = db.get(Client, tpl.box.client_id) if tpl.box else None
            due_recurring.append({
                "template_id": tpl.id, "title": tpl.title, "cadence": tpl.cadence,
                "occurrence_date": rec["due"]["occurrence_date"], "box_id": tpl.box_id,
                "client_name": client.name if client else None,
            })
    open_tasks = db.execute(
        select(Task).where(Task.assigned_to_id == user.id, Task.status != TASK_COMPLETED)
    ).scalars().all()
    from ..serializers import task_card
    singles = [task_card(t, db) for t in open_tasks]
    overdue = [t for t in singles if t["due_date"] and t["due_date"] < today.isoformat()]
    return {
        "due_recurring": due_recurring,
        "open_tasks": singles,
        "overdue_tasks": overdue,
        "me": performance_row(user, db, today),
    }
