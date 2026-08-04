from datetime import date
import json
import logging
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from accounts import account_tokens, auth, email_delivery, login_throttle, models, schemas
from dependencies import DatabaseSession
from security import hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["libtools-auth"])
admin_router = APIRouter(
    prefix="/api/admin/users",
    tags=["libtools-admin"],
    dependencies=[Depends(auth.require_platform_admin)],
)
logger = logging.getLogger(__name__)


def _account_action_url(request: Request, path: str, token: str) -> str:
    base_url = str(request.base_url).rstrip("/")
    return f"{base_url}{path}?{urlencode({'token': token})}"


def _deliver_verification(request: Request, user: models.LibtoolsUser, token: str) -> bool:
    if user.email is None:
        return False
    try:
        return email_delivery.send_verification_email(
            recipient=user.email,
            username=user.username,
            verification_url=_account_action_url(request, "/verify-email", token),
        )
    except Exception:
        logger.exception("Could not hand off an account verification email")
        return False


def _deliver_password_reset(request: Request, user: models.LibtoolsUser, token: str) -> bool:
    if user.email is None:
        return False
    try:
        return email_delivery.send_password_reset_email(
            recipient=user.email,
            username=user.username,
            reset_url=_account_action_url(request, "/reset-password", token),
        )
    except Exception:
        logger.exception("Could not hand off a password reset email")
        return False


def _deliver_password_changed(user: models.LibtoolsUser) -> bool:
    if user.email is None:
        return False
    try:
        return email_delivery.send_password_changed_email(
            recipient=user.email,
            username=user.username,
        )
    except Exception:
        logger.exception("Could not hand off a password-changed confirmation email")
        return False


@router.post(
    "/register",
    response_model=schemas.RegistrationResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    value: schemas.RegistrationRequest,
    request: Request,
    db: DatabaseSession,
):
    if auth.get_user(db, value.username) is not None:
        raise HTTPException(status_code=409, detail="That account name is already in use")
    if value.email and auth.get_user_by_email(db, value.email) is not None:
        raise HTTPException(status_code=409, detail="That email address is already in use")

    user = models.LibtoolsUser(
        name=value.name,
        username=value.username,
        email=value.email,
        password_hash=hash_password(value.password),
        role="user",
    )
    db.add(user)
    recovery_code = auth.issue_recovery_code(user)
    verification_token = None
    try:
        db.flush()
        if user.email:
            verification_token = account_tokens.issue_token(
                db,
                user,
                account_tokens.EMAIL_VERIFICATION,
                account_tokens.EMAIL_VERIFICATION_LIFETIME,
            )
        db.commit()
        db.refresh(user)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="That account name or email address is already in use",
        ) from exc

    request.session["libtools_user_id"] = user.id
    request.session["libtools_session_version"] = user.session_version
    delivered = (
        _deliver_verification(request, user, verification_token)
        if verification_token
        else False
    )
    return schemas.RegistrationResponse(
        **auth.user_response(db, user).model_dump(),
        recovery_code=recovery_code,
        email_verification_required=user.email is not None,
        email_delivery_configured=delivered,
    )


@router.post("/login", response_model=schemas.UserResponse)
def login(
    credentials: schemas.LoginRequest,
    request: Request,
    db: DatabaseSession,
):
    throttle_key = auth.normalize_username(credentials.username)
    retry_after = login_throttle.seconds_until_unlocked(throttle_key)
    if retry_after > 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed sign-in attempts. Try again in a few minutes.",
            headers={"Retry-After": str(int(retry_after) + 1)},
        )
    user = auth.verify_login(db, credentials.username, credentials.password)
    if user is None:
        login_throttle.record_failure(throttle_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect name or password",
        )
    login_throttle.record_success(throttle_key)
    request.session["libtools_user_id"] = user.id
    request.session["libtools_session_version"] = user.session_version
    return auth.user_response(db, user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request) -> Response:
    request.session.pop("libtools_user_id", None)
    request.session.pop("libtools_session_version", None)
    request.session.pop("bookclub_id", None)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=schemas.UserResponse)
def me(user: auth.CurrentUser, db: DatabaseSession):
    return auth.user_response(db, user)


@router.get("/dashboard-summary", response_model=schemas.DashboardSummary)
def dashboard_summary(user: auth.CurrentUser, db: DatabaseSession):
    from bookclub.access import accessible_club_statement
    from bookclub.models import BookClub, BookClubAccess, BookClubMeeting
    from lendery import crud as lendery_crud
    from lendery.models import Component, LenderyItem

    inventory_counts = db.execute(
        select(
            func.count(LenderyItem.id),
            func.count(LenderyItem.id).filter(
                LenderyItem.availability_status == "checked_out"
            ),
            func.count(LenderyItem.id).filter(
                LenderyItem.availability_status == "available"
            ),
        ).where(LenderyItem.lifecycle_status != "removed")
    ).one()
    total_items, checked_out_items, available_items = inventory_counts

    attention_count = None
    if auth.has_tool_access(db, user, "lendery_manage"):
        open_cases = lendery_crud.list_open_maintenance_cases(db)
        open_case_item_ids = {case.item_id for case in open_cases}
        unavailable_filters = [
            LenderyItem.lifecycle_status != "removed",
            or_(
                LenderyItem.lifecycle_status == "unavailable",
                LenderyItem.availability_status == "unavailable",
            ),
        ]
        if open_case_item_ids:
            unavailable_filters.append(LenderyItem.id.not_in(open_case_item_ids))
        unresolved_unavailable = db.scalar(
            select(func.count(LenderyItem.id)).where(*unavailable_filters)
        ) or 0
        missing_components = (
            db.scalar(
                select(func.count(Component.id))
                .join(LenderyItem, Component.item_id == LenderyItem.id)
                .where(
                    Component.missing_reported_at.is_not(None),
                    LenderyItem.lifecycle_status != "removed",
                )
            )
            or 0
        )
        attention_count = len(open_cases) + unresolved_unavailable + missing_components

    has_bookclub_access = not user.must_change_password
    club_count = 0
    next_meeting = None
    if has_bookclub_access:
        club_count = db.scalar(
            select(func.count()).select_from(accessible_club_statement(user).subquery())
        ) or 0
        meeting_statement = (
            select(BookClubMeeting, BookClub.name)
            .join(BookClub, BookClub.id == BookClubMeeting.club_id)
            .where(BookClubMeeting.meeting_date >= date.today())
        )
        if user.role != "admin":
            meeting_statement = meeting_statement.join(
                BookClubAccess, BookClubAccess.club_id == BookClub.id
            ).where(BookClubAccess.user_id == user.id)
        meeting_row = db.execute(
            meeting_statement.order_by(
                BookClubMeeting.meeting_date,
                BookClubMeeting.id,
            ).limit(1)
        ).first()
        if meeting_row is not None:
            meeting, club_name = meeting_row
            next_meeting = schemas.DashboardMeetingSummary(
                club_id=meeting.club_id,
                club_name=club_name,
                meeting_id=meeting.id,
                meeting_date=meeting.meeting_date,
                days_until=(meeting.meeting_date - date.today()).days,
                meeting_time=meeting.meeting_time,
                location=meeting.location,
                book_title=meeting.book_title,
            )

    return schemas.DashboardSummary(
        lendery=schemas.DashboardLenderySummary(
            total_items=total_items,
            checked_out_items=checked_out_items,
            available_items=available_items,
            attention_count=attention_count,
        ),
        bookclub=schemas.DashboardBookClubSummary(
            has_access=has_bookclub_access,
            club_count=club_count,
            next_meeting=next_meeting,
        ),
    )


@router.put(
    "/quick-actions",
    response_model=schemas.QuickActionsResponse,
)
def update_quick_actions(
    value: schemas.QuickActionsUpdate,
    user: auth.CurrentUser,
    db: DatabaseSession,
):
    unavailable = set(value.actions) - auth.available_quick_actions(db, user)
    if unavailable:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="One or more shortcuts require additional access",
        )
    user.quick_actions = json.dumps(value.actions)
    db.commit()
    return schemas.QuickActionsResponse(quick_actions=value.actions)


@router.put("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    value: schemas.ChangePasswordRequest,
    request: Request,
    user: auth.CurrentUser,
    db: DatabaseSession,
) -> Response:
    if not verify_password(value.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    user.password_hash = hash_password(value.password)
    user.must_change_password = False
    user.session_version += 1
    account_tokens.revoke_tokens(db, user, account_tokens.PASSWORD_RESET)
    db.commit()
    request.session["libtools_session_version"] = user.session_version
    _deliver_password_changed(user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/recover", response_model=schemas.RecoveryCodeResponse)
def recover(value: schemas.RecoveryResetRequest, db: DatabaseSession):
    user = auth.get_user(db, value.username)
    valid = (
        user is not None
        and user.active
        and user.recovery_code_hash is not None
        and verify_password(value.recovery_code.upper(), user.recovery_code_hash)
    )
    if not valid or user is None:
        raise HTTPException(status_code=400, detail="Recovery details are incorrect")
    user.password_hash = hash_password(value.password)
    user.must_change_password = False
    user.session_version += 1
    account_tokens.revoke_tokens(db, user, account_tokens.PASSWORD_RESET)
    replacement = auth.issue_recovery_code(user)
    db.commit()
    return schemas.RecoveryCodeResponse(recovery_code=replacement)


@router.post("/recovery-code", response_model=schemas.RecoveryCodeResponse)
def replace_own_recovery_code(user: auth.CurrentUser, db: DatabaseSession):
    code = auth.issue_recovery_code(user)
    db.commit()
    return schemas.RecoveryCodeResponse(recovery_code=code)


@router.post(
    "/email-verification/request",
    response_model=schemas.EmailActionResponse,
)
def request_email_verification(
    request: Request,
    user: auth.CurrentUser,
    db: DatabaseSession,
):
    if user.email is None:
        raise HTTPException(status_code=409, detail="This account has no email address")
    if user.email_verified_at is not None:
        raise HTTPException(status_code=409, detail="This email address is already verified")
    token = account_tokens.issue_token(
        db,
        user,
        account_tokens.EMAIL_VERIFICATION,
        account_tokens.EMAIL_VERIFICATION_LIFETIME,
    )
    db.commit()
    _deliver_verification(request, user, token)
    return schemas.EmailActionResponse(
        message="Check your email for a verification link.",
        delivery_configured=email_delivery.DELIVERY_CONFIGURED,
    )


@router.post("/verify-email", response_model=schemas.UserResponse)
def verify_email(value: schemas.VerifyEmailRequest, db: DatabaseSession):
    token = account_tokens.consume_token(
        db,
        value.token,
        account_tokens.EMAIL_VERIFICATION,
    )
    if token is None:
        raise HTTPException(
            status_code=400,
            detail="This verification link is invalid or has expired",
        )
    user = token.user
    user.email_verified_at = token.used_at
    db.commit()
    db.refresh(user)
    return auth.user_response(db, user)


@router.post(
    "/password-reset/request",
    response_model=schemas.EmailActionResponse,
)
def request_password_reset(
    value: schemas.PasswordResetEmailRequest,
    request: Request,
    db: DatabaseSession,
):
    user = auth.get_user_by_email(db, value.email)
    if (
        user is not None
        and user.active
        and user.email_verified_at is not None
    ):
        token = account_tokens.issue_token(
            db,
            user,
            account_tokens.PASSWORD_RESET,
            account_tokens.PASSWORD_RESET_LIFETIME,
        )
        db.commit()
        _deliver_password_reset(request, user, token)
    return schemas.EmailActionResponse(
        message=(
            "If that address belongs to a verified account, "
            "a password reset link will be sent."
        ),
        delivery_configured=email_delivery.DELIVERY_CONFIGURED,
    )


@router.post(
    "/password-reset/confirm",
    status_code=status.HTTP_204_NO_CONTENT,
)
def confirm_password_reset(
    value: schemas.PasswordResetConfirmRequest,
    db: DatabaseSession,
) -> Response:
    token = account_tokens.consume_token(
        db,
        value.token,
        account_tokens.PASSWORD_RESET,
    )
    if token is None:
        raise HTTPException(
            status_code=400,
            detail="This password reset link is invalid or has expired",
        )
    user = token.user
    if not user.active:
        raise HTTPException(status_code=400, detail="This account is disabled")
    user.password_hash = hash_password(value.password)
    user.must_change_password = False
    user.session_version += 1
    db.commit()
    _deliver_password_changed(user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@admin_router.get("", response_model=list[schemas.UserResponse])
def list_users(db: DatabaseSession):
    users = list(db.scalars(select(models.LibtoolsUser).order_by(models.LibtoolsUser.username)))
    return [auth.user_response(db, user) for user in users]


@admin_router.post(
    "", response_model=schemas.UserCreatedResponse, status_code=status.HTTP_201_CREATED
)
def create_user(
    value: schemas.UserCreate,
    request: Request,
    db: DatabaseSession,
):
    if auth.get_user(db, value.username) is not None:
        raise HTTPException(status_code=409, detail="That account name is already in use")
    if value.email and auth.get_user_by_email(db, value.email) is not None:
        raise HTTPException(status_code=409, detail="That email address is already in use")
    user = models.LibtoolsUser(
        name=value.name,
        username=value.username,
        email=value.email,
        password_hash=hash_password(value.password),
        role=value.role,
    )
    db.add(user)
    code = auth.issue_recovery_code(user)
    auth.set_tools(db, user, value.tools)
    verification_token = None
    try:
        db.flush()
        if user.email:
            verification_token = account_tokens.issue_token(
                db,
                user,
                account_tokens.EMAIL_VERIFICATION,
                account_tokens.EMAIL_VERIFICATION_LIFETIME,
            )
        db.commit()
        db.refresh(user)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="That account name or email address is already in use",
        ) from exc
    delivered = (
        _deliver_verification(request, user, verification_token)
        if verification_token
        else False
    )
    return schemas.UserCreatedResponse(
        **auth.user_response(db, user).model_dump(),
        recovery_code=code,
        email_verification_required=user.email is not None,
        email_delivery_configured=delivered,
    )


@admin_router.patch("/{user_id}", response_model=schemas.UserResponse)
def update_user(
    user_id: int,
    value: schemas.UserUpdate,
    db: DatabaseSession,
    admin: Annotated[models.LibtoolsUser, Depends(auth.require_platform_admin)],
):
    user = db.get(models.LibtoolsUser, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    data = value.model_dump(exclude_unset=True)
    if user.id == admin.id and data.get("active") is False:
        raise HTTPException(status_code=409, detail="You cannot disable your own account")
    if user.id == admin.id and data.get("role") == "user":
        raise HTTPException(status_code=409, detail="You cannot remove your own administrator access")
    tools = data.pop("tools", None)
    for field, item in data.items():
        setattr(user, field, item)
    if tools is not None:
        auth.set_tools(db, user, tools)
    db.commit()
    return auth.user_response(db, user)


@admin_router.post("/{user_id}/password", response_model=schemas.RecoveryCodeResponse)
def reset_user_password(
    user_id: int, value: schemas.AdminPasswordResetRequest, db: DatabaseSession
):
    user = db.get(models.LibtoolsUser, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    user.password_hash = hash_password(value.password)
    user.must_change_password = True
    user.session_version += 1
    account_tokens.revoke_tokens(db, user, account_tokens.PASSWORD_RESET)
    code = auth.issue_recovery_code(user)
    db.commit()
    return schemas.RecoveryCodeResponse(recovery_code=code)


@admin_router.post("/{user_id}/recovery-code", response_model=schemas.RecoveryCodeResponse)
def replace_recovery_code(user_id: int, db: DatabaseSession):
    user = db.get(models.LibtoolsUser, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    code = auth.issue_recovery_code(user)
    db.commit()
    return schemas.RecoveryCodeResponse(recovery_code=code)
