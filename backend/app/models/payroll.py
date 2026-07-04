"""payroll_entries — per-employee, per-month manual adjustments on top of computed pay.

Net pay is computed live from salary + attendance + overtime; this table stores the Super Admin's
manual bonus/deduction/notes and a 'finalized' flag per period so payroll is repeatable.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..utils.time import utcnow


class PayrollEntry(Base):
    __tablename__ = "payroll_entries"
    __table_args__ = (UniqueConstraint("user_id", "period", name="uq_payroll_user_period"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    period: Mapped[str] = mapped_column(String(7), nullable=False, index=True)  # "YYYY-MM"
    bonus: Mapped[float] = mapped_column(Float, default=0.0)          # allowances, 13th month, etc.
    deduction: Mapped[float] = mapped_column(Float, default=0.0)      # loans, taxes, other
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    finalized: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
