"""Pydantic request schemas (validation + OpenAPI). Responses are serialized as plain dicts by the
routers so we keep tight control over which fields are exposed (esp. internal vs client-facing)."""
from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field


# --- Auth ------------------------------------------------------------------
class DevLoginIn(BaseModel):
    user_id: int | None = None
    email: str | None = None


class LoginIn(BaseModel):
    email: str
    password: str


class ChangePasswordIn(BaseModel):
    current_password: str | None = None
    new_password: str


# --- Attendance ------------------------------------------------------------
class ScanIn(BaseModel):
    token: str


class EventIn(BaseModel):
    token: str
    action: str
    late_reason: str | None = None
    handover_note: str | None = None
    device: str = "kiosk"


class OfflinePunch(BaseModel):
    token: str
    action: str
    client_time: str  # ISO instant captured on the device while offline
    late_reason: str | None = None
    handover_note: str | None = None


class OfflineSyncIn(BaseModel):
    punches: list[OfflinePunch] = Field(default_factory=list)


class AttendanceRequestIn(BaseModel):
    date: date
    request_type: str  # regularization | overtime
    reason: str
    old_value: str | None = None
    new_value: str | None = None


class RequestDecisionIn(BaseModel):
    status: str  # Approved | Rejected


class AttendanceEditIn(BaseModel):
    """Super Admin manual correction of a day's summary. Times are PH 'HH:MM' (blank = clear)."""
    clock_in: str | None = None
    clock_out: str | None = None
    status: str | None = None


# --- Gym -------------------------------------------------------------------
class GymStartIn(BaseModel):
    day_type: str = "Custom"


class GymEndIn(BaseModel):
    notes: str | None = None


class GymAdminEditIn(BaseModel):
    """Super Admin correction of any user's gym session."""
    day_type: str | None = None
    status: str | None = None
    notes: str | None = None


class GymSetIn(BaseModel):
    set: int
    kg: float = 0
    reps: int = 0
    type: str = "Normal"
    done: bool = True
    pr: bool = False


class GymExerciseIn(BaseModel):
    exercise_name: str
    muscle_group: str | None = None
    weight_value: float = 0
    weight_unit: str = "kg"
    sets: int = 0
    reps: int = 0
    set_type: str = "Normal"
    sets_detail: list[GymSetIn] = Field(default_factory=list)
    duration_minutes: int = 0
    notes: str | None = None


# --- Tasks -----------------------------------------------------------------
class ChecklistItem(BaseModel):
    text: str
    done: bool = False


class TaskCreateIn(BaseModel):
    title: str
    description: str | None = None
    client_id: int | None = None
    service_box_id: int | None = None
    campaign: str | None = None
    content_type: str | None = None
    assigned_team_id: int | None = None
    assigned_to_id: int | None = None
    priority: str = "Medium"
    status: str = "To Do"
    due_date: date | None = None
    time_span_hours: float | None = None
    labels: list[str] = Field(default_factory=list)
    checklist: list[ChecklistItem] = Field(default_factory=list)
    deliverable_url: str | None = None
    internal_notes: str | None = None
    client_facing_notes: str | None = None


class TaskUpdateIn(BaseModel):
    title: str | None = None
    description: str | None = None
    client_id: int | None = None
    service_box_id: int | None = None
    campaign: str | None = None
    content_type: str | None = None
    assigned_team_id: int | None = None
    assigned_to_id: int | None = None
    due_date: date | None = None
    time_span_hours: float | None = None
    actual_hours: float | None = None
    progress: int | None = None
    finished_date: date | None = None
    labels: list[str] | None = None
    checklist: list[ChecklistItem] | None = None
    deliverable_url: str | None = None
    internal_notes: str | None = None
    client_facing_notes: str | None = None
    atrium_visible: bool | None = None


class TaskStatusIn(BaseModel):
    status: str


class TaskPriorityIn(BaseModel):
    priority: str


class CommentIn(BaseModel):
    body: str
    attachments: list[dict[str, Any]] = Field(default_factory=list)


# --- Task Tracker v0.3: service boxes & sub-objects ------------------------
class BoxCreateIn(BaseModel):
    client_id: int
    service_line: str
    team_leader_id: int | None = None
    run_length_days: int | None = None
    notes: str | None = None


class BoxUpdateIn(BaseModel):
    team_leader_id: int | None = None
    is_paid: bool | None = None
    ads_running: bool | None = None
    started_date: date | None = None
    approved_date: date | None = None
    client_confirmed_date: date | None = None
    launch_date: date | None = None
    run_length_days: int | None = None
    notes: str | None = None


class StageMoveIn(BaseModel):
    stage: str
    reason: str | None = None  # required when moving backward


class RecurringCreateIn(BaseModel):
    title: str
    cadence: str  # Daily | Weekly | Monthly
    assignee_id: int | None = None
    time_span_hours: float = 1.0
    start_date: date
    end_date: date | None = None


class RecurringUpdateIn(BaseModel):
    title: str | None = None
    cadence: str | None = None
    assignee_id: int | None = None
    time_span_hours: float | None = None
    end_date: date | None = None
    active: bool | None = None


class OccurrenceCheckIn(BaseModel):
    occurrence_date: date
    done: bool = True
    actual_hours: float | None = None


class ReconCreateIn(BaseModel):
    trigger_type: str
    description: str | None = None
    owner_id: int | None = None


class ReconUpdateIn(BaseModel):
    trigger_type: str | None = None
    description: str | None = None
    owner_id: int | None = None
    status: str | None = None
    resolution: str | None = None


class RevisionCreateIn(BaseModel):
    what_changed: str | None = None
    ball_with: str = "us"


class RevisionUpdateIn(BaseModel):
    what_changed: str | None = None
    ball_with: str | None = None
    approval_outcome: str | None = None


class ClientCreateIn(BaseModel):
    name: str
    contact_email: str | None = None
    atrium_client_id: str | None = None
    color: str | None = None


class ClientUpdateIn(BaseModel):
    name: str | None = None
    contact_email: str | None = None
    atrium_client_id: str | None = None
    color: str | None = None


# --- People ----------------------------------------------------------------
class PersonCreateIn(BaseModel):
    name: str
    email: str
    role: str = "employee"
    team_id: int | None = None
    phone: str | None = None
    hired_date: date | None = None
    shift_start: str | None = None
    shift_end: str | None = None
    password: str | None = None  # optional initial password


class PersonUpdateIn(BaseModel):
    name: str | None = None
    email: str | None = None
    role: str | None = None
    team_id: int | None = None
    phone: str | None = None
    hired_date: date | None = None
    shift_start: str | None = None
    shift_end: str | None = None
    is_active: bool | None = None
    password: str | None = None  # admin set/reset (blank/None = leave unchanged)


# --- Leave -----------------------------------------------------------------
class LeaveRequestIn(BaseModel):
    leave_type_id: int
    start_date: date
    end_date: date
    reason: str


class LeaveDecisionIn(BaseModel):
    status: str  # Approved | Rejected


# --- Admin -----------------------------------------------------------------
class SettingsIn(BaseModel):
    settings: dict[str, str]


class AnnouncementIn(BaseModel):
    title: str
    body: str | None = None


# --- Payroll (Super Admin only) --------------------------------------------
class SalaryIn(BaseModel):
    monthly_salary: float = Field(ge=0)


class PayrollAdjustIn(BaseModel):
    period: str  # "YYYY-MM"
    bonus: float = Field(default=0, ge=0)
    deduction: float = Field(default=0, ge=0)
    note: str | None = None


class PayrollFinalizeIn(BaseModel):
    period: str
    finalized: bool = True
