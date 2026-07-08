"""Model → dict serializers. Central so field exposure (internal vs client-facing) stays consistent.

Datetimes are emitted as ISO strings in Manila time so the frontend can display them directly while
the DB keeps UTC.
"""
from __future__ import annotations

import json
from datetime import date, datetime

from sqlalchemy.orm import Session

from .constants import BOX_STAGES, RECON_RESOLVED, ROLE_LABELS, TASK_COMPLETED
from .models import (
    AttendanceRequest,
    BoxRevision,
    Client,
    DailyAttendanceSummary,
    GymLog,
    LeaveBalance,
    LeaveRequest,
    LeaveType,
    Notification,
    RecurringTemplate,
    ReconciliationCase,
    ServiceBox,
    StageTransition,
    Task,
    TaskComment,
    TaskHistory,
    TaskOccurrence,
    Team,
    User,
)
from .utils.time import to_ph, today_ph


def _iso(dt: datetime | None) -> str | None:
    return to_ph(dt).isoformat() if dt else None


def _d(d: date | None) -> str | None:
    return d.isoformat() if d else None


def _loads(raw: str | None, default):
    try:
        return json.loads(raw) if raw else default
    except (ValueError, TypeError):
        return default


def user_public(u: User | None) -> dict | None:
    if not u:
        return None
    return {
        "id": u.id,
        "name": u.name,
        "email": u.email,
        "role": u.role,
        "role_label": ROLE_LABELS.get(u.role, u.role),
        "team_id": u.team_id,
        "initials": u.initials,
        "profile_pic_url": u.profile_pic_url,
    }


def user_full(u: User, team: Team | None = None) -> dict:
    d = user_public(u) or {}
    d.update(
        {
            "phone": u.phone,
            "is_active": u.is_active,
            "hired_date": _d(u.hired_date),
            "shift_start": u.shift_start,
            "shift_end": u.shift_end,
            "team_name": team.name if team else None,
        }
    )
    return d


def team_dict(t: Team) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "shift_start": t.shift_start,
        "shift_end": t.shift_end,
        "break_duration_min": t.break_duration_min,
    }


def client_dict(c: Client) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "contact_email": c.contact_email,
        "atrium_client_id": c.atrium_client_id,
    }


def task_card(t: Task, db: Session) -> dict:
    """Compact shape for the Kanban board."""
    comment_count = len(t.comments)
    attach_count = sum(len(_loads(c.attachments_json, [])) for c in t.comments)
    client = db.get(Client, t.client_id) if t.client_id else None
    assignee = db.get(User, t.assigned_to_id) if t.assigned_to_id else None
    checklist = _loads(t.checklist_json, [])
    done = sum(1 for i in checklist if i.get("done"))
    on_time = None
    if t.status == TASK_COMPLETED and t.finished_date and t.due_date:
        on_time = t.finished_date <= t.due_date
    return {
        "id": t.id,
        "title": t.title,
        "status": t.status,
        "priority": t.priority,
        "due_date": _d(t.due_date),
        "finished_date": _d(t.finished_date),
        "progress": t.progress or 0,
        "time_span_hours": t.time_span_hours,
        "actual_hours": t.actual_hours,
        "on_time": on_time,
        "labels": _loads(t.labels_json, []),
        "client_id": t.client_id,
        "client_name": client.name if client else None,
        "service_box_id": t.service_box_id,
        "assigned_to_id": t.assigned_to_id,
        "assignee": user_public(assignee),
        "assigned_team_id": t.assigned_team_id,
        "comment_count": comment_count,
        "attachment_count": attach_count,
        "checklist_total": len(checklist),
        "checklist_done": done,
        "atrium_visible": t.atrium_visible,
    }


def task_detail(t: Task, db: Session) -> dict:
    """Full task incl. internal fields (Sentinel users are all internal staff)."""
    d = task_card(t, db)
    am = db.get(User, t.account_manager_id) if t.account_manager_id else None
    team = db.get(Team, t.assigned_team_id) if t.assigned_team_id else None
    box = db.get(ServiceBox, t.service_box_id) if t.service_box_id else None
    receiver = db.get(User, box.team_leader_id) if box and box.team_leader_id else None
    d.update(
        {
            "description": t.description,
            "campaign": t.campaign,
            "content_type": t.content_type,
            "account_manager_id": t.account_manager_id,
            "account_manager": user_public(am),
            "receiver": user_public(receiver),  # auto = the box's team leader
            "assigned_team_name": team.name if team else None,
            "checklist": _loads(t.checklist_json, []),
            "deliverable_url": t.deliverable_url,
            "internal_notes": t.internal_notes,
            "client_facing_notes": t.client_facing_notes,
            "comments": [comment_dict(c, db) for c in sorted(t.comments, key=lambda c: c.id)],
            "history": [history_dict(h, db) for h in sorted(t.history, key=lambda h: h.id, reverse=True)],
            "created_at": _iso(t.created_at),
            "updated_at": _iso(t.updated_at),
        }
    )
    return d


def atrium_payload(t: Task, db: Session) -> dict:
    """ONLY client-facing fields — this is what may cross the bridge into Atrium."""
    client = db.get(Client, t.client_id) if t.client_id else None
    return {
        "task_id": t.id,
        "client": client.name if client else None,
        "campaign": t.campaign,
        "content_type": t.content_type,
        "title": t.title,
        "due_date": _d(t.due_date),
        "labels": _loads(t.labels_json, []),
        "deliverable_url": t.deliverable_url,
        "client_notes": t.client_facing_notes,
    }


def comment_dict(c: TaskComment, db: Session) -> dict:
    return {
        "id": c.id,
        "author": user_public(db.get(User, c.author_id)),
        "body": c.body,
        "attachments": _loads(c.attachments_json, []),
        "created_at": _iso(c.created_at),
    }


def history_dict(h: TaskHistory, db: Session) -> dict:
    return {
        "id": h.id,
        "actor": user_public(db.get(User, h.changed_by_id)) if h.changed_by_id else None,
        "field": h.field_changed,
        "old_value": h.old_value,
        "new_value": h.new_value,
        "changed_at": _iso(h.changed_at),
    }


def summary_dict(s: DailyAttendanceSummary, user: User | None = None) -> dict:
    return {
        "id": s.id,
        "user_id": s.user_id,
        "user": user_public(user) if user else None,
        "date": _d(s.date),
        "clock_in": _iso(s.clock_in),
        "clock_out": _iso(s.clock_out),
        "break_duration_min": s.break_duration_min,
        "total_work_hours": s.total_work_hours,
        "status": s.status,
        "handover_note": s.handover_note,
    }


def attendance_request_dict(r: AttendanceRequest, db: Session) -> dict:
    return {
        "id": r.id,
        "user": user_public(db.get(User, r.user_id)),
        "date": _d(r.date),
        "request_type": r.request_type,
        "reason": r.reason,
        "old_value": r.old_value,
        "new_value": r.new_value,
        "status": r.status,
        "created_at": _iso(r.created_at),
    }


def gym_log_dict(g: GymLog, db: Session, with_exercises: bool = False) -> dict:
    d = {
        "id": g.id,
        "user_id": g.user_id,
        "user": user_public(db.get(User, g.user_id)),
        "date": _d(g.date),
        "day_type": g.day_type,
        "start_time": _iso(g.start_time),
        "end_time": _iso(g.end_time),
        "duration_minutes": g.duration_minutes,
        "status": g.status,
        "notes": g.notes,
        "exercise_count": len(g.exercises),
    }
    if with_exercises:
        d["exercises"] = [
            {
                "id": e.id,
                "exercise_name": e.exercise_name,
                "muscle_group": e.muscle_group,
                "weight_value": e.weight_value,
                "weight_unit": e.weight_unit,
                "sets": e.sets,
                "reps": e.reps,
                "set_type": e.set_type,
                "sets_detail": _loads(e.sets_json, []),
                "duration_minutes": e.duration_minutes,
                "notes": e.notes,
            }
            for e in g.exercises
        ]
    return d


def leave_type_dict(lt: LeaveType) -> dict:
    return {
        "id": lt.id,
        "name": lt.name,
        "annual_balance": lt.annual_balance,
        "accrual_type": lt.accrual_type,
        "requires_approval": lt.requires_approval,
        "carry_over_days": lt.carry_over_days,
    }


def leave_balance_dict(b: LeaveBalance, lt: LeaveType | None) -> dict:
    return {
        "id": b.id,
        "leave_type_id": b.leave_type_id,
        "leave_type": lt.name if lt else None,
        "year": b.year,
        "used": b.used,
        "remaining": b.remaining,
        "unlimited": bool(lt and lt.annual_balance < 0),
    }


def leave_request_dict(r: LeaveRequest, db: Session) -> dict:
    lt = db.get(LeaveType, r.leave_type_id)
    return {
        "id": r.id,
        "user": user_public(db.get(User, r.user_id)),
        "leave_type": lt.name if lt else None,
        "leave_type_id": r.leave_type_id,
        "start_date": _d(r.start_date),
        "end_date": _d(r.end_date),
        "total_days": r.total_days,
        "reason": r.reason,
        "status": r.status,
        "created_at": _iso(r.created_at),
    }


def notification_dict(n: Notification) -> dict:
    return {
        "id": n.id,
        "type": n.type,
        "title": n.title,
        "body": n.body,
        "link": n.link,
        "is_read": n.is_read,
        "created_at": _iso(n.created_at),
    }


# ============================================================================
# Task Tracker v0.3 — service boxes, recurring occurrences, reconciliation
# ============================================================================
from datetime import timedelta

AT_RISK_DAYS = 3       # flag "at risk" when due within N days
AT_RISK_PROGRESS = 60  # ...and progress below X%
STRIP_PAST = 20        # adherence-strip window: most-recent N past/today occurrences
STRIP_FUTURE = 5       # ...plus this many upcoming


def _add_month(d: date) -> date:
    """Same day-of-month next month, clamped to the month's length."""
    y, m = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    for day in (d.day, 28, 29, 30, 31):
        try:
            return date(y, m, min(day, 31))
        except ValueError:
            continue
    return date(y, m, 28)


def _expected_dates(cadence: str, start: date, end_cap: date) -> list[date]:
    """All scheduled occurrence dates from ``start`` through ``end_cap`` (inclusive).

    Note: every calendar day is scheduled for Daily — weekend/holiday skipping is a pending
    business decision (§12.A2), and is the single place it would be applied.
    """
    if not start or end_cap < start:
        return []
    out: list[date] = []
    d = start
    guard = 0
    while d <= end_cap and guard < 4000:
        out.append(d)
        guard += 1
        if cadence == "Daily":
            d = d + timedelta(days=1)
        elif cadence == "Weekly":
            d = d + timedelta(days=7)
        else:  # Monthly
            d = _add_month(d)
    return out


def _template_adherence(tpl: RecurringTemplate, today: date) -> tuple[int, int, int]:
    """Return (resolved, done, missed).

    A "resolved" occurrence is one that has already come due: any scheduled date strictly before
    today, plus today itself IF it has been ticked. Today-not-yet-done is pending (neither counted
    against adherence nor as missed), so ticking today's box immediately improves the number.
    """
    done_dates = {o.occurrence_date for o in tpl.occurrences}
    end_cap = tpl.end_date if (tpl.end_date and tpl.end_date < today) else today
    expected = _expected_dates(tpl.cadence, tpl.start_date, end_cap)
    resolved = [d for d in expected if d < today or d in done_dates]
    done = [d for d in resolved if d in done_dates]
    missed = [d for d in resolved if d not in done_dates]
    return len(resolved), len(done), len(missed)


def recurring_dict(tpl: RecurringTemplate, db: Session, today: date | None = None) -> dict:
    today = today or today_ph()
    assignee = db.get(User, tpl.assignee_id) if tpl.assignee_id else None
    done_dates = {o.occurrence_date for o in tpl.occurrences}

    end_cap = tpl.end_date if (tpl.end_date and tpl.end_date < today) else today
    expected = _expected_dates(tpl.cadence, tpl.start_date, end_cap)
    resolved, done_count, missed_count = _template_adherence(tpl, today)
    adherence = round(100 * done_count / resolved) if resolved else 100

    # Rolling strip: last STRIP_PAST scheduled (incl. today) + a few upcoming.
    upto_today = [d for d in expected if d <= today][-STRIP_PAST:]
    future = _expected_dates(
        tpl.cadence, tpl.start_date, tpl.end_date or (today + timedelta(days=400))
    )
    future = [d for d in future if d > today][:STRIP_FUTURE]

    def _state(d: date) -> str:
        if d in done_dates:
            return "done"
        if d == today:
            return "today"
        return "missed" if d < today else "upcoming"

    strip = [{"date": _d(d), "state": _state(d)} for d in (upto_today + future)]

    # The current-period occurrence to tick off (most recent scheduled date <= today).
    current = [d for d in expected if d <= today]
    due = None
    if current and tpl.active:
        cd = current[-1]
        due = {"occurrence_date": _d(cd), "done": cd in done_dates}

    return {
        "id": tpl.id,
        "box_id": tpl.box_id,
        "title": tpl.title,
        "cadence": tpl.cadence,
        "assignee_id": tpl.assignee_id,
        "assignee": user_public(assignee),
        "time_span_hours": tpl.time_span_hours,
        "start_date": _d(tpl.start_date),
        "end_date": _d(tpl.end_date),
        "active": tpl.active,
        "expected_total": len(expected),
        "done_total": done_count,
        "missed_total": missed_count,
        "adherence_pct": adherence,
        "strip": strip,
        "due": due,
    }


def recon_dict(r: ReconciliationCase, db: Session) -> dict:
    return {
        "id": r.id,
        "box_id": r.box_id,
        "trigger_type": r.trigger_type,
        "description": r.description,
        "owner_id": r.owner_id,
        "owner": user_public(db.get(User, r.owner_id)) if r.owner_id else None,
        "status": r.status,
        "resolution": r.resolution,
        "opened_at": _iso(r.opened_at),
        "resolved_at": _iso(r.resolved_at),
        "is_open": r.status != RECON_RESOLVED,
    }


def revision_dict(r: BoxRevision) -> dict:
    return {
        "id": r.id,
        "box_id": r.box_id,
        "round_no": r.round_no,
        "what_changed": r.what_changed,
        "ball_with": r.ball_with,
        "approval_outcome": r.approval_outcome,
        "created_at": _iso(r.created_at),
    }


def transition_dict(t: StageTransition, db: Session) -> dict:
    return {
        "id": t.id,
        "from_stage": t.from_stage,
        "to_stage": t.to_stage,
        "is_backward": t.is_backward,
        "reason": t.reason,
        "moved_by": user_public(db.get(User, t.moved_by_id)) if t.moved_by_id else None,
        "created_at": _iso(t.created_at),
    }


def _box_tasks(box_id: int, db: Session) -> list[Task]:
    from sqlalchemy import select
    return list(db.execute(select(Task).where(Task.service_box_id == box_id)).scalars().all())


def box_card(box: ServiceBox, db: Session, today: date | None = None) -> dict:
    """Compact box shape for the matrix board (with the data the stacked tabs need)."""
    today = today or today_ph()
    client = db.get(Client, box.client_id)
    leader = db.get(User, box.team_leader_id) if box.team_leader_id else None
    tasks = _box_tasks(box.id, db)
    open_tasks = [t for t in tasks if t.status != TASK_COMPLETED]
    overdue = [t for t in open_tasks if t.due_date and t.due_date < today]
    at_risk = [
        t for t in open_tasks
        if t.due_date and 0 <= (t.due_date - today).days <= AT_RISK_DAYS and (t.progress or 0) < AT_RISK_PROGRESS
    ]
    open_recon = [r for r in box.reconciliations if r.status != RECON_RESOLVED]
    missed_occ = 0
    for tpl in box.templates:
        if tpl.active:
            missed_occ += recurring_dict(tpl, db, today)["missed_total"]

    run_day = None
    if box.launch_date:
        run_day = (min(today, box.closed_date or today) - box.launch_date).days + 1

    return {
        "id": box.id,
        "client_id": box.client_id,
        "client_name": client.name if client else None,
        "service_line": box.service_line,
        "stage": box.stage,
        "team_leader_id": box.team_leader_id,
        "team_leader": user_public(leader),
        "is_paid": box.is_paid,
        "ads_running": box.ads_running,
        "started_date": _d(box.started_date),
        "approved_date": _d(box.approved_date),
        "client_confirmed_date": _d(box.client_confirmed_date),
        "launch_date": _d(box.launch_date),
        "closed_date": _d(box.closed_date),
        "run_length_days": box.run_length_days,
        "run_day": run_day,
        "revisions_count": len(box.revisions),
        "task_total": len(tasks),
        "task_open": len(open_tasks),
        "overdue_count": len(overdue),
        "at_risk_count": len(at_risk),
        "missed_occurrences": missed_occ,
        "open_recon_count": len(open_recon),
    }


def box_detail(box: ServiceBox, db: Session, today: date | None = None) -> dict:
    today = today or today_ph()
    d = box_card(box, db, today)
    tasks = _box_tasks(box.id, db)
    unsolutioned = [t for t in tasks if t.status != TASK_COMPLETED]
    open_recon = [r for r in box.reconciliations if r.status != RECON_RESOLVED]
    d.update(
        {
            "notes": box.notes,
            "tasks": [task_card(t, db) for t in sorted(tasks, key=lambda t: t.id, reverse=True)],
            "recurring": [
                recurring_dict(t, db, today)
                for t in sorted(box.templates, key=lambda t: t.id)
            ],
            "reconciliations": [
                recon_dict(r, db) for r in sorted(box.reconciliations, key=lambda r: r.id, reverse=True)
            ],
            "revisions": [revision_dict(r) for r in sorted(box.revisions, key=lambda r: r.round_no)],
            "transitions": [
                transition_dict(t, db) for t in sorted(box.transitions, key=lambda t: t.id, reverse=True)
            ],
            # Stage guards, surfaced so the UI can explain WHY a move is blocked.
            "guards": {
                "can_launch": box.is_paid,
                "can_close": not unsolutioned and not open_recon,
                "unsolutioned_tasks": len(unsolutioned),
                "open_reconciliations": len(open_recon),
            },
            "stage_index": BOX_STAGES.index(box.stage) if box.stage in BOX_STAGES else 0,
        }
    )
    return d


def performance_row(user: User, db: Session, today: date | None = None) -> dict:
    """Personnel performance. RANKED on objective, dated signals (on-time + adherence);
    hours are reported but informational (self-reported → not trusted for ranking)."""
    from sqlalchemy import select

    today = today or today_ph()
    tasks = list(db.execute(select(Task).where(Task.assigned_to_id == user.id)).scalars().all())
    finished = [t for t in tasks if t.status == TASK_COMPLETED and t.finished_date and t.due_date]
    on_time = [t for t in finished if t.finished_date <= t.due_date]
    on_time_rate = round(100 * len(on_time) / len(finished)) if finished else 100
    open_tasks = [t for t in tasks if t.status != TASK_COMPLETED]
    overdue = [t for t in open_tasks if t.due_date and t.due_date < today]

    # Adherence across recurring templates assigned to this user.
    tpls = list(db.execute(select(RecurringTemplate).where(RecurringTemplate.assignee_id == user.id)).scalars().all())
    resolved_total = done_total = 0
    for tpl in tpls:
        resolved, done, _missed = _template_adherence(tpl, today)
        resolved_total += resolved
        done_total += done
    adherence = round(100 * done_total / resolved_total) if resolved_total else 100

    # Hours (informational): average allotted vs actual over completed tasks that recorded both.
    with_hours = [t for t in finished if t.time_span_hours and t.actual_hours]
    avg_allot = round(sum(t.time_span_hours for t in with_hours) / len(with_hours), 1) if with_hours else None
    avg_actual = round(sum(t.actual_hours for t in with_hours) / len(with_hours), 1) if with_hours else None

    # "Score" ranks on objective, dated signals only (on-time + adherence). Someone with no
    # finished tasks and no resolved occurrences has NO signal — score is null so they rank last
    # rather than sitting at a flattering default 100.
    has_signal = bool(finished) or resolved_total > 0
    score = round(0.6 * on_time_rate + 0.4 * adherence) if has_signal else None
    return {
        "user": user_public(user),
        "on_time_rate": on_time_rate if finished else None,
        "adherence_pct": adherence if resolved_total else None,
        "open_count": len(open_tasks),
        "overdue_count": len(overdue),
        "finished_count": len(finished),
        "avg_allotted_hours": avg_allot,
        "avg_actual_hours": avg_actual,
        "score": score,
    }
