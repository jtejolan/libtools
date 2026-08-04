import re
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import or_, select

from accounts.auth import CurrentUser
from bookclub.models import BookClub, BookClubAccess
from dependencies import DatabaseSession


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug or "book-club"


def accessible_club_statement(user: CurrentUser):
    statement = select(BookClub)
    if user.role != "admin":
        statement = statement.join(BookClubAccess).where(BookClubAccess.user_id == user.id)
    return statement


def require_bookclub_tool(user: CurrentUser):
    if user.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Change your temporary password before continuing",
        )
    return user


BookClubUser = Annotated[object, Depends(require_bookclub_tool)]


def require_selected_club(
    request: Request,
    user: Annotated[object, Depends(require_bookclub_tool)],
    db: DatabaseSession,
) -> BookClub:
    club_id = request.session.get("bookclub_id")
    if not isinstance(club_id, int):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Choose a book club first",
        )
    statement = accessible_club_statement(user).where(BookClub.id == club_id)
    club = db.scalar(statement)
    if club is None:
        request.session.pop("bookclub_id", None)
        raise HTTPException(status_code=403, detail="You cannot access this book club")
    db.info["bookclub_id"] = club.id
    db.info["bookclub"] = club
    return club


SelectedClub = Annotated[BookClub, Depends(require_selected_club)]
