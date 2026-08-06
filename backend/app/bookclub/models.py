from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class BookClub(Base):
    __tablename__ = "book_clubs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text())
    public: Mapped[bool] = mapped_column(Boolean(), default=True, server_default="1")
    organizer_name: Mapped[str | None] = mapped_column(String(200))
    organizer_branch: Mapped[str | None] = mapped_column(String(200))
    video_call_url: Mapped[str | None] = mapped_column(String(500))

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
    notes: Mapped[str | None] = mapped_column(Text())

    meeting: Mapped[BookClubMeeting] = relationship(
        back_populates="participants"
    )
    member: Mapped[BookClubMember] = relationship()


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
