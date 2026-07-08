"""Task Tracker v0.3 — service boxes and their sub-objects.

The board is a matrix: Client rows × Stage columns. Each cell holds a **ServiceBox** (one of the
4 service lines, led by a Team Leader) that slides rightward through the stages. Hanging off a box:

    service_boxes        -> the box itself (client × service line × stage)
    stage_transitions    -> append-only log of every stage move (who/when/why)
    recurring_templates  -> a recurring task definition (spawns dated occurrences lazily)
    task_occurrences     -> SPARSE completion log: a row exists only once an occurrence is done
    reconciliation_cases -> a separate object (Launched); an open one blocks Closing
    box_revisions        -> the In Process "Approval track" (revision rounds + approval outcome)

Single (one-off) tasks are the existing ``tasks`` table, linked to a box via ``service_box_id``.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..constants import (
    APPROVAL_PENDING,
    BALL_US,
    RECON_OPEN,
    STAGE_IN_PROCESS,
)
from ..database import Base
from ..utils.time import utcnow


class ServiceBox(Base):
    __tablename__ = "service_boxes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), nullable=False, index=True)
    service_line: Mapped[str] = mapped_column(String(40), nullable=False)  # SERVICE_LINES
    # The Team Leader owns the box and is the auto-receiver on every task inside it.
    team_leader_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    stage: Mapped[str] = mapped_column(String(24), default=STAGE_IN_PROCESS, index=True)

    # Guard 1: a box cannot reach Launched unless it is marked paid.
    is_paid: Mapped[bool] = mapped_column(Boolean, default=False)
    ads_running: Mapped[bool] = mapped_column(Boolean, default=False)  # billing indicator (Launched)

    # Milestone dates surfaced in the stacked stage tabs.
    started_date: Mapped[date | None] = mapped_column(Date, nullable=True)          # In Process began
    approved_date: Mapped[date | None] = mapped_column(Date, nullable=True)         # proposal approved
    client_confirmed_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # start date confirmed
    launch_date: Mapped[date | None] = mapped_column(Date, nullable=True)           # went live
    closed_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    run_length_days: Mapped[int | None] = mapped_column(Integer, nullable=True)     # contract length of run

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    transitions: Mapped[list["StageTransition"]] = relationship(
        back_populates="box", cascade="all, delete-orphan"
    )
    templates: Mapped[list["RecurringTemplate"]] = relationship(
        back_populates="box", cascade="all, delete-orphan"
    )
    reconciliations: Mapped[list["ReconciliationCase"]] = relationship(
        back_populates="box", cascade="all, delete-orphan"
    )
    revisions: Mapped[list["BoxRevision"]] = relationship(
        back_populates="box", cascade="all, delete-orphan"
    )


class StageTransition(Base):
    __tablename__ = "stage_transitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    box_id: Mapped[int] = mapped_column(ForeignKey("service_boxes.id"), nullable=False, index=True)
    from_stage: Mapped[str | None] = mapped_column(String(24), nullable=True)
    to_stage: Mapped[str] = mapped_column(String(24), nullable=False)
    is_backward: Mapped[bool] = mapped_column(Boolean, default=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)  # required for backward moves
    moved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    box: Mapped[ServiceBox] = relationship(back_populates="transitions")


class RecurringTemplate(Base):
    __tablename__ = "recurring_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    box_id: Mapped[int] = mapped_column(ForeignKey("service_boxes.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    cadence: Mapped[str] = mapped_column(String(16), nullable=False)  # Daily | Weekly | Monthly
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    time_span_hours: Mapped[float] = mapped_column(Float, default=1.0)  # allotted hrs per occurrence
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # null = runs for contract length
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    box: Mapped[ServiceBox] = relationship(back_populates="templates")
    occurrences: Mapped[list["TaskOccurrence"]] = relationship(
        back_populates="template", cascade="all, delete-orphan"
    )


class TaskOccurrence(Base):
    """SPARSE log — a row is created only when an occurrence is checked off (done).

    Expected occurrences are computed on the fly from the template's cadence, so a 6-month daily
    task never materializes ~180 empty rows. A past expected date with no row here == missed.
    """
    __tablename__ = "task_occurrences"
    __table_args__ = (UniqueConstraint("template_id", "occurrence_date", name="uq_occ_template_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("recurring_templates.id"), nullable=False, index=True)
    occurrence_date: Mapped[date] = mapped_column(Date, nullable=False)
    done_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    done_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    actual_hours: Mapped[float | None] = mapped_column(Float, nullable=True)

    template: Mapped[RecurringTemplate] = relationship(back_populates="occurrences")


class ReconciliationCase(Base):
    __tablename__ = "reconciliation_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    box_id: Mapped[int] = mapped_column(ForeignKey("service_boxes.id"), nullable=False, index=True)
    trigger_type: Mapped[str] = mapped_column(String(80), nullable=False)  # RECON_TRIGGERS
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default=RECON_OPEN)  # Open | Investigating | Resolved
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    box: Mapped[ServiceBox] = relationship(back_populates="reconciliations")


class BoxRevision(Base):
    """A revision round in the In Process 'Approval track' (separate from the defined task list)."""
    __tablename__ = "box_revisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    box_id: Mapped[int] = mapped_column(ForeignKey("service_boxes.id"), nullable=False, index=True)
    round_no: Mapped[int] = mapped_column(Integer, default=1)
    what_changed: Mapped[str | None] = mapped_column(Text, nullable=True)
    ball_with: Mapped[str] = mapped_column(String(10), default=BALL_US)  # us | client
    approval_outcome: Mapped[str] = mapped_column(String(24), default=APPROVAL_PENDING)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    box: Mapped[ServiceBox] = relationship(back_populates="revisions")
