"""
Pydantic request/response schemas for the tasks API.

AISuggestion and ParseRequest/ParseResponse are also used by ai_service.py —
import them from there to keep a single source of truth.
"""

from datetime import date, datetime
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from app.models.task import TaskStatus, TaskType
from app.services.ai_service import AISuggestion, ParseRequest, ParseResponse

__all__ = [
    "TaskCreate",
    "TaskConfirm",
    "TaskUpdate",
    "TaskRead",
    "TaskBlockInfo",
    "ReorderRequest",
    "CompleteRequest",
    "MoreWorkRequest",
    "MoreWorkSuggestion",
    "RescheduleAllOverdueResponse",
    "BlockDoneRequest",
    "ParseRequest",
    "ParseResponse",
    "AISuggestion",
]


class TaskBlockInfo(BaseModel):
    """A single scheduled calendar block belonging to a task."""
    id: int
    start_at: datetime
    end_at: datetime

    model_config = {"from_attributes": True}


class TaskCreate(BaseModel):
    """
    Payload for creating a confirmed task.
    The frontend sends this after the user accepts (and optionally edits) the AI suggestion.
    """
    title: str = Field(min_length=1, max_length=512)
    type: TaskType
    priority: Optional[int] = None          # null = append to end of backlog
    estimated_duration_minutes: Optional[int] = Field(default=None, ge=15, le=480)
    optional_user_estimate: Optional[str] = None
    optional_deadline: Optional[date] = None
    is_off_hours_allowed: bool = False
    is_workday_allowed: bool = False
    no_weekends: bool = False
    description: Optional[str] = None
    part_of_task_id: Optional[int] = None
    # AI suggestion metadata logged alongside the task
    ai_confidence: Optional[Literal["high", "medium", "low"]] = None
    ai_keywords: Optional[List[str]] = None


class TaskUpdate(BaseModel):
    """Partial update — all fields optional."""
    title: Optional[str] = Field(default=None, min_length=1, max_length=512)
    type: Optional[TaskType] = None
    priority: Optional[int] = None
    status: Optional[TaskStatus] = None
    estimated_duration_minutes: Optional[int] = Field(default=None, ge=15, le=480)
    optional_user_estimate: Optional[str] = None
    optional_deadline: Optional[date] = None
    is_off_hours_allowed: Optional[bool] = None
    is_workday_allowed: Optional[bool] = None
    no_weekends: Optional[bool] = None
    description: Optional[str] = None
    procrastination_flag: Optional[bool] = None
    # Linked Google Calendar event (manually associated by user)
    linked_calendar_event_id: Optional[str] = None
    linked_calendar_event_title: Optional[str] = None
    linked_calendar_event_start: Optional[str] = None


class TaskRead(BaseModel):
    """Full task representation returned to the client."""
    id: int
    title: str
    type: TaskType
    priority: int
    status: TaskStatus
    estimated_duration_minutes: Optional[int]
    optional_user_estimate: Optional[str]
    optional_deadline: Optional[date]
    actual_duration_minutes: Optional[int]
    is_off_hours_allowed: bool
    is_workday_allowed: bool
    no_weekends: bool
    part_of_task_id: Optional[int]
    procrastination_flag: bool
    created_at: datetime
    completed_at: Optional[datetime]
    updated_at: datetime
    description: Optional[str]
    # Computed from calendar_blocks (populated by router, not ORM)
    scheduled_blocks: List[str] = Field(default_factory=list)
    next_scheduled_start: Optional[datetime] = None
    blocks: List[TaskBlockInfo] = Field(default_factory=list)
    # Linked Google Calendar event (manually associated by user)
    linked_calendar_event_id: Optional[str] = None
    linked_calendar_event_title: Optional[str] = None
    linked_calendar_event_start: Optional[str] = None
    # Cached AI Assistant response
    ai_assistant_cache: Optional[Any] = None
    ai_assistant_cached_at: Optional[datetime] = None

    model_config = {"from_attributes": True}

    @field_validator("optional_deadline", mode="before")
    @classmethod
    def coerce_deadline_to_date(cls, v: object) -> object:
        """The DB column is DateTime(timezone=True); extract just the date part."""
        if isinstance(v, datetime):
            return v.date()
        return v


class ReorderRequest(BaseModel):
    """Ordered list of task IDs representing the new priority sequence."""
    ordered_task_ids: List[int] = Field(min_length=1)


class CompleteRequest(BaseModel):
    actual_duration_minutes: Optional[int] = Field(default=None, ge=1, le=1440)


class MoreWorkRequest(BaseModel):
    """User-confirmed additional minutes to schedule beyond what's already on the calendar."""
    additional_minutes: int = Field(ge=15, le=480)


class MoreWorkSuggestion(BaseModel):
    """AI-suggested additional minutes for the more-work flow, plus context."""
    suggested_additional_minutes: int
    original_estimate_minutes: Optional[int]
    scheduled_past_minutes: int
    scheduled_future_minutes: int
    ai_available: bool


class RescheduleAllOverdueResponse(BaseModel):
    """Result of batch-rescheduling all overdue tasks."""
    rescheduled_task_ids: List[int]
    task_count: int


class BlockDoneRequest(BaseModel):
    """User-confirmed remaining minutes after marking a single chunk as done."""
    confirmed_remaining_minutes: int = Field(ge=0, le=960)
