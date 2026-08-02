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


class BookClubMember(Base):
    __tablename__ = "bookclub_members"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    joined_on: Mapped[date] = mapped_column(Date())
    active: Mapped[bool] = mapped_column(
        Boolean(), default=True, server_default="1"
    )
    notes: Mapped[str | None] = mapped_column(Text())


class BookClubMeeting(Base):
    __tablename__ = "bookclub_meetings"

    id: Mapped[int] = mapped_column(primary_key=True)
    meeting_date: Mapped[date] = mapped_column(Date(), index=True)
    meeting_time: Mapped[str | None] = mapped_column(String(50))
    location: Mapped[str | None] = mapped_column(String(200))
    book_title: Mapped[str] = mapped_column(String(300))
    book_author: Mapped[str] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text())
    giveaway_winner_member_id: Mapped[int | None] = mapped_column(
        ForeignKey("bookclub_members.id", ondelete="SET NULL")
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
    delivery_method: Mapped[str] = mapped_column(
        String(30), default="none", server_default="none"
    )
    destination_branch: Mapped[str | None] = mapped_column(String(200))
    book_checked_out: Mapped[bool] = mapped_column(
        Boolean(), default=False, server_default="0"
    )
    attended: Mapped[bool] = mapped_column(
        Boolean(), default=False, server_default="0"
    )

    meeting: Mapped[BookClubMeeting] = relationship(
        back_populates="participants"
    )
    member: Mapped[BookClubMember] = relationship()


class BookClubTemplate(Base):
    __tablename__ = "bookclub_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
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
