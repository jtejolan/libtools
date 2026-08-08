from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class ParticipantAccount(Base):
    """A club member's own login, separate from staff LibtoolsUser accounts.

    Scoped to a single club (uniqueness is club_id+email, not global) —
    the same person joining two different clubs gets two separate rows,
    mirroring how BookClubMember/BookClubAccess are already club-scoped.
    """

    __tablename__ = "bookclub_participant_accounts"
    __table_args__ = (
        UniqueConstraint("club_id", "email", name="uq_bookclub_participant_club_email"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    club_id: Mapped[int] = mapped_column(
        ForeignKey("book_clubs.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320), index=True)
    password_hash: Mapped[str] = mapped_column(String(500))
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # "owner" is the club's facilitator/lead (set at club-creation time,
    # single owner in v1 — see docs/backend/bookclub.md); "member" is an
    # ordinary participant. Both are the same account type/session, just a
    # permission check away from each other, not a separate table.
    role: Mapped[str] = mapped_column(String(20), default="member", server_default="member")
    session_version: Mapped[int] = mapped_column(Integer(), default=1, server_default="1")
    active: Mapped[bool] = mapped_column(Boolean(), default=True, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    tokens: Mapped[list["ParticipantAccountToken"]] = relationship(
        back_populates="participant", cascade="all, delete-orphan"
    )


class ParticipantAccountToken(Base):
    """A hashed, expiring token for participant email verification/reset.

    Mirrors accounts.models.AccountToken but scoped to ParticipantAccount —
    kept as a separate table/module rather than a shared generic one, same
    as the two independent catalogue.py implementations elsewhere in this
    package (see docs/backend/bookclub.md).
    """

    __tablename__ = "bookclub_participant_account_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    participant_id: Mapped[int] = mapped_column(
        ForeignKey("bookclub_participant_accounts.id", ondelete="CASCADE"), index=True
    )
    purpose: Mapped[str] = mapped_column(String(40), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    participant: Mapped[ParticipantAccount] = relationship(back_populates="tokens")
