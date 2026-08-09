import logging
from datetime import date
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from accounts import login_throttle
from bookclub import participant_auth, participant_email_delivery, participant_tokens
from bookclub.models import BookClub, BookClubMember
from bookclub.participant_models import ParticipantAccount
from bookclub.participant_schemas import (
    ParticipantEmailActionResponse,
    ParticipantClubResponse,
    ParticipantGlobalLoginRequest,
    ParticipantLoginRequest,
    ParticipantPasswordResetConfirmRequest,
    ParticipantPasswordResetEmailRequest,
    ParticipantRegistrationRequest,
    ParticipantResponse,
    ParticipantVerifyEmailRequest,
)
from dependencies import DatabaseSession
from security import hash_password

router = APIRouter(prefix="/participant/auth", tags=["bookclub-participant-auth"])
logger = logging.getLogger(__name__)


def _get_public_club(db: DatabaseSession, slug: str) -> BookClub:
    club = db.scalar(select(BookClub).where(BookClub.slug == slug, BookClub.public.is_(True)))
    if club is None:
        raise HTTPException(status_code=404, detail="Book club not found")
    return club


def _member_by_email(db: DatabaseSession, club: BookClub, email: str) -> BookClubMember | None:
    return db.scalar(
        select(BookClubMember).where(
            BookClubMember.club_id == club.id,
            func.lower(BookClubMember.email) == email.casefold(),
        )
    )


def _membership_for_account(
    db: DatabaseSession, club: BookClub, participant: ParticipantAccount
) -> BookClubMember:
    member = db.scalar(
        select(BookClubMember).where(
            BookClubMember.club_id == club.id,
            BookClubMember.participant_account_id == participant.id,
        )
    )
    if member is not None:
        if not member.active:
            raise HTTPException(status_code=403, detail="Your membership in this club is inactive")
        return member

    # A facilitator may have entered this reader before they created their
    # global portal login. A successful password login proves ownership of
    # the account email, so it is safe to claim the matching roster entry.
    member = _member_by_email(db, club, participant.email)
    if member is not None:
        if not member.active:
            raise HTTPException(status_code=403, detail="Your membership in this club is inactive")
        if club.enrollment_policy == "closed":
            raise HTTPException(status_code=403, detail="This club is not activating new participant accounts")
        if member.participant_account_id not in (None, participant.id):
            raise HTTPException(status_code=409, detail="That roster entry is linked to another account")
        member.participant_account_id = participant.id
    elif club.enrollment_policy == "open":
        member = BookClubMember(
            club_id=club.id,
            name=participant.name,
            email=participant.email,
            joined_on=date.today(),
            delivery_method="none",
            participant_account_id=participant.id,
        )
        db.add(member)
    elif club.enrollment_policy == "invite_only":
        raise HTTPException(
            status_code=403,
            detail="This club is invitation only. Ask the facilitator to add your email to the roster.",
        )
    else:
        raise HTTPException(status_code=403, detail="This club is not accepting new participants")
    db.commit()
    db.refresh(member)
    return member


def _memberships_for_account(
    db: DatabaseSession, participant: ParticipantAccount
) -> list[tuple[BookClubMember, BookClub]]:
    """Return every active portal membership and claim matching roster rows.

    Password authentication proves control of the participant account email,
    so this mirrors the existing club-specific login behavior across all
    public clubs in one step.
    """
    rows = list(
        db.execute(
            select(BookClubMember, BookClub)
            .join(BookClub, BookClub.id == BookClubMember.club_id)
            .where(
                BookClubMember.active.is_(True),
                BookClub.public.is_(True),
                or_(
                    BookClubMember.participant_account_id == participant.id,
                    (
                        BookClubMember.participant_account_id.is_(None)
                        & (func.lower(BookClubMember.email) == participant.email.casefold())
                        & (BookClub.enrollment_policy != "closed")
                    ),
                ),
            )
            .order_by(BookClub.name, BookClub.id)
        )
    )
    claimed = False
    for member, _club in rows:
        if member.participant_account_id is None:
            member.participant_account_id = participant.id
            claimed = True
    if claimed:
        db.commit()
    return rows


def _club_summary(club: BookClub) -> ParticipantClubResponse:
    return ParticipantClubResponse(
        id=club.id,
        name=club.name,
        slug=club.slug,
        description=club.description,
        organizer_name=club.organizer_name,
        organizer_branch=club.organizer_branch,
    )


def _account_action_url(request: Request, path: str, token: str) -> str:
    return f"{str(request.base_url).rstrip('/')}{path}?{urlencode({'token': token})}"


def _deliver_verification(request: Request, club: BookClub, participant: ParticipantAccount, token: str) -> bool:
    try:
        return participant_email_delivery.send_verification_email(
            recipient=participant.email,
            name=participant.name,
            club_name=club.name,
            verification_url=_account_action_url(request, "/verify-email", token),
        )
    except Exception:
        logger.exception("Could not hand off a participant verification email")
        return False


def _deliver_password_reset(request: Request, club: BookClub, participant: ParticipantAccount, token: str) -> bool:
    try:
        return participant_email_delivery.send_password_reset_email(
            recipient=participant.email,
            name=participant.name,
            club_name=club.name,
            reset_url=_account_action_url(request, "/reset-password", token),
        )
    except Exception:
        logger.exception("Could not hand off a participant password reset email")
        return False


@router.post("/register", response_model=ParticipantResponse, status_code=status.HTTP_201_CREATED)
def register(value: ParticipantRegistrationRequest, request: Request, db: DatabaseSession):
    throttle_key = f"bookclub-participant-register:{request.client.host if request.client else 'unknown'}"
    retry_after = login_throttle.seconds_until_unlocked(throttle_key)
    if retry_after > 0:
        raise HTTPException(
            status_code=429,
            detail="Too many attempts. Try again in a few minutes.",
            headers={"Retry-After": str(int(retry_after) + 1)},
        )
    login_throttle.record_failure(throttle_key)
    club = _get_public_club(db, value.club_slug)
    if participant_auth.get_participant_by_email(db, value.email) is not None:
        raise HTTPException(
            status_code=409,
            detail="An account with that email already exists. Sign in to link this club.",
        )

    member = _member_by_email(db, club, value.email)
    if club.enrollment_policy == "closed":
        raise HTTPException(status_code=403, detail="This club is not accepting new participant accounts")
    if club.enrollment_policy == "invite_only" and member is None:
        raise HTTPException(
            status_code=403,
            detail="This club is invitation only. Use the email address your facilitator added to the roster.",
        )
    if member is not None and member.participant_account_id is not None:
        raise HTTPException(status_code=409, detail="That roster entry already has an account")
    participant = ParticipantAccount(
        name=value.name, email=value.email, password_hash=hash_password(value.password)
    )
    db.add(participant)
    try:
        db.flush()
        if member is None:
            member = BookClubMember(
                club_id=club.id,
                name=value.name,
                email=value.email,
                joined_on=date.today(),
                delivery_method="none",
                participant_account_id=participant.id,
            )
            db.add(member)
        else:
            member.participant_account_id = participant.id
        db.flush()
        verification_token = participant_tokens.issue_token(
            db,
            participant,
            participant_tokens.EMAIL_VERIFICATION,
            participant_tokens.EMAIL_VERIFICATION_LIFETIME,
        )
        db.commit()
        db.refresh(participant)
        db.refresh(member)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="That email address is already registered") from exc

    login_throttle.record_success(throttle_key)
    participant_auth.start_participant_session(request, participant, member)
    _deliver_verification(request, club, participant, verification_token)
    return participant_auth.participant_response(participant, club, member)


@router.post("/login", response_model=ParticipantResponse)
def login(value: ParticipantLoginRequest, request: Request, db: DatabaseSession):
    club = _get_public_club(db, value.club_slug)
    throttle_key = f"bookclub-participant-login:{value.email}"
    retry_after = login_throttle.seconds_until_unlocked(throttle_key)
    if retry_after > 0:
        raise HTTPException(
            status_code=429,
            detail="Too many failed sign-in attempts. Try again in a few minutes.",
            headers={"Retry-After": str(int(retry_after) + 1)},
        )
    participant = participant_auth.verify_participant_login(db, value.email, value.password)
    if participant is None:
        login_throttle.record_failure(throttle_key)
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    member = _membership_for_account(db, club, participant)
    login_throttle.record_success(throttle_key)
    participant_auth.start_participant_session(request, participant, member)
    return participant_auth.participant_response(participant, club, member)


@router.post("/login/global", response_model=list[ParticipantClubResponse])
def global_login(
    value: ParticipantGlobalLoginRequest, request: Request, db: DatabaseSession
):
    throttle_key = f"bookclub-participant-login:{value.email}"
    retry_after = login_throttle.seconds_until_unlocked(throttle_key)
    if retry_after > 0:
        raise HTTPException(
            status_code=429,
            detail="Too many failed sign-in attempts. Try again in a few minutes.",
            headers={"Retry-After": str(int(retry_after) + 1)},
        )
    participant = participant_auth.verify_participant_login(db, value.email, value.password)
    if participant is None:
        login_throttle.record_failure(throttle_key)
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    login_throttle.record_success(throttle_key)
    memberships = _memberships_for_account(db, participant)
    if not memberships:
        raise HTTPException(status_code=403, detail="This account has no active book club memberships")
    participant_auth.start_participant_session(request, participant, memberships[0][0])
    return [_club_summary(club) for _member, club in memberships]


@router.get("/clubs", response_model=list[ParticipantClubResponse])
def participant_clubs(
    participant: participant_auth.CurrentParticipant, db: DatabaseSession
):
    return [_club_summary(club) for _member, club in _memberships_for_account(db, participant)]


@router.post("/clubs/{slug}/select", response_model=ParticipantResponse)
def select_participant_club(
    slug: str,
    request: Request,
    participant: participant_auth.CurrentParticipant,
    db: DatabaseSession,
):
    memberships = _memberships_for_account(db, participant)
    selected = next(((member, club) for member, club in memberships if club.slug == slug), None)
    if selected is None:
        raise HTTPException(status_code=404, detail="Book club membership not found")
    member, club = selected
    participant_auth.start_participant_session(request, participant, member)
    return participant_auth.participant_response(participant, club, member)


@router.post("/clubs/{slug}/join", response_model=ParticipantResponse)
def join_participant_club(
    slug: str,
    request: Request,
    participant: participant_auth.CurrentParticipant,
    db: DatabaseSession,
):
    club = _get_public_club(db, slug)
    member = _membership_for_account(db, club, participant)
    participant_auth.start_participant_session(request, participant, member)
    return participant_auth.participant_response(participant, club, member)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request) -> Response:
    participant_auth.end_participant_session(request)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=ParticipantResponse)
def me(
    participant: participant_auth.CurrentParticipant,
    member: participant_auth.CurrentParticipantMember,
    db: DatabaseSession,
):
    club = db.get(BookClub, member.club_id)
    return participant_auth.participant_response(participant, club, member)


@router.post("/email-verification/request", response_model=ParticipantEmailActionResponse)
def request_email_verification(
    request: Request,
    participant: participant_auth.CurrentParticipant,
    member: participant_auth.CurrentParticipantMember,
    db: DatabaseSession,
):
    if participant.email_verified_at is not None:
        raise HTTPException(status_code=409, detail="This email address is already verified")
    club = db.get(BookClub, member.club_id)
    token = participant_tokens.issue_token(
        db, participant, participant_tokens.EMAIL_VERIFICATION, participant_tokens.EMAIL_VERIFICATION_LIFETIME
    )
    db.commit()
    _deliver_verification(request, club, participant, token)
    return ParticipantEmailActionResponse(
        message="Check your email for a verification link.",
        delivery_configured=participant_email_delivery.DELIVERY_CONFIGURED,
    )


def _first_membership(db: DatabaseSession, participant: ParticipantAccount) -> tuple[BookClubMember, BookClub]:
    member = db.scalar(
        select(BookClubMember)
        .where(BookClubMember.participant_account_id == participant.id)
        .order_by(BookClubMember.id)
    )
    if member is None:
        raise HTTPException(status_code=403, detail="This account has no book club membership")
    return member, db.get(BookClub, member.club_id)


@router.post("/verify-email", response_model=ParticipantResponse)
def verify_email(value: ParticipantVerifyEmailRequest, db: DatabaseSession):
    token = participant_tokens.consume_token(db, value.token, participant_tokens.EMAIL_VERIFICATION)
    if token is None:
        raise HTTPException(status_code=400, detail="This verification link is invalid or has expired")
    participant = token.participant
    participant.email_verified_at = token.used_at
    db.commit()
    db.refresh(participant)
    member, club = _first_membership(db, participant)
    return participant_auth.participant_response(participant, club, member)


@router.post("/password-reset/request", response_model=ParticipantEmailActionResponse)
def request_password_reset(value: ParticipantPasswordResetEmailRequest, request: Request, db: DatabaseSession):
    club = _get_public_club(db, value.club_slug)
    participant = participant_auth.get_participant_by_email(db, value.email)
    if participant is not None and participant.active and participant.email_verified_at is not None:
        member = _member_by_email(db, club, value.email)
        if member is not None and member.participant_account_id == participant.id:
            token = participant_tokens.issue_token(
                db, participant, participant_tokens.PASSWORD_RESET, participant_tokens.PASSWORD_RESET_LIFETIME
            )
            db.commit()
            _deliver_password_reset(request, club, participant, token)
    return ParticipantEmailActionResponse(
        message="If that address belongs to a verified account, a password reset link will be sent.",
        delivery_configured=participant_email_delivery.DELIVERY_CONFIGURED,
    )


@router.post("/password-reset/confirm", response_model=ParticipantResponse)
def confirm_password_reset(value: ParticipantPasswordResetConfirmRequest, db: DatabaseSession):
    token = participant_tokens.consume_token(db, value.token, participant_tokens.PASSWORD_RESET)
    if token is None:
        raise HTTPException(status_code=400, detail="This password reset link is invalid or has expired")
    participant = token.participant
    if not participant.active:
        raise HTTPException(status_code=400, detail="This account is disabled")
    participant.password_hash = hash_password(value.password)
    participant.session_version += 1
    db.commit()
    db.refresh(participant)
    member, club = _first_membership(db, participant)
    try:
        participant_email_delivery.send_password_changed_email(
            recipient=participant.email, name=participant.name, club_name=club.name
        )
    except Exception:
        logger.exception("Could not hand off a participant password-changed email")
    return participant_auth.participant_response(participant, club, member)
