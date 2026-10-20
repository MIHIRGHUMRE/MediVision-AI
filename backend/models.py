from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


class CaseRecord(Base):
    __tablename__ = "cases"
    __table_args__ = (
        Index("ix_cases_created_at_id", "created_at", "id"),
        Index("ix_cases_report_status_created_at", "report_status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    body_region: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    images: Mapped[list[dict[str, str | int]]] = mapped_column(JSON, nullable=False)
    report_status: Mapped[str | None] = mapped_column(String(24))
    indication: Mapped[str | None] = mapped_column(Text)
    findings: Mapped[str | None] = mapped_column(Text)
    impression: Mapped[str | None] = mapped_column(Text)
    reviewer: Mapped[str | None] = mapped_column(String(200))
    review_note: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(nullable=False, default=1)

    audit_events: Mapped[list[AuditEvent]] = relationship(
        back_populates="case", cascade="all, delete-orphan", order_by="AuditEvent.id"
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_events_case_id_id", "case_id", "id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    case: Mapped[CaseRecord] = relationship(back_populates="audit_events")
