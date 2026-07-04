"""clients — the agency's clients (bridged to Atrium via atrium_client_id)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..utils.time import utcnow


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    contact_email: Mapped[str | None] = mapped_column(String(160), nullable=True)
    # Links a Sentinel client to its Atrium workspace key (the AM bridges the two systems).
    atrium_client_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
