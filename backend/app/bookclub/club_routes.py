from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from accounts.auth import CurrentUser
from bookclub import crud, schemas
from bookclub.access import accessible_club_statement, require_bookclub_tool, slugify
from bookclub.models import BookClub, BookClubAccess, BookClubBook, BookClubMeeting
from dependencies import DatabaseSession

router = APIRouter(prefix="/bookclub/clubs", tags=["book clubs"])
public_router = APIRouter(prefix="/api/public/clubs", tags=["public book clubs"])


def club_response(club: BookClub, role: str | None = None) -> schemas.ClubResponse:
    return schemas.ClubResponse(
        id=club.id,
        name=club.name,
        slug=club.slug,
        description=club.description,
        public=club.public,
        organizer_name=club.organizer_name,
        organizer_branch=club.organizer_branch,
        video_call_url=club.video_call_url,
        club_type=club.club_type,
        role=role,
    )


@router.get("", response_model=list[schemas.ClubResponse])
def list_clubs(
    user: Annotated[object, Depends(require_bookclub_tool)], db: DatabaseSession
):
    clubs = list(db.scalars(accessible_club_statement(user).order_by(BookClub.name)))
    roles = {
        access.club_id: access.role
        for access in db.scalars(
            select(BookClubAccess).where(BookClubAccess.user_id == user.id)
        )
    }
    return [club_response(club, "admin" if user.role == "admin" else roles.get(club.id)) for club in clubs]


@router.post("", response_model=schemas.ClubResponse, status_code=status.HTTP_201_CREATED)
def create_club(
    value: schemas.ClubCreate,
    user: Annotated[object, Depends(require_bookclub_tool)],
    db: DatabaseSession,
):
    base_slug = slugify(value.slug or value.name)
    slug = base_slug
    suffix = 2
    while db.scalar(select(BookClub.id).where(BookClub.slug == slug)) is not None:
        slug = f"{base_slug}-{suffix}"
        suffix += 1
    club = BookClub(**value.model_dump(exclude={"slug"}), slug=slug)
    club.access.append(BookClubAccess(user_id=user.id, role="owner"))
    db.add(club)
    try:
        db.commit()
        db.refresh(club)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="That club address is already in use") from exc
    db.info["bookclub_id"] = club.id
    crud.ensure_default_templates(db)
    return club_response(club, "owner")


@router.post("/{club_id}/select", response_model=schemas.ClubResponse)
def select_club(
    club_id: int,
    request: Request,
    user: Annotated[object, Depends(require_bookclub_tool)],
    db: DatabaseSession,
):
    club = db.scalar(accessible_club_statement(user).where(BookClub.id == club_id))
    if club is None:
        raise HTTPException(status_code=404, detail="Book club not found")
    request.session["bookclub_id"] = club.id
    return club_response(club)


@router.get("/selected", response_model=schemas.ClubResponse)
def selected_club(request: Request, user: CurrentUser, db: DatabaseSession):
    club_id = request.session.get("bookclub_id")
    club = (
        db.scalar(accessible_club_statement(user).where(BookClub.id == club_id))
        if isinstance(club_id, int)
        else None
    )
    if club is None:
        raise HTTPException(status_code=404, detail="No book club selected")
    return club_response(club)


@router.patch("/{club_id}", response_model=schemas.ClubResponse)
def update_club(
    club_id: int,
    value: schemas.ClubUpdate,
    user: Annotated[object, Depends(require_bookclub_tool)],
    db: DatabaseSession,
):
    club = db.scalar(accessible_club_statement(user).where(BookClub.id == club_id))
    if club is None:
        raise HTTPException(status_code=404, detail="Book club not found")
    data = value.model_dump(exclude_unset=True)
    if "slug" in data:
        data["slug"] = slugify(data["slug"])
    for field, item in data.items():
        setattr(club, field, item)
    try:
        db.commit()
        db.refresh(club)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="That club address is already in use") from exc
    return club_response(club)


SHELF_LIMIT = 60


@public_router.get("/{slug}", response_model=schemas.PublicClubResponse)
def public_club(slug: str, db: DatabaseSession):
    club = db.scalar(select(BookClub).where(BookClub.slug == slug, BookClub.public.is_(True)))
    if club is None:
        raise HTTPException(status_code=404, detail="Book club not found")
    today = date.today()
    meeting = db.scalar(
        select(BookClubMeeting)
        .options(selectinload(BookClubMeeting.book))
        .where(
            BookClubMeeting.club_id == club.id,
            BookClubMeeting.meeting_date >= today,
        )
        .order_by(BookClubMeeting.meeting_date, BookClubMeeting.id)
    )
    past_meetings = list(db.scalars(
        select(BookClubMeeting)
        .options(selectinload(BookClubMeeting.book))
        .where(
            BookClubMeeting.club_id == club.id,
            BookClubMeeting.meeting_date < today,
        )
        .order_by(BookClubMeeting.meeting_date.desc(), BookClubMeeting.id.desc())
        .limit(SHELF_LIMIT)
    ))
    shelf = [
        schemas.PublicShelfBookResponse(
            title=past.book.title,
            author=past.book.author,
            cover_image_url=past.book.cover_image_url,
            meeting_date=past.meeting_date,
        )
        for past in past_meetings
    ]
    remaining = SHELF_LIMIT - len(shelf)
    if remaining:
        scheduled_book_ids = set(
            db.scalars(
                select(BookClubMeeting.book_id).where(
                    BookClubMeeting.club_id == club.id
                )
            )
        )
        flagged_statement = select(BookClubBook).where(
            BookClubBook.club_id == club.id,
            BookClubBook.is_past_selection.is_(True),
        )
        if scheduled_book_ids:
            flagged_statement = flagged_statement.where(
                BookClubBook.id.not_in(scheduled_book_ids)
            )
        flagged_books = db.scalars(
            flagged_statement.order_by(BookClubBook.title, BookClubBook.id).limit(remaining)
        )
        shelf.extend(
            schemas.PublicShelfBookResponse(
                title=book.title,
                author=book.author,
                cover_image_url=book.cover_image_url,
            )
            for book in flagged_books
        )
    return schemas.PublicClubResponse(
        name=club.name,
        slug=club.slug,
        description=club.description,
        organizer_name=club.organizer_name,
        organizer_branch=club.organizer_branch,
        upcoming_meeting=meeting,
        shelf=shelf,
    )
