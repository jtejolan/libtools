from datetime import date, datetime
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    field_validator,
    model_validator,
)


class ClubCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str | None = Field(default=None, max_length=120)
    description: str | None = None
    public: bool = True
    organizer_name: str | None = Field(default=None, max_length=200)
    organizer_branch: str | None = Field(default=None, max_length=200)
    video_call_url: str | None = Field(default=None, max_length=500)
    club_type: Literal["library", "private"] = "library"


class ClubUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    slug: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    public: bool | None = None
    organizer_name: str | None = Field(default=None, max_length=200)
    organizer_branch: str | None = Field(default=None, max_length=200)
    video_call_url: str | None = Field(default=None, max_length=500)
    club_type: Literal["library", "private"] | None = None


class ClubResponse(BaseModel):
    id: int
    name: str
    slug: str
    description: str | None
    public: bool
    organizer_name: str | None
    organizer_branch: str | None
    video_call_url: str | None = None
    club_type: str
    role: str | None = None
    model_config = ConfigDict(from_attributes=True)


class PublicMeetingResponse(BaseModel):
    meeting_date: date
    meeting_time: str | None
    location: str | None
    book: "BookResponse"
    model_config = ConfigDict(from_attributes=True)


class PublicShelfBookResponse(BaseModel):
    title: str
    author: str
    cover_image_url: str | None = None
    meeting_date: date | None = None
    model_config = ConfigDict(from_attributes=True)


class PublicClubResponse(BaseModel):
    name: str
    slug: str
    description: str | None
    organizer_name: str | None
    organizer_branch: str | None
    upcoming_meeting: PublicMeetingResponse | None
    shelf: list[PublicShelfBookResponse] = Field(default_factory=list)

DeliveryMethod = Literal["pickup", "transfer", "none"]
TemplateKind = Literal["email", "print"]


def _strip(value: str) -> str:
    return value.strip()


class MemberBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=320)
    joined_on: date
    active: bool = True
    notes: str | None = None
    is_new_registrant: bool = False
    delivery_method: DeliveryMethod = "none"
    destination_branch: str | None = Field(default=None, max_length=200)

    _strip_name = field_validator("name")(_strip)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.strip().lower()
        if "@" not in value or value.startswith("@") or value.endswith("@"):
            raise ValueError("email must be a valid email address")
        return value

    @model_validator(mode="after")
    def transfer_requires_branch(self):
        if self.delivery_method == "transfer" and not self.destination_branch:
            raise ValueError("destination_branch is required for a transfer")
        return self


class MemberCreate(MemberBase):
    pass


class MemberUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    email: str | None = Field(default=None, min_length=3, max_length=320)
    joined_on: date | None = None
    active: bool | None = None
    notes: str | None = None
    is_new_registrant: bool | None = None
    delivery_method: DeliveryMethod | None = None
    destination_branch: str | None = Field(default=None, max_length=200)

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

    @model_validator(mode="after")
    def transfer_requires_branch(self):
        if self.delivery_method == "transfer" and not self.destination_branch:
            raise ValueError("destination_branch is required for a transfer")
        return self


class MemberResponse(MemberBase):
    id: int
    participant_account_id: int | None = None
    participant_account_linked: bool = False
    onboarding_email_sent_at: datetime | None = None
    arrival_email_sent_at: datetime | None = None
    transit_label_printed_at: datetime | None = None
    last_reminder_sent_at: datetime | None = None
    model_config = ConfigDict(from_attributes=True)


class BookBase(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    author: str = Field(min_length=1, max_length=200)
    cover_image_url: HttpUrl | None = None
    description: str | None = None
    publication_date: date | None = None
    isbn: str | None = Field(default=None, min_length=10, max_length=20)
    publisher: str | None = Field(default=None, max_length=200)
    page_count: int | None = Field(default=None, ge=1)
    genres: str | None = Field(default=None, max_length=500)
    series: str | None = Field(default=None, max_length=300)
    catalogue_url: HttpUrl | None = None
    discussion_notes: str | None = None
    is_past_selection: bool = False

    @field_validator("title", "author")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("isbn")
    @classmethod
    def normalize_isbn(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.replace("-", "").replace(" ", "").upper()


class BookCreate(BookBase):
    pass


class BookUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    author: str | None = Field(default=None, min_length=1, max_length=200)
    cover_image_url: HttpUrl | None = None
    description: str | None = None
    publication_date: date | None = None
    isbn: str | None = Field(default=None, min_length=10, max_length=20)
    publisher: str | None = Field(default=None, max_length=200)
    page_count: int | None = Field(default=None, ge=1)
    genres: str | None = Field(default=None, max_length=500)
    series: str | None = Field(default=None, max_length=300)
    catalogue_url: HttpUrl | None = None
    discussion_notes: str | None = None
    is_past_selection: bool | None = None

    @field_validator("is_past_selection")
    @classmethod
    def past_selection_cannot_be_null(cls, value: bool | None) -> bool:
        if value is None:
            raise ValueError("field cannot be null")
        return value

    @field_validator("title", "author")
    @classmethod
    def required_text_cannot_be_null(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("field cannot be null")
        return value.strip()

    @field_validator("isbn")
    @classmethod
    def normalize_isbn(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.replace("-", "").replace(" ", "").upper()


class BookResponse(BookBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


class BookInsightRatingResponse(BaseModel):
    participant_name: str
    rating: int
    review_text: str | None
    updated_at: datetime


class BookInsightMeetingResponse(BaseModel):
    id: int
    meeting_date: date
    meeting_time: str | None
    location: str | None
    status: str
    discussion_notes: str | None
    roster_count: int
    attendance_count: int
    pages_read: int


class BookInsightsResponse(BaseModel):
    book_id: int
    average_rating: float | None
    rating_count: int
    ratings: list[BookInsightRatingResponse]
    meetings: list[BookInsightMeetingResponse]
    total_attendance: int
    reading_impact_pages: int


class BookImportRequest(BaseModel):
    catalogue_url: HttpUrl


class BookImportResponse(BaseModel):
    title: str | None = None
    author: str | None = None
    cover_image_url: HttpUrl | None = None
    description: str | None = None
    publication_date: date | None = None
    isbn: str | None = None
    publisher: str | None = None
    page_count: int | None = None
    genres: str | None = None
    series: str | None = None
    catalogue_url: HttpUrl


class MeetingBase(BaseModel):
    meeting_date: date
    meeting_time: str | None = Field(default=None, max_length=50)
    meeting_duration_minutes: int = Field(default=90, ge=15, le=480)
    location: str | None = Field(default=None, max_length=200)
    notes: str | None = None
    discussion_notes: str | None = None
    # "in_progress" is computed client-side from meeting time + duration,
    # never stored. "cancelled" doesn't exist — delete the meeting instead.
    status: Literal["planned", "completed"] = "planned"


class MeetingCreate(MeetingBase):
    book_id: int = Field(ge=1)


class MeetingUpdate(BaseModel):
    meeting_date: date | None = None
    meeting_time: str | None = Field(default=None, max_length=50)
    meeting_duration_minutes: int | None = Field(default=None, ge=15, le=480)
    location: str | None = Field(default=None, max_length=200)
    book_id: int | None = Field(default=None, ge=1)
    notes: str | None = None
    discussion_notes: str | None = None
    status: Literal["planned", "completed"] | None = None
    # Settable directly — a display-mode toggle (which view a session opens
    # to), not an audit-trail field, so it doesn't need a dedicated endpoint
    # the way the email-sent timestamps do. Null clears it (unarchive).
    archived_at: datetime | None = None

    @field_validator("meeting_date", "book_id", "status")
    @classmethod
    def required_values_cannot_be_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("field cannot be null")
        return value


class MeetingResponse(MeetingBase):
    id: int
    book_id: int
    book: BookResponse
    giveaway_winner_member_id: int | None = None
    reminder_sent_at: datetime | None = None
    archived_at: datetime | None = None
    # Widened from MeetingBase's Literal on purpose: this is read-only output,
    # not something a client is choosing, so a stray legacy value (e.g. a
    # pre-migration "in_progress"/"cancelled" row) should still be reported
    # rather than 500ing the whole list. Writes stay strict via
    # MeetingBase/MeetingUpdate's Literal — this doesn't loosen what can be
    # newly saved.
    status: str = "planned"
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    model_config = ConfigDict(from_attributes=True)


class ParticipationUpdate(BaseModel):
    attended: bool | None = None
    notes: str | None = None


class ParticipationResponse(BaseModel):
    id: int
    meeting_id: int
    member_id: int
    attended: bool
    notes: str | None = None
    member: MemberResponse
    model_config = ConfigDict(from_attributes=True)


class GiveawayWinnerResponse(BaseModel):
    meeting_id: int
    member: MemberResponse


class MemberHistoryResponse(BaseModel):
    meeting: MeetingResponse
    attended: bool


class OnboardingSendResponse(BaseModel):
    member_id: int
    sent: bool
    already_sent_before: bool


class ReminderSendRequest(BaseModel):
    member_ids: list[int] = Field(min_length=1)
    subject_override: str | None = None
    body_override: str | None = None


class ReminderSendResponse(BaseModel):
    sent: bool
    recipient_count: int
    already_sent_before: bool


class MemberParticipationSummary(BaseModel):
    member: MemberResponse
    meetings_total: int
    attended_count: int
    giveaways_won: int
    pages_read: int
    last_attended_date: date | None = None
    last_contacted_at: datetime | None = None
    meetings_since_last_attended: int


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


class TransitLabelRenderRequest(BaseModel):
    member_id: int = Field(ge=1)
    destination_branch: str = Field(min_length=1, max_length=200)


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
