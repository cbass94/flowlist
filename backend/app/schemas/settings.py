from datetime import time
from typing import Optional

from pydantic import BaseModel, Field


class CalendarItem(BaseModel):
    id: str
    summary: str
    primary: bool = False


class UserSettings(BaseModel):
    timezone: str
    display_name: Optional[str]
    personal_account_connected: bool
    # Scheduling preferences
    work_start_hour: int
    work_end_hour: int
    hard_start_hour: int
    hard_end_hour: int
    buffer_minutes: int
    # Calendar IDs (None = using app default from env)
    work_calendar_id: Optional[str]
    personal_calendar_id: Optional[str]
    # Weekend scheduling
    allow_work_on_weekends: bool = False
    allow_personal_on_weekends: bool = True
    # Per-day weekend hour ranges (null = that day disabled)
    work_saturday_start_time: Optional[time] = None
    work_saturday_end_time: Optional[time] = None
    work_sunday_start_time: Optional[time] = None
    work_sunday_end_time: Optional[time] = None
    personal_saturday_start_time: Optional[time] = None
    personal_saturday_end_time: Optional[time] = None
    personal_sunday_start_time: Optional[time] = None
    personal_sunday_end_time: Optional[time] = None
    # Synthesis time (post-meeting buffer)
    synthesis_enabled: bool = True
    synthesis_duration_minutes: int = 15
    synthesis_self_emails: Optional[str] = None
    # Calendar color-coding
    colorize_enabled: bool = False
    color_purposeful: str = "10"
    color_necessary: str = "7"
    color_distracting: str = "11"
    color_unnecessary: str = "8"


class UpdateSettings(BaseModel):
    timezone: Optional[str] = Field(default=None, min_length=1, max_length=64)
    display_name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    work_start_hour: Optional[int] = Field(default=None, ge=0, le=23)
    work_end_hour: Optional[int] = Field(default=None, ge=0, le=23)
    hard_start_hour: Optional[int] = Field(default=None, ge=0, le=23)
    hard_end_hour: Optional[int] = Field(default=None, ge=0, le=23)
    buffer_minutes: Optional[int] = Field(default=None, ge=0, le=120)
    work_calendar_id: Optional[str] = Field(default=None, max_length=255)
    personal_calendar_id: Optional[str] = Field(default=None, max_length=255)
    allow_work_on_weekends: Optional[bool] = None
    allow_personal_on_weekends: Optional[bool] = None
    # Per-day weekend hour ranges — pass null to disable a day
    work_saturday_start_time: Optional[time] = None
    work_saturday_end_time: Optional[time] = None
    work_sunday_start_time: Optional[time] = None
    work_sunday_end_time: Optional[time] = None
    personal_saturday_start_time: Optional[time] = None
    personal_saturday_end_time: Optional[time] = None
    personal_sunday_start_time: Optional[time] = None
    personal_sunday_end_time: Optional[time] = None
    # Synthesis time (post-meeting buffer)
    synthesis_enabled: Optional[bool] = None
    synthesis_duration_minutes: Optional[int] = Field(default=None, ge=5, le=120)
    synthesis_self_emails: Optional[str] = Field(default=None, max_length=2000)
    # Calendar color-coding
    colorize_enabled: Optional[bool] = None
    color_purposeful: Optional[str] = Field(default=None, max_length=2)
    color_necessary: Optional[str] = Field(default=None, max_length=2)
    color_distracting: Optional[str] = Field(default=None, max_length=2)
    color_unnecessary: Optional[str] = Field(default=None, max_length=2)
