from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from accounts.schemas import EMAIL_PATTERN


def _clean_name(value: str) -> str:
    cleaned = " ".join(value.split())
    if not cleaned:
        raise ValueError("Name cannot be blank")
    return cleaned


def _clean_email(value: str) -> str:
    cleaned = value.strip().casefold()
    if not EMAIL_PATTERN.fullmatch(cleaned):
        raise ValueError("Enter a valid email address")
    return cleaned


class ParticipantPasswordPair(BaseModel):
    password: str = Field(min_length=10, max_length=200)
    confirm_password: str = Field(min_length=10, max_length=200)

    @model_validator(mode="after")
    def passwords_match(self):
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self


class ParticipantRegistrationRequest(ParticipantPasswordPair):
    club_slug: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=200)
    # Required and verified, unlike the optional email on LibtoolsUser —
    # participant accounts have no username to fall back on for identity.
    email: str = Field(min_length=3, max_length=320)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return _clean_name(value)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return _clean_email(value)


class ParticipantLoginRequest(BaseModel):
    club_slug: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=200)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return _clean_email(value)


class ParticipantResponse(BaseModel):
    id: int
    club_id: int
    club_name: str
    club_slug: str
    name: str
    email: str
    email_verified: bool
    role: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ParticipantClubCreateRequest(ParticipantPasswordPair):
    club_name: str = Field(min_length=1, max_length=200)
    club_slug: str | None = Field(default=None, max_length=120)
    club_description: str | None = None
    facilitator_name: str = Field(min_length=1, max_length=200)
    # Required and verified, same reasoning as ParticipantRegistrationRequest.
    facilitator_email: str = Field(min_length=3, max_length=320)

    @field_validator("facilitator_name")
    @classmethod
    def validate_facilitator_name(cls, value: str) -> str:
        return _clean_name(value)

    @field_validator("facilitator_email")
    @classmethod
    def validate_facilitator_email(cls, value: str) -> str:
        return _clean_email(value)


class ParticipantEmailActionResponse(BaseModel):
    message: str
    delivery_configured: bool


class ParticipantVerifyEmailRequest(BaseModel):
    token: str = Field(min_length=20, max_length=200)


class ParticipantPasswordResetEmailRequest(BaseModel):
    club_slug: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=320)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return _clean_email(value)


class ParticipantPasswordResetConfirmRequest(ParticipantPasswordPair):
    token: str = Field(min_length=20, max_length=200)
