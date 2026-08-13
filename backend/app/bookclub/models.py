from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bookclub.scheduling import meeting_datetime_range
from database import Base


class BookClub(Base):
    __tablename__ = "book_clubs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text())
    public: Mapped[bool] = mapped_column(Boolean(), default=True, server_default="1")
    # Page visibility and enrollment are intentionally separate: a club can
    # advertise its reading program without accepting unrestricted signups.
    enrollment_policy: Mapped[str] = mapped_column(
        String(20), default="open", server_default="open"
    )
    organizer_name: Mapped[str | None] = mapped_column(String(200))
    organizer_branch: Mapped[str | None] = mapped_column(String(200))
    video_call_url: Mapped[str | None] = mapped_column(String(500))
    # Both library and private clubs are managed by LibtoolsUser accounts.
    # This controls library-specific defaults/presentation only;
    # BookClubAccess is the authorization mechanism for both.
    club_type: Mapped[str] = mapped_column(String(20), default="library", server_default="library")

    access: Mapped[list["BookClubAccess"]] = relationship(
        back_populates="club", cascade="all, delete-orphan"
    )


class BookClubAccess(Base):
    __tablename__ = "book_club_access"
    __table_args__ = (
        UniqueConstraint("club_id", "user_id", name="uq_book_club_user"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    club_id: Mapped[int] = mapped_column(
        ForeignKey("book_clubs.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("libtools_users.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(20), default="owner", server_default="owner")

    club: Mapped[BookClub] = relationship(back_populates="access")


class BookClubMember(Base):
    __tablename__ = "bookclub_members"
    __table_args__ = (
        UniqueConstraint("club_id", "email", name="uq_bookclub_club_email"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    club_id: Mapped[int] = mapped_column(
        ForeignKey("book_clubs.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320), index=True)
    # A roster entry is canonical whether or not the reader has a portal
    # login. Linking an account unlocks community features without creating
    # a second, parallel roster population.
    participant_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("bookclub_participant_accounts.id", ondelete="SET NULL"),
        index=True,
    )
    joined_on: Mapped[date] = mapped_column(Date())
    active: Mapped[bool] = mapped_column(
        Boolean(), default=True, server_default="1"
    )
    notes: Mapped[str | None] = mapped_column(Text())
    is_new_registrant: Mapped[bool] = mapped_column(
        Boolean(), default=False, server_default="0"
    )
    delivery_method: Mapped[str] = mapped_column(
        String(30), default="none", server_default="none"
    )
    destination_branch: Mapped[str | None] = mapped_column(String(200))
    onboarding_email_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    arrival_email_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    transit_label_printed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    last_reminder_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    participant_unsubscribed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    bio: Mapped[str | None] = mapped_column(Text())
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    directory_visible: Mapped[bool] = mapped_column(
        Boolean(), default=False, server_default="0"
    )

    @property
    def participant_account_linked(self) -> bool:
        return self.participant_account_id is not None


class BookClubBook(Base):
    __tablename__ = "bookclub_books"
    __table_args__ = (
        UniqueConstraint("club_id", "isbn", name="uq_bookclub_club_isbn"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    club_id: Mapped[int] = mapped_column(
        ForeignKey("book_clubs.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(300), index=True)
    author: Mapped[str] = mapped_column(String(200), index=True)
    cover_image_url: Mapped[str | None] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text())
    publication_date: Mapped[date | None] = mapped_column(Date())
    isbn: Mapped[str | None] = mapped_column(
        String(20), index=True
    )
    publisher: Mapped[str | None] = mapped_column(String(200))
    page_count: Mapped[int | None] = mapped_column(Integer())
    genres: Mapped[str | None] = mapped_column(String(500))
    series: Mapped[str | None] = mapped_column(String(300))
    catalogue_url: Mapped[str | None] = mapped_column(String(500))
    discussion_notes: Mapped[str | None] = mapped_column(Text())
    is_past_selection: Mapped[bool] = mapped_column(
        Boolean(), default=False, server_default="0"
    )

    meetings: Mapped[list["BookClubMeeting"]] = relationship(
        back_populates="book"
    )


class BookClubMeeting(Base):
    __tablename__ = "bookclub_meetings"

    id: Mapped[int] = mapped_column(primary_key=True)
    club_id: Mapped[int] = mapped_column(
        ForeignKey("book_clubs.id", ondelete="CASCADE"), index=True
    )
    meeting_date: Mapped[date] = mapped_column(Date(), index=True)
    meeting_time: Mapped[str | None] = mapped_column(String(50))
    meeting_duration_minutes: Mapped[int] = mapped_column(
        Integer(), default=90, server_default="90"
    )
    location: Mapped[str | None] = mapped_column(String(200))
    book_id: Mapped[int] = mapped_column(
        ForeignKey("bookclub_books.id", ondelete="RESTRICT"),
        index=True,
    )
    # Retained for backwards-compatible database migrations. New writes keep
    # these values synchronized with the related book record.
    book_title: Mapped[str] = mapped_column(String(300))
    book_author: Mapped[str] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text())
    discussion_notes: Mapped[str | None] = mapped_column(Text())
    status: Mapped[str] = mapped_column(
        String(30), default="planned", server_default="planned"
    )
    giveaway_winner_member_id: Mapped[int | None] = mapped_column(
        ForeignKey("bookclub_members.id", ondelete="SET NULL")
    )
    reminder_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    participants: Mapped[list["BookClubParticipation"]] = relationship(
        back_populates="meeting",
        cascade="all, delete-orphan",
    )
    discussion_questions: Mapped[list["BookClubDiscussionQuestion"]] = (
        relationship(
            back_populates="meeting",
            cascade="all, delete-orphan",
            order_by="BookClubDiscussionQuestion.position",
        )
    )
    giveaway_winner: Mapped[BookClubMember | None] = relationship(
        foreign_keys=[giveaway_winner_member_id]
    )
    book: Mapped[BookClubBook] = relationship(back_populates="meetings")
    club: Mapped[BookClub] = relationship()

    # Not mapped columns — plain Python properties that MeetingResponse
    # picks up via from_attributes, same as any other attribute. Null
    # when meeting_time doesn't parse (it's free text, e.g. "7:00 PM").
    @property
    def starts_at(self) -> datetime | None:
        time_range = meeting_datetime_range(
            self.meeting_date, self.meeting_time, self.meeting_duration_minutes
        )
        return time_range[0] if time_range else None

    @property
    def ends_at(self) -> datetime | None:
        time_range = meeting_datetime_range(
            self.meeting_date, self.meeting_time, self.meeting_duration_minutes
        )
        return time_range[1] if time_range else None


class BookClubParticipation(Base):
    __tablename__ = "bookclub_participation"
    __table_args__ = (
        UniqueConstraint(
            "meeting_id",
            "member_id",
            name="uq_bookclub_meeting_member",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    meeting_id: Mapped[int] = mapped_column(
        ForeignKey("bookclub_meetings.id", ondelete="CASCADE"),
        index=True,
    )
    member_id: Mapped[int] = mapped_column(
        ForeignKey("bookclub_members.id", ondelete="CASCADE"),
        index=True,
    )
    attended: Mapped[bool] = mapped_column(
        Boolean(), default=False, server_default="0"
    )
    participant_attended: Mapped[bool | None] = mapped_column(Boolean())
    participant_attendance_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    attendance_source: Mapped[str | None] = mapped_column(String(20))
    attendance_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    rsvp_status: Mapped[str | None] = mapped_column(String(20))
    notes: Mapped[str | None] = mapped_column(Text())

    meeting: Mapped[BookClubMeeting] = relationship(
        back_populates="participants"
    )
    member: Mapped[BookClubMember] = relationship()


class BookClubAnnouncement(Base):
    __tablename__ = "bookclub_announcements"

    id: Mapped[int] = mapped_column(primary_key=True)
    club_id: Mapped[int] = mapped_column(
        ForeignKey("book_clubs.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text())
    pinned: Mapped[bool] = mapped_column(Boolean(), default=False, server_default="0")
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    club: Mapped[BookClub] = relationship()


class BookClubAnnouncementRead(Base):
    __tablename__ = "bookclub_announcement_reads"
    __table_args__ = (
        UniqueConstraint(
            "announcement_id", "member_id", name="uq_bookclub_announcement_member_read"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    announcement_id: Mapped[int] = mapped_column(
        ForeignKey("bookclub_announcements.id", ondelete="CASCADE"), index=True
    )
    member_id: Mapped[int] = mapped_column(
        ForeignKey("bookclub_members.id", ondelete="CASCADE"), index=True
    )
    read_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class BookClubReadingProgress(Base):
    __tablename__ = "bookclub_reading_progress"
    __table_args__ = (
        UniqueConstraint("member_id", "book_id", name="uq_bookclub_member_book_progress"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    club_id: Mapped[int] = mapped_column(
        ForeignKey("book_clubs.id", ondelete="CASCADE"), index=True
    )
    member_id: Mapped[int] = mapped_column(
        ForeignKey("bookclub_members.id", ondelete="CASCADE"), index=True
    )
    book_id: Mapped[int] = mapped_column(
        ForeignKey("bookclub_books.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(20))
    current_page: Mapped[int | None] = mapped_column(Integer())
    shared_with_club: Mapped[bool] = mapped_column(
        Boolean(), default=False, server_default="0"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    book: Mapped[BookClubBook] = relationship()


class BookClubNotificationPreference(Base):
    __tablename__ = "bookclub_notification_preferences"

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(
        ForeignKey("bookclub_members.id", ondelete="CASCADE"), unique=True, index=True
    )
    announcements: Mapped[bool] = mapped_column(Boolean(), default=True, server_default="1")
    polls: Mapped[bool] = mapped_column(Boolean(), default=True, server_default="1")
    meeting_reminders: Mapped[bool] = mapped_column(Boolean(), default=True, server_default="1")
    discussion_replies: Mapped[bool] = mapped_column(Boolean(), default=True, server_default="1")
    delivery_frequency: Mapped[str] = mapped_column(
        String(20), default="immediate", server_default="immediate"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class BookClubDiscussionPost(Base):
    __tablename__ = "bookclub_discussion_posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    club_id: Mapped[int] = mapped_column(
        ForeignKey("book_clubs.id", ondelete="CASCADE"), index=True
    )
    book_id: Mapped[int] = mapped_column(
        ForeignKey("bookclub_books.id", ondelete="CASCADE"), index=True
    )
    member_id: Mapped[int] = mapped_column(
        ForeignKey("bookclub_members.id", ondelete="CASCADE"), index=True
    )
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("bookclub_discussion_posts.id", ondelete="CASCADE"), index=True
    )
    body: Mapped[str] = mapped_column(Text())
    spoiler: Mapped[bool] = mapped_column(Boolean(), default=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    member: Mapped[BookClubMember] = relationship()


class BookClubDiscussionReaction(Base):
    __tablename__ = "bookclub_discussion_reactions"
    __table_args__ = (
        UniqueConstraint("post_id", "member_id", name="uq_bookclub_post_member_reaction"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(
        ForeignKey("bookclub_discussion_posts.id", ondelete="CASCADE"), index=True
    )
    member_id: Mapped[int] = mapped_column(
        ForeignKey("bookclub_members.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(20), default="like", server_default="like")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class BookClubActivity(Base):
    __tablename__ = "bookclub_activity"

    id: Mapped[int] = mapped_column(primary_key=True)
    club_id: Mapped[int] = mapped_column(
        ForeignKey("book_clubs.id", ondelete="CASCADE"), index=True
    )
    member_id: Mapped[int] = mapped_column(
        ForeignKey("bookclub_members.id", ondelete="CASCADE"), index=True
    )
    book_id: Mapped[int] = mapped_column(
        ForeignKey("bookclub_books.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(30), index=True)
    detail: Mapped[str | None] = mapped_column(String(500))
    reference_id: Mapped[int | None] = mapped_column(Integer())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    member: Mapped[BookClubMember] = relationship()
    book: Mapped[BookClubBook] = relationship()


class BookClubTemplate(Base):
    __tablename__ = "bookclub_templates"
    __table_args__ = (
        UniqueConstraint("club_id", "key", name="uq_bookclub_club_template_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    club_id: Mapped[int] = mapped_column(
        ForeignKey("book_clubs.id", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(String(80), index=True)
    name: Mapped[str] = mapped_column(String(150))
    kind: Mapped[str] = mapped_column(String(20))
    subject: Mapped[str | None] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class BookClubDiscussionQuestion(Base):
    __tablename__ = "bookclub_discussion_questions"
    __table_args__ = (
        UniqueConstraint(
            "meeting_id",
            "position",
            name="uq_bookclub_question_position",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    meeting_id: Mapped[int] = mapped_column(
        ForeignKey("bookclub_meetings.id", ondelete="CASCADE"),
        index=True,
    )
    position: Mapped[int] = mapped_column(Integer())
    text: Mapped[str] = mapped_column(Text())

    meeting: Mapped[BookClubMeeting] = relationship(
        back_populates="discussion_questions"
    )


class BookClubRating(Base):
    """A participant's rating of a book, visible to every participant in
    the club (not just an aggregate) — see docs/backend/bookclub.md. FK to
    ParticipantAccount is string-based (bookclub_participant_accounts.id)
    rather than an ORM relationship, since that model lives in
    participant_models.py — crud.py joins in the participant's name
    explicitly rather than via a cross-module relationship() (no existing
    precedent for that in this package).
    """

    __tablename__ = "bookclub_ratings"
    __table_args__ = (
        UniqueConstraint("book_id", "participant_id", name="uq_bookclub_rating_book_participant"),
        CheckConstraint("rating BETWEEN 1 AND 5", name="ck_bookclub_rating_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    club_id: Mapped[int] = mapped_column(
        ForeignKey("book_clubs.id", ondelete="CASCADE"), index=True
    )
    book_id: Mapped[int] = mapped_column(
        ForeignKey("bookclub_books.id", ondelete="CASCADE"), index=True
    )
    participant_id: Mapped[int] = mapped_column(
        ForeignKey("bookclub_participant_accounts.id", ondelete="CASCADE"), index=True
    )
    rating: Mapped[float] = mapped_column(Float())
    review_text: Mapped[str | None] = mapped_column(Text())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class BookClubVotingRound(Base):
    """A poll for "what should we read next". Simplified from the original
    draft/open/closed design to just open/closed. There is no strong need
    for a prep-only "draft" stage before participants can see it: a facilitator
    opens a round with an initial candidate list already in hand. One open
    round per club at a time, enforced at the application layer in crud.py
    (not a DB constraint — SQLite's partial-unique-index support is
    inconsistent across the sqlite/Postgres backends this app supports).
    """

    __tablename__ = "bookclub_voting_rounds"

    id: Mapped[int] = mapped_column(primary_key=True)
    club_id: Mapped[int] = mapped_column(
        ForeignKey("book_clubs.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="open", server_default="open")
    winning_book_id: Mapped[int | None] = mapped_column(
        ForeignKey("bookclub_books.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BookClubBookCandidate(Base):
    """A book nominated for a voting round. `proposed_by_participant_id` is
    identifies participant proposals. Manager-added candidates use NULL and
    auto-approve; participant proposals start pending until reviewed.
    """

    __tablename__ = "bookclub_book_candidates"
    __table_args__ = (
        UniqueConstraint("voting_round_id", "book_id", name="uq_bookclub_candidate_round_book"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    voting_round_id: Mapped[int] = mapped_column(
        ForeignKey("bookclub_voting_rounds.id", ondelete="CASCADE"), index=True
    )
    book_id: Mapped[int] = mapped_column(
        ForeignKey("bookclub_books.id", ondelete="CASCADE"), index=True
    )
    proposed_by_participant_id: Mapped[int | None] = mapped_column(
        ForeignKey("bookclub_participant_accounts.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    book: Mapped[BookClubBook] = relationship()


class BookClubBookSuggestion(Base):
    """A participant's catalogue suggestion before it becomes a club book."""

    __tablename__ = "bookclub_book_suggestions"

    id: Mapped[int] = mapped_column(primary_key=True)
    club_id: Mapped[int] = mapped_column(
        ForeignKey("book_clubs.id", ondelete="CASCADE"), index=True
    )
    participant_id: Mapped[int] = mapped_column(
        ForeignKey("bookclub_participant_accounts.id", ondelete="CASCADE"), index=True
    )
    book_id: Mapped[int | None] = mapped_column(
        ForeignKey("bookclub_books.id", ondelete="SET NULL"), index=True
    )
    google_books_id: Mapped[str | None] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(String(300))
    author: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text())
    cover_image_url: Mapped[str | None] = mapped_column(String(1000))
    publication_date: Mapped[date | None] = mapped_column(Date())
    isbn: Mapped[str | None] = mapped_column(String(20))
    page_count: Mapped[int | None] = mapped_column(Integer())
    comments: Mapped[str | None] = mapped_column(Text())
    status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class BookClubVote(Base):
    __tablename__ = "bookclub_votes"
    __table_args__ = (
        UniqueConstraint("voting_round_id", "participant_id", name="uq_bookclub_vote_round_participant"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    voting_round_id: Mapped[int] = mapped_column(
        ForeignKey("bookclub_voting_rounds.id", ondelete="CASCADE"), index=True
    )
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("bookclub_book_candidates.id", ondelete="CASCADE"), index=True
    )
    participant_id: Mapped[int] = mapped_column(
        ForeignKey("bookclub_participant_accounts.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class BookClubDatePoll(Base):
    """A "when should we meet next" poll — deliberately a separate,
    independent system from BookClubVotingRound/BookClubBookCandidate/
    BookClubVote (not a shared generalized poll), per an explicit product
    choice: each can change shape later without the other compromising it.
    Simpler than book voting in one respect — date options are
    facilitator-only, so there's no candidate approval queue here at all.
    """

    __tablename__ = "bookclub_date_polls"

    id: Mapped[int] = mapped_column(primary_key=True)
    club_id: Mapped[int] = mapped_column(
        ForeignKey("book_clubs.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="open", server_default="open")
    winning_date: Mapped[date | None] = mapped_column(Date())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BookClubDatePollOption(Base):
    __tablename__ = "bookclub_date_poll_options"
    __table_args__ = (
        UniqueConstraint("poll_id", "option_date", name="uq_bookclub_date_poll_option"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    poll_id: Mapped[int] = mapped_column(
        ForeignKey("bookclub_date_polls.id", ondelete="CASCADE"), index=True
    )
    option_date: Mapped[date] = mapped_column(Date())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class BookClubDatePollVote(Base):
    __tablename__ = "bookclub_date_poll_votes"
    __table_args__ = (
        UniqueConstraint(
            "poll_id", "participant_id", "option_id", name="uq_bookclub_date_poll_vote"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    poll_id: Mapped[int] = mapped_column(
        ForeignKey("bookclub_date_polls.id", ondelete="CASCADE"), index=True
    )
    option_id: Mapped[int] = mapped_column(
        ForeignKey("bookclub_date_poll_options.id", ondelete="CASCADE"), index=True
    )
    participant_id: Mapped[int] = mapped_column(
        ForeignKey("bookclub_participant_accounts.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
