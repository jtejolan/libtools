from datetime import date, datetime
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ToolKey = Literal["lendery_manage"]
PlatformRole = Literal["user", "admin"]
QuickActionKey = Literal[
    "lendery-suggest-item",
    "lendery-add-item",
    "lendery-report-issue",
    "bookclub-add-member",
    "bookclub-add-book",
]
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def clean_username(value: str) -> str:
    cleaned = " ".join(value.split())
    if not cleaned:
        raise ValueError("Username cannot be blank")
    return cleaned


def clean_name(value: str) -> str:
    cleaned = " ".join(value.split())
    if not cleaned:
        raise ValueError("Name cannot be blank")
    return cleaned


def clean_email(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    cleaned = value.strip().casefold()
    if not EMAIL_PATTERN.fullmatch(cleaned):
        raise ValueError("Enter a valid email address")
    return cleaned


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


class PasswordPair(BaseModel):
    password: str = Field(min_length=10, max_length=200)
    confirm_password: str = Field(min_length=10, max_length=200)

    @model_validator(mode="after")
    def passwords_match(self):
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self


class UserCreate(PasswordPair):
    name: str = Field(min_length=1, max_length=200)
    username: str = Field(min_length=2, max_length=80)
    email: str = Field(min_length=3, max_length=320)
    role: PlatformRole = "user"
    tools: list[ToolKey] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return clean_name(value)

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        return clean_username(value)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        cleaned = clean_email(value)
        if cleaned is None:
            raise ValueError("Email is required")
        return cleaned


class RegistrationRequest(PasswordPair):
    name: str = Field(min_length=1, max_length=200)
    username: str = Field(min_length=2, max_length=80)
    email: str = Field(min_length=3, max_length=320)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return clean_name(value)

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        return clean_username(value)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        cleaned = clean_email(value)
        if cleaned is None:
            raise ValueError("Email is required")
        return cleaned


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    active: bool | None = None
    role: PlatformRole | None = None
    tools: list[ToolKey] | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        return clean_name(value) if value is not None else None


class UserResponse(BaseModel):
    id: int
    name: str
    username: str
    email: str | None
    email_verified: bool
    role: PlatformRole
    active: bool
    must_change_password: bool
    tools: list[str] = Field(default_factory=list)
    clubs: list[str] = Field(default_factory=list)
    quick_actions: list[QuickActionKey] = Field(default_factory=list)
    created_at: datetime


class UserCreatedResponse(UserResponse):
    recovery_code: str
    email_verification_required: bool = False
    email_delivery_configured: bool = False


class RegistrationResponse(UserCreatedResponse):
    pass


class CurrentUserResponse(UserResponse):
    model_config = ConfigDict(from_attributes=True)


class DashboardLenderySummary(BaseModel):
    total_items: int
    checked_out_items: int
    available_items: int
    attention_count: int | None = None


class DashboardMeetingSummary(BaseModel):
    club_id: int
    club_name: str
    meeting_id: int
    meeting_date: date
    days_until: int
    meeting_time: str | None = None
    location: str | None = None
    book_title: str


class DashboardFollowupSummary(BaseModel):
    club_id: int
    member_id: int
    member_name: str
    stage: str


class DashboardBookClubSummary(BaseModel):
    has_access: bool
    club_count: int
    next_meeting: DashboardMeetingSummary | None = None
    followup_count: int = 0
    next_followup: DashboardFollowupSummary | None = None


class DashboardSummary(BaseModel):
    lendery: DashboardLenderySummary
    bookclub: DashboardBookClubSummary


class QuickActionsUpdate(BaseModel):
    actions: list[QuickActionKey] = Field(min_length=1, max_length=4)

    @field_validator("actions")
    @classmethod
    def actions_must_be_unique(
        cls, value: list[QuickActionKey]
    ) -> list[QuickActionKey]:
        if len(value) != len(set(value)):
            raise ValueError("Select each quick action only once")
        return value


class QuickActionsResponse(BaseModel):
    quick_actions: list[QuickActionKey]


class ChangePasswordRequest(PasswordPair):
    current_password: str = Field(min_length=1, max_length=200)


class RecoveryResetRequest(PasswordPair):
    username: str = Field(min_length=1, max_length=80)
    recovery_code: str = Field(min_length=10, max_length=200)


class AdminPasswordResetRequest(PasswordPair):
    pass


class RecoveryCodeResponse(BaseModel):
    recovery_code: str


class EmailActionResponse(BaseModel):
    message: str
    delivery_configured: bool


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=20, max_length=200)


class PasswordResetEmailRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        cleaned = clean_email(value)
        if cleaned is None:
            raise ValueError("Enter a valid email address")
        return cleaned


class PasswordResetConfirmRequest(PasswordPair):
    token: str = Field(min_length=20, max_length=200)
