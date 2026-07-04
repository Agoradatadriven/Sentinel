"""users, teams, qr_tokens."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from ..utils.time import utcnow


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    # Configurable shift window (from Zoho). "HH:MM" 24h strings, applied in PH time.
    shift_start: Mapped[str] = mapped_column(String(5), default="08:00")
    shift_end: Mapped[str] = mapped_column(String(5), default="17:00")
    break_duration_min: Mapped[int] = mapped_column(Integer, default=60)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    members: Mapped[list["User"]] = relationship(back_populates="team")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(160), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    google_sub: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    profile_pic_url: Mapped[str | None] = mapped_column(String(400), nullable=True)
    # Password login (PBKDF2). Null = no password set yet (must use Google, or admin sets one).
    password_hash: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Optional per-employee shift override; falls back to the team's shift when null.
    shift_start: Mapped[str | None] = mapped_column(String(5), nullable=True)
    shift_end: Mapped[str | None] = mapped_column(String(5), nullable=True)
    hired_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Monthly base salary (Super Admin only — never exposed via public serializers).
    monthly_salary: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    team: Mapped[Team | None] = relationship(back_populates="members")
    qr_tokens: Mapped[list["QRToken"]] = relationship(back_populates="user")

    @property
    def initials(self) -> str:
        parts = [p for p in (self.name or "").split() if p]
        return ("".join(p[0] for p in parts[:2]) or "?").upper()


class QRToken(Base):
    __tablename__ = "qr_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped[User] = relationship(back_populates="qr_tokens")
