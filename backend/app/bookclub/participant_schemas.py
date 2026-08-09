from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from accounts.schemas import EMAIL_PATTERN
from bookclub.schemas import BookResponse


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
    member_id: int
    role: str = "member"
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


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


class RatingSubmit(BaseModel):
    rating: int = Field(ge=1, le=5)
    review_text: str | None = Field(default=None, max_length=4000)

    @field_validator("review_text")
    @classmethod
    def blank_review_is_null(cls, value: str | None) -> str | None:
        return value.strip() or None if value else None


class RatingResponse(BaseModel):
    id: int
    book_id: int
    participant_id: int
    participant_name: str
    rating: int
    review_text: str | None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class BookRatingsResponse(BaseModel):
    book_id: int
    average: float | None
    count: int
    ratings: list[RatingResponse]


class ProposeCandidateRequest(BaseModel):
    book_id: int = Field(ge=1)


class CastVoteRequest(BaseModel):
    candidate_id: int = Field(ge=1)


class OpenVotingRoundRequest(BaseModel):
    candidate_book_ids: list[int] = Field(default_factory=list)


class CandidateResponse(BaseModel):
    id: int
    book: BookResponse
    status: str
    proposed_by_participant_id: int | None
    proposed_by_name: str | None
    # Hidden (null) while the round is open and the caller is an ordinary
    # participant, to avoid a visible running tally influencing votes —
    # always populated for facilitators and for closed rounds.
    vote_count: int | None = None
    created_at: datetime


class VotingRoundResponse(BaseModel):
    id: int
    status: str
    winning_book: BookResponse | None = None
    candidates: list[CandidateResponse]
    my_vote_candidate_id: int | None = None


class OpenDatePollRequest(BaseModel):
    # Consistent with OpenVotingRoundRequest: an empty list is allowed, more
    # dates can be added afterward via the add-option endpoint.
    option_dates: list[date] = Field(default_factory=list)


class AddDateOptionRequest(BaseModel):
    option_date: date


class CastDateVoteRequest(BaseModel):
    option_id: int = Field(ge=1)


class DatePollOptionResponse(BaseModel):
    id: int
    option_date: date
    # Same hidden-while-open / null-vs-zero convention as CandidateResponse.
    vote_count: int | None = None


class DatePollResponse(BaseModel):
    id: int
    status: str
    winning_date: date | None = None
    options: list[DatePollOptionResponse]
    my_vote_option_id: int | None = None


class BroadcastEmailRequest(BaseModel):
    template_key: str = Field(min_length=1, max_length=80)
    variables: dict[str, str | int | bool | None] = Field(default_factory=dict)


class BroadcastEmailResponse(BaseModel):
    # Audience size (who we tried to reach), independent of whether any
    # individual send actually succeeded — see sent_count for that. Keeping
    # these separate matters specifically because delivery_configured is
    # commonly False in dev/test (no RESEND_API_KEY), where recipient_count
    # should still reflect the real audience, not silently read 0.
    recipient_count: int
    sent_count: int
    delivery_configured: bool
    missing_variables: list[str] = Field(default_factory=list)


class UnsubscribeRequest(BaseModel):
    token: str = Field(min_length=1, max_length=500)


class UnsubscribeResponse(BaseModel):
    club_name: str
    email: str
    already_unsubscribed: bool
