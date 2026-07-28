from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = "admin"
    password: str


class LoginResponse(BaseModel):
    ok: bool = True
    username: str
    is_admin: bool = True


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


class HolidayOut(BaseModel):
    id: int
    holiday_date: date
    name: str
    source: str
    notes: str

    model_config = {"from_attributes": True}


class HolidayCreate(BaseModel):
    holiday_date: date
    name: str
    notes: str = ""


class HolidayUpdate(BaseModel):
    name: str | None = None
    notes: str | None = None
    holiday_date: date | None = None


class EmailSettings(BaseModel):
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_use_tls: bool = True
    email_to: str = ""
    email_enabled: bool = False
    email_on_run: bool = True


class DeskSettings(BaseModel):
    use_llm: bool = True
    schedule_enabled: bool = True
    schedule_cron: str = "15 8 * * mon-fri"
    next_run_at: str | None = None
    email: EmailSettings = Field(default_factory=EmailSettings)


class ReportSummary(BaseModel):
    id: int
    created_at: datetime
    cutoff_iso: str
    bias: str
    confidence: int
    articles_in_window: int
    unique_stocks: int
    emailed: bool
    used_llm: bool
    status: str
    progress_pct: int = 0
    progress_message: str = ""

    model_config = {"from_attributes": True}


class ReportDetail(ReportSummary):
    markdown: str
    payload: dict[str, Any] = Field(default_factory=dict)


class RunRequest(BaseModel):
    use_llm: bool | None = None
    send_email: bool | None = None


class MessageOut(BaseModel):
    ok: bool = True
    message: str = ""
