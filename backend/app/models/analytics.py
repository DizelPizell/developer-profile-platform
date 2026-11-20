import uuid
from datetime import date

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

EVENT_TYPES = ("PROFILE_VIEW", "PROJECT_VIEW", "DEMO_CLICK", "GITHUB_CLICK", "CONTACT_CLICK")
# Events about one project; GITHUB_CLICK is either: a repository or the profile's GitHub.
PROJECT_EVENTS = ("PROJECT_VIEW", "DEMO_CLICK")
PROFILE_EVENTS = ("PROFILE_VIEW", "CONTACT_CLICK")


def _listed(kinds: tuple[str, ...]) -> str:
    return ", ".join(f"'{kind}'" for kind in kinds)


class AnalyticsDailyCount(Base):
    """Events of one type for a profile or a project in one UTC day; nothing about
    the visitor (ADR-0029)."""

    __tablename__ = "analytics_daily_counts"
    __table_args__ = (
        CheckConstraint(f"event_type IN ({_listed(EVENT_TYPES)})", name="ck_analytics_event_type"),
        CheckConstraint(
            f"(event_type NOT IN ({_listed(PROJECT_EVENTS)}) OR project_id IS NOT NULL) "
            f"AND (event_type NOT IN ({_listed(PROFILE_EVENTS)}) OR project_id IS NULL)",
            name="ck_analytics_project",
        ),
        CheckConstraint("count > 0", name="ck_analytics_count"),
        UniqueConstraint(
            "profile_id",
            "project_id",
            "event_type",
            "day",
            name="uq_analytics_daily_counts",
            postgresql_nulls_not_distinct=True,
        ),
        # The unique index leads with profile_id; project_id needs its own for the cascade.
        Index("ix_analytics_daily_counts_project_id", "project_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(20), nullable=False)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False)
