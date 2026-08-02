from datetime import date, datetime
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

DeliveryMethod = Literal["pickup", "transfer", "none"]
RecipientFilter = Literal[
    "all",
    "checked_out",
    "not_checked_out",
    "pickup",
    "transfer",
    "no_copy",
]
TemplateKind = Literal["email", "print"]


def _strip(value: str) -> str:
    return value.strip()


class MemberBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=320)
    joined_on: date
    active: bool = True
    notes: str | None = None

    _strip_name = field_validator("name")(_strip)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.strip().lower()
        if "@" not in value or value.startswith("@") or value.endswith("@"):
            raise ValueError("email must be a valid email address")
        return value


class MemberCreate(MemberBase):
    pass


class MemberUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    email: str | None = Field(default=None, min_length=3, max_length=320)
    joined_on: date | None = None
    active: bool | None = None
    notes: str | None = None

    @field_validator("name", "email", "joined_on", "active")
    @classmethod
    def required_values_cannot_be_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("field cannot be null")
        return value

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        return value.strip()

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.strip().lower()
        if "@" not in value or value.startswith("@") or value.endswith("@"):
            raise ValueError("email must be a valid email address")
        return value


class MemberResponse(MemberBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


class MeetingBase(BaseModel):
    meeting_date: date
    meeting_time: str | None = Field(default=None, max_length=50)
    location: str | None = Field(default=None, max_length=200)
    book_title: str = Field(min_length=1, max_length=300)
    book_author: str = Field(min_length=1, max_length=200)
    notes: str | None = None


class MeetingCreate(MeetingBase):
    add_active_members: bool = True


class MeetingUpdate(BaseModel):
    meeting_date: date | None = None
    meeting_time: str | None = Field(default=None, max_length=50)
    location: str | None = Field(default=None, max_length=200)
    book_title: str | None = Field(default=None, min_length=1, max_length=300)
    book_author: str | None = Field(default=None, min_length=1, max_length=200)
    notes: str | None = None

    @field_validator("meeting_date", "book_title", "book_author")
    @classmethod
    def required_values_cannot_be_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("field cannot be null")
        return value


class MeetingResponse(MeetingBase):
    id: int
    giveaway_winner_member_id: int | None = None
    model_config = ConfigDict(from_attributes=True)


class ParticipationUpdate(BaseModel):
    delivery_method: DeliveryMethod | None = None
    destination_branch: str | None = Field(default=None, max_length=200)
    book_checked_out: bool | None = None
    attended: bool | None = None

    @model_validator(mode="after")
    def transfer_requires_branch(self):
        if self.delivery_method == "transfer" and not self.destination_branch:
            raise ValueError("destination_branch is required for a transfer")
        return self


class ParticipationResponse(BaseModel):
    id: int
    meeting_id: int
    member_id: int
    delivery_method: DeliveryMethod
    destination_branch: str | None = None
    book_checked_out: bool
    attended: bool
    member: MemberResponse
    model_config = ConfigDict(from_attributes=True)


class RosterSyncResponse(BaseModel):
    added: int
    total: int


class GiveawayWinnerResponse(BaseModel):
    meeting_id: int
    member: MemberResponse


class MemberHistoryResponse(BaseModel):
    meeting: MeetingResponse
    delivery_method: DeliveryMethod
    destination_branch: str | None = None
    book_checked_out: bool
    attended: bool


class TemplateBase(BaseModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]*$", max_length=80)
    name: str = Field(min_length=1, max_length=150)
    kind: TemplateKind
    subject: str | None = Field(default=None, max_length=300)
    body: str = Field(min_length=1)

    @model_validator(mode="after")
    def email_requires_subject(self):
        if self.kind == "email" and not self.subject:
            raise ValueError("email templates require a subject")
        return self


class TemplateCreate(TemplateBase):
    pass


class TemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    subject: str | None = Field(default=None, max_length=300)
    body: str | None = Field(default=None, min_length=1)


class TemplateResponse(TemplateBase):
    id: int
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class TemplateRenderRequest(BaseModel):
    variables: dict[str, str | int | bool | None] = Field(default_factory=dict)
    subject_override: str | None = None
    body_override: str | None = None


class TemplateRenderResponse(BaseModel):
    subject: str | None
    body: str
    missing_variables: list[str]


class EmailPreviewRequest(BaseModel):
    email_type: Literal["onboarding", "monthly_reminder"]
    member_ids: list[int] | None = None
    subject_override: str | None = None
    body_override: str | None = None


class EmailPreviewResponse(BaseModel):
    member_id: int
    member_name: str
    email: str
    template_key: str
    subject: str
    body: str
    missing_variables: list[str]


class TransitLabelRequest(BaseModel):
    member_ids: list[int] | None = None
    body_override: str | None = None


class TransitLabelResponse(BaseModel):
    member_id: int
    member_name: str
    destination_branch: str
    body: str
    missing_variables: list[str]


class DiscussionQuestionCreate(BaseModel):
    text: str = Field(min_length=1)
    position: int | None = Field(default=None, ge=1)


class DiscussionQuestionUpdate(BaseModel):
    text: str | None = Field(default=None, min_length=1)
    position: int | None = Field(default=None, ge=1)


class DiscussionQuestionResponse(BaseModel):
    id: int
    meeting_id: int
    position: int
    text: str
    model_config = ConfigDict(from_attributes=True)


class GenerateQuestionsRequest(BaseModel):
    count: int = Field(default=10, ge=1, le=20)
    spoiler_free: bool = False
    tone: Literal["casual", "in_depth"] = "casual"
    focus: Literal[
        "balanced", "themes", "characters", "science_fiction", "style"
    ] = "balanced"
    synopsis: str | None = Field(default=None, max_length=5000)
    replace_existing: bool = False
