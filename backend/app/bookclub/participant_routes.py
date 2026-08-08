import logging
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from accounts import login_throttle
from bookclub import participant_auth, participant_email_delivery, participant_tokens
from bookclub.access import slugify
from bookclub.models import BookClub
from bookclub.participant_models import ParticipantAccount
from bookclub.participant_schemas import (
    ParticipantClubCreateRequest,
    ParticipantEmailActionResponse,
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
club_router = APIRouter(prefix="/participant/clubs", tags=["bookclub-participant-clubs"])
logger = logging.getLogger(__name__)


def _get_public_club(db: DatabaseSession, slug: str) -> BookClub:
    club = db.scalar(select(BookClub).where(BookClub.slug == slug, BookClub.public.is_(True)))
    if club is None:
        raise HTTPException(status_code=404, detail="Book club not found")
    return club


def _account_action_url(request: Request, path: str, token: str) -> str:
    base_url = str(request.base_url).rstrip("/")
    return f"{base_url}{path}?{urlencode({'token': token})}"


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


def _deliver_password_changed(club: BookClub, participant: ParticipantAccount) -> bool:
    try:
        return participant_email_delivery.send_password_changed_email(
            recipient=participant.email, name=participant.name, club_name=club.name
        )
    except Exception:
        logger.exception("Could not hand off a participant password-changed email")
        return False


@router.post(
    "/register",
    response_model=ParticipantResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(value: ParticipantRegistrationRequest, request: Request, db: DatabaseSession):
    throttle_key = f"bookclub-participant-register:{request.client.host if request.client else 'unknown'}"
    retry_after = login_throttle.seconds_until_unlocked(throttle_key)
    if retry_after > 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Try again in a few minutes.",
            headers={"Retry-After": str(int(retry_after) + 1)},
        )
    login_throttle.record_failure(throttle_key)

    club = _get_public_club(db, value.club_slug)
    if participant_auth.get_participant_by_email(db, club, value.email) is not None:
        raise HTTPException(status_code=409, detail="That email address is already registered for this club")

    participant = ParticipantAccount(
        club_id=club.id,
        name=value.name,
        email=value.email,
        password_hash=hash_password(value.password),
    )
    db.add(participant)
    try:
        db.flush()
        verification_token = participant_tokens.issue_token(
            db,
            participant,
            participant_tokens.EMAIL_VERIFICATION,
            participant_tokens.EMAIL_VERIFICATION_LIFETIME,
        )
        db.commit()
        db.refresh(participant)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="That email address is already registered for this club"
        ) from exc

    participant_auth.start_participant_session(request, participant)
    _deliver_verification(request, club, participant, verification_token)
    return participant_auth.participant_response(participant, club)


@router.post("/login", response_model=ParticipantResponse)
def login(value: ParticipantLoginRequest, request: Request, db: DatabaseSession):
    club = _get_public_club(db, value.club_slug)
    throttle_key = f"bookclub-participant-login:{club.id}:{value.email}"
    retry_after = login_throttle.seconds_until_unlocked(throttle_key)
    if retry_after > 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed sign-in attempts. Try again in a few minutes.",
            headers={"Retry-After": str(int(retry_after) + 1)},
        )
    participant = participant_auth.verify_participant_login(db, club, value.email, value.password)
    if participant is None:
        login_throttle.record_failure(throttle_key)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")
    login_throttle.record_success(throttle_key)
    participant_auth.start_participant_session(request, participant)
    return participant_auth.participant_response(participant, club)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request) -> Response:
    participant_auth.end_participant_session(request)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=ParticipantResponse)
def me(participant: participant_auth.CurrentParticipant, db: DatabaseSession):
    club = db.get(BookClub, participant.club_id)
    return participant_auth.participant_response(participant, club)


@router.post("/email-verification/request", response_model=ParticipantEmailActionResponse)
def request_email_verification(
    request: Request, participant: participant_auth.CurrentParticipant, db: DatabaseSession
):
    if participant.email_verified_at is not None:
        raise HTTPException(status_code=409, detail="This email address is already verified")
    club = db.get(BookClub, participant.club_id)
    token = participant_tokens.issue_token(
        db, participant, participant_tokens.EMAIL_VERIFICATION, participant_tokens.EMAIL_VERIFICATION_LIFETIME
    )
    db.commit()
    _deliver_verification(request, club, participant, token)
    return ParticipantEmailActionResponse(
        message="Check your email for a verification link.",
        delivery_configured=participant_email_delivery.DELIVERY_CONFIGURED,
    )


@router.post("/verify-email", response_model=ParticipantResponse)
def verify_email(value: ParticipantVerifyEmailRequest, db: DatabaseSession):
    token = participant_tokens.consume_token(db, value.token, participant_tokens.EMAIL_VERIFICATION)
    if token is None:
        raise HTTPException(status_code=400, detail="This verification link is invalid or has expired")
    participant = token.participant
    participant.email_verified_at = token.used_at
    db.commit()
    db.refresh(participant)
    club = db.get(BookClub, participant.club_id)
    return participant_auth.participant_response(participant, club)


@router.post("/password-reset/request", response_model=ParticipantEmailActionResponse)
def request_password_reset(value: ParticipantPasswordResetEmailRequest, request: Request, db: DatabaseSession):
    club = _get_public_club(db, value.club_slug)
    participant = participant_auth.get_participant_by_email(db, club, value.email)
    if participant is not None and participant.active and participant.email_verified_at is not None:
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
    club = db.get(BookClub, participant.club_id)
    _deliver_password_changed(club, participant)
    # Unlike accounts' /auth/password-reset/confirm (204), this returns the
    # participant so the frontend can link straight to this club's login
    # page — there's no single global /login on this subdomain to fall
    # back to, since participant sign-in is per-club.
    return participant_auth.participant_response(participant, club)


@club_router.post("", response_model=ParticipantResponse, status_code=status.HTTP_201_CREATED)
def create_club(value: ParticipantClubCreateRequest, request: Request, db: DatabaseSession):
    """Create a self-serve club and its owner account together.

    Mirrors club_routes.create_club's slug-collision retry, but for the
    participant-owner path: there's no existing LibtoolsUser/club to attach
    to, so both rows are created in one request. Deliberately does NOT call
    crud.ensure_default_templates — its DEFAULT_TEMPLATES are hardcoded
    library-specific content (physical pickup/transfer, a named organizer),
    meaningless for a self-serve club; sensible self-serve defaults are a
    later phase's concern.
    """
    throttle_key = f"bookclub-participant-create-club:{request.client.host if request.client else 'unknown'}"
    retry_after = login_throttle.seconds_until_unlocked(throttle_key)
    if retry_after > 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Try again in a few minutes.",
            headers={"Retry-After": str(int(retry_after) + 1)},
        )
    login_throttle.record_failure(throttle_key)

    base_slug = slugify(value.club_slug or value.club_name)
    slug = base_slug
    suffix = 2
    while db.scalar(select(BookClub.id).where(BookClub.slug == slug)) is not None:
        slug = f"{base_slug}-{suffix}"
        suffix += 1

    club = BookClub(
        name=value.club_name,
        slug=slug,
        description=value.club_description,
        public=True,
        club_type="self_serve",
    )
    db.add(club)
    try:
        db.flush()
        participant = ParticipantAccount(
            club_id=club.id,
            name=value.facilitator_name,
            email=value.facilitator_email,
            password_hash=hash_password(value.password),
            role="owner",
        )
        db.add(participant)
        db.flush()
        verification_token = participant_tokens.issue_token(
            db,
            participant,
            participant_tokens.EMAIL_VERIFICATION,
            participant_tokens.EMAIL_VERIFICATION_LIFETIME,
        )
        db.commit()
        db.refresh(participant)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="That club address is already in use"
        ) from exc

    participant_auth.start_participant_session(request, participant)
    _deliver_verification(request, club, participant, verification_token)
    return participant_auth.participant_response(participant, club)
