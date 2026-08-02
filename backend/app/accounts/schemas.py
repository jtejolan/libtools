from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ToolKey = Literal[
    "bookclub", "storytime", "lendery_view", "lendery_manage"
]
PlatformRole = Literal["user", "admin"]


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
    username: str = Field(min_length=2, max_length=80)
    role: PlatformRole = "user"
    tools: list[ToolKey] = Field(default_factory=list)

    @field_validator("username")
    @classmethod
    def clean_username(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Name cannot be blank")
        return cleaned


class UserUpdate(BaseModel):
    active: bool | None = None
    role: PlatformRole | None = None
    tools: list[ToolKey] | None = None


class UserResponse(BaseModel):
    id: int
    username: str
    role: PlatformRole
    active: bool
    must_change_password: bool
    tools: list[str] = Field(default_factory=list)
    clubs: list[str] = Field(default_factory=list)
    created_at: datetime


class UserCreatedResponse(UserResponse):
    recovery_code: str


class CurrentUserResponse(UserResponse):
    model_config = ConfigDict(from_attributes=True)


class ChangePasswordRequest(PasswordPair):
    current_password: str = Field(min_length=1, max_length=200)


class RecoveryResetRequest(PasswordPair):
    username: str = Field(min_length=1, max_length=80)
    recovery_code: str = Field(min_length=10, max_length=200)


class AdminPasswordResetRequest(PasswordPair):
    pass


class RecoveryCodeResponse(BaseModel):
    recovery_code: str
