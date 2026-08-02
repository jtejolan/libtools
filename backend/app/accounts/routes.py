from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from accounts import auth, models, schemas
from dependencies import DatabaseSession
from security import hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["libtools-auth"])
admin_router = APIRouter(
    prefix="/api/admin/users",
    tags=["libtools-admin"],
    dependencies=[Depends(auth.require_platform_admin)],
)


@router.post("/login", response_model=schemas.UserResponse)
def login(
    credentials: schemas.LoginRequest,
    request: Request,
    db: DatabaseSession,
):
    user = auth.verify_login(db, credentials.username, credentials.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect name or password",
        )
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
    db.commit()
    request.session["libtools_session_version"] = user.session_version
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
    replacement = auth.issue_recovery_code(user)
    db.commit()
    return schemas.RecoveryCodeResponse(recovery_code=replacement)


@router.post("/recovery-code", response_model=schemas.RecoveryCodeResponse)
def replace_own_recovery_code(user: auth.CurrentUser, db: DatabaseSession):
    code = auth.issue_recovery_code(user)
    db.commit()
    return schemas.RecoveryCodeResponse(recovery_code=code)


@admin_router.get("", response_model=list[schemas.UserResponse])
def list_users(db: DatabaseSession):
    users = list(db.scalars(select(models.LibtoolsUser).order_by(models.LibtoolsUser.username)))
    return [auth.user_response(db, user) for user in users]


@admin_router.post(
    "", response_model=schemas.UserCreatedResponse, status_code=status.HTTP_201_CREATED
)
def create_user(value: schemas.UserCreate, db: DatabaseSession):
    user = models.LibtoolsUser(
        username=" ".join(value.username.split()),
        password_hash=hash_password(value.password),
        role=value.role,
    )
    db.add(user)
    code = auth.issue_recovery_code(user)
    auth.set_tools(db, user, value.tools)
    try:
        db.commit()
        db.refresh(user)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="That account name is already in use") from exc
    return schemas.UserCreatedResponse(
        **auth.user_response(db, user).model_dump(), recovery_code=code
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
