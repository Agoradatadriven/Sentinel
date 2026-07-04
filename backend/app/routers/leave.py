"""Leave Management: types, balances, requests, approvals."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..constants import (
    LEAVE_APPROVED,
    LEAVE_PENDING,
    LEAVE_REJECTED,
    NOTIF_APPROVAL,
    ROLE_TEAM_LEAD,
)
from ..database import get_db
from ..models import LeaveBalance, LeaveRequest, LeaveType, User
from ..schemas import LeaveDecisionIn, LeaveRequestIn
from ..security import get_current_user, require_min_role
from ..serializers import leave_balance_dict, leave_request_dict, leave_type_dict
from ..services import audit
from ..services import leave as leave_svc
from ..services import notifications as notif
from ..utils.time import today_ph, utcnow

router = APIRouter(prefix="/api/leave", tags=["leave"])


@router.get("/types")
def types(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(LeaveType).order_by(LeaveType.id)).scalars().all()
    return [leave_type_dict(lt) for lt in rows]


@router.get("/balance")
def balance(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    year = today_ph().year
    leave_svc.ensure_balances(db, user.id, year)
    rows = db.execute(
        select(LeaveBalance).where(LeaveBalance.user_id == user.id, LeaveBalance.year == year)
    ).scalars().all()
    return [leave_balance_dict(b, db.get(LeaveType, b.leave_type_id)) for b in rows]


@router.get("/my")
def my_requests(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.execute(
        select(LeaveRequest).where(LeaveRequest.user_id == user.id).order_by(LeaveRequest.created_at.desc())
    ).scalars().all()
    return [leave_request_dict(r, db) for r in rows]


@router.post("/request")
def create_request(payload: LeaveRequestIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    lt = db.get(LeaveType, payload.leave_type_id)
    if not lt:
        raise HTTPException(status_code=404, detail="Leave type not found")
    if payload.end_date < payload.start_date:
        raise HTTPException(status_code=400, detail="End date is before start date")
    days = leave_svc.count_days(payload.start_date, payload.end_date)
    req = LeaveRequest(
        user_id=user.id, leave_type_id=lt.id, start_date=payload.start_date,
        end_date=payload.end_date, total_days=days, reason=payload.reason, status=LEAVE_PENDING,
    )
    db.add(req)
    db.commit()
    notif.notify_managers(
        db, type=NOTIF_APPROVAL, title=f"{lt.name} request from {user.name} ({days}d)",
        body=payload.reason, link="/leave", team_id=user.team_id,
    )
    audit.record(db, actor_id=user.id, table_name="leave_requests", record_id=req.id, action="create",
                 new={"type": lt.name, "days": days})
    return leave_request_dict(req, db)


@router.get("/requests")
def all_requests(
    status: str | None = Query(None),
    reviewer: User = Depends(require_min_role(ROLE_TEAM_LEAD)),
    db: Session = Depends(get_db),
):
    q = select(LeaveRequest).order_by(LeaveRequest.created_at.desc())
    if status:
        q = q.where(LeaveRequest.status == status)
    rows = db.execute(q).scalars().all()
    if reviewer.role == ROLE_TEAM_LEAD:
        rows = [r for r in rows if (db.get(User, r.user_id) or User()).team_id == reviewer.team_id]
    return [leave_request_dict(r, db) for r in rows]


@router.patch("/request/{req_id}")
def decide(req_id: int, payload: LeaveDecisionIn, reviewer: User = Depends(require_min_role(ROLE_TEAM_LEAD)), db: Session = Depends(get_db)):
    req = db.get(LeaveRequest, req_id)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if payload.status not in (LEAVE_APPROVED, LEAVE_REJECTED):
        raise HTTPException(status_code=400, detail="Status must be Approved or Rejected")
    old = req.status
    req.status = payload.status
    req.reviewed_by_id = reviewer.id
    req.reviewed_at = utcnow()
    if payload.status == LEAVE_APPROVED and old != LEAVE_APPROVED:
        leave_svc.apply_approval(db, req.user_id, req.leave_type_id, req.total_days, req.start_date.year)
    db.commit()
    notif.notify(
        db, user_id=req.user_id, type=NOTIF_APPROVAL,
        title=f"Your leave request was {payload.status.lower()}",
        body=f"{req.total_days} day(s) from {req.start_date}", link="/leave",
    )
    audit.record(db, actor_id=reviewer.id, table_name="leave_requests", record_id=req.id, action="decide",
                 old={"status": old}, new={"status": payload.status})
    return leave_request_dict(req, db)
