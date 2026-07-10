import enum

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, Time
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class OAuthAccount(str, enum.Enum):
    """Which Google account a token belongs to."""
    work = "work"
    personal = "personal"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    display_name = Column(String(255))
    timezone = Column(String(64), nullable=False, default="America/Chicago")

    # Work account OAuth tokens (stored encrypted — see services/crypto.py TODO)
    work_google_id = Column(String(255), unique=True, nullable=True)
    work_access_token = Column(Text, nullable=True)
    work_refresh_token = Column(Text, nullable=True)
    work_token_expiry = Column(DateTime(timezone=True), nullable=True)

    # Personal account OAuth tokens
    personal_google_id = Column(String(255), unique=True, nullable=True)
    personal_access_token = Column(Text, nullable=True)
    personal_refresh_token = Column(Text, nullable=True)
    personal_token_expiry = Column(DateTime(timezone=True), nullable=True)

    # Scheduling preferences (override app config defaults)
    work_start_hour = Column(Integer, nullable=False, default=8, server_default="8")
    work_end_hour = Column(Integer, nullable=False, default=17, server_default="17")
    hard_start_hour = Column(Integer, nullable=False, default=7, server_default="7")
    hard_end_hour = Column(Integer, nullable=False, default=22, server_default="22")
    buffer_minutes = Column(Integer, nullable=False, default=30, server_default="30")
    # User-selected calendar IDs (null = fall back to app config env vars)
    work_calendar_id = Column(String(255), nullable=True)
    personal_calendar_id = Column(String(255), nullable=True)

    # Weekend scheduling preferences
    allow_work_on_weekends = Column(Boolean, nullable=False, default=False, server_default="false")
    allow_personal_on_weekends = Column(Boolean, nullable=False, default=True, server_default="true")
    # Per-day weekend hour ranges (null = that day is disabled)
    work_saturday_start_time = Column(Time, nullable=True)
    work_saturday_end_time = Column(Time, nullable=True)
    work_sunday_start_time = Column(Time, nullable=True)
    work_sunday_end_time = Column(Time, nullable=True)
    personal_saturday_start_time = Column(Time, nullable=True)
    personal_saturday_end_time = Column(Time, nullable=True)
    personal_sunday_start_time = Column(Time, nullable=True)
    personal_sunday_end_time = Column(Time, nullable=True)

    # Synthesis time: 15-min buffer auto-created after multi-person meetings
    synthesis_enabled = Column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    synthesis_duration_minutes = Column(
        Integer, nullable=False, default=15, server_default="15"
    )
    # Comma-separated list of email addresses that count as "me" — a meeting
    # only qualifies for synthesis if it has an attendee outside this set.
    synthesis_self_emails = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    tasks = relationship(
        "Task", back_populates="user", lazy="raise", cascade="all, delete-orphan"
    )

    @property
    def personal_account_connected(self) -> bool:
        return self.personal_google_id is not None

    @property
    def synthesis_self_email_set(self) -> set[str]:
        """
        Lowercased set of email addresses that represent the user. A meeting
        needs at least one attendee outside this set to earn a synthesis block.
        Always includes the primary login email; extended by
        synthesis_self_emails (comma-separated).
        """
        emails: set[str] = set()
        if self.email:
            emails.add(self.email.strip().lower())
        if self.synthesis_self_emails:
            for raw in self.synthesis_self_emails.split(","):
                cleaned = raw.strip().lower()
                if cleaned:
                    emails.add(cleaned)
        return emails
