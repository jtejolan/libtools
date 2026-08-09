from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from bookclub.models import BookClub, BookClubMember
from bookclub.participant_models import ParticipantAccount
from bookclub.participant_schemas import ParticipantResponse
from bookclub.participant_session import get_participant_session
from dependencies import DatabaseSession
from security import verify_password

SESSION_PARTICIPANT_ID = "bookclub_participant_id"
SESSION_PARTICIPANT_VERSION = "bookclub_participant_session_version"
SESSION_MEMBER_ID = "bookclub_member_id"


def get_participant_by_email(db: Session, email: str) -> ParticipantAccount | None:
    return db.scalar(
        select(ParticipantAccount).where(
            func.lower(ParticipantAccount.email) == email.casefold(),
        )
    )


def verify_participant_login(
    db: Session, email: str, password: str
) -> ParticipantAccount | None:
    participant = get_participant_by_email(db, email)
    if (
        participant is None
        or not participant.active
        or not verify_password(password, participant.password_hash)
    ):
        return None
    return participant


def participant_response(
    participant: ParticipantAccount, club: BookClub, member: BookClubMember
) -> ParticipantResponse:
    return ParticipantResponse(
        id=participant.id,
        member_id=member.id,
        club_id=club.id,
        club_name=club.name,
        club_slug=club.slug,
        name=participant.name,
        email=participant.email,
        email_verified=participant.email_verified_at is not None,
        role="member",
        created_at=participant.created_at,
    )


def get_current_participant(request: Request, db: DatabaseSession) -> ParticipantAccount:
    session = get_participant_session(request)
    participant_id = session.get(SESSION_PARTICIPANT_ID)
    participant = (
        db.get(ParticipantAccount, participant_id)
        if isinstance(participant_id, int)
        else None
    )
    session_version = session.get(SESSION_PARTICIPANT_VERSION)
    if (
        participant is None
        or not participant.active
        or session_version != participant.session_version
    ):
        session.pop(SESSION_PARTICIPANT_ID, None)
        session.pop(SESSION_PARTICIPANT_VERSION, None)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in to your book club account",
        )
    return participant


CurrentParticipant = Annotated[ParticipantAccount, Depends(get_current_participant)]


def start_participant_session(
    request: Request, participant: ParticipantAccount, member: BookClubMember
) -> None:
    session = get_participant_session(request)
    session[SESSION_PARTICIPANT_ID] = participant.id
    session[SESSION_PARTICIPANT_VERSION] = participant.session_version
    session[SESSION_MEMBER_ID] = member.id


def end_participant_session(request: Request) -> None:
    session = get_participant_session(request)
    session.pop(SESSION_PARTICIPANT_ID, None)
    session.pop(SESSION_PARTICIPANT_VERSION, None)
    session.pop(SESSION_MEMBER_ID, None)


def require_participant_club(
    request: Request, participant: CurrentParticipant, db: DatabaseSession
) -> BookClub:
    """Resolve the signed-in participant's club and set db.info["bookclub_id"]
    the same way access.py's require_selected_club does for staff — lets any
    signed-in participant (member or owner) call club-scoped crud.py reads
    (e.g. listing books to rate). Management uses the primary app's
    require_selected_club dependency instead.
    """
    member_id = get_participant_session(request).get(SESSION_MEMBER_ID)
    member = db.scalar(
        select(BookClubMember).where(
            BookClubMember.id == member_id,
            BookClubMember.participant_account_id == participant.id,
            BookClubMember.active.is_(True),
        )
    ) if isinstance(member_id, int) else None
    club = db.get(BookClub, member.club_id) if member is not None else None
    if club is None:
        raise HTTPException(status_code=403, detail="You are not an active member of this club")
    db.info["bookclub_id"] = club.id
    db.info["bookclub"] = club
    return club


CurrentParticipantClub = Annotated[BookClub, Depends(require_participant_club)]


def current_participant_member(
    request: Request, participant: CurrentParticipant, db: DatabaseSession
) -> BookClubMember:
    member_id = get_participant_session(request).get(SESSION_MEMBER_ID)
    member = db.get(BookClubMember, member_id) if isinstance(member_id, int) else None
    if member is None or member.participant_account_id != participant.id:
        raise HTTPException(status_code=403, detail="Book club membership is required")
    return member


CurrentParticipantMember = Annotated[BookClubMember, Depends(current_participant_member)]
