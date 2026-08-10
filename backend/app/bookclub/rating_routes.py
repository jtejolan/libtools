from fastapi import APIRouter, HTTPException, Response, status

from bookclub import crud, models, schemas
from bookclub.participant_auth import CurrentParticipant, CurrentParticipantClub, CurrentParticipantMember
from bookclub.participant_schemas import BookRatingsResponse, RatingResponse, RatingSubmit
from dependencies import DatabaseSession

# Participant-facing: any signed-in participant (member or owner) can browse
# their club's books and rate the ones they've read. Ratings are visible to
# every participant in the club, not just an aggregate — see
# docs/backend/bookclub.md.

router = APIRouter(prefix="/participant/books", tags=["bookclub-participant-ratings"])


def _not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def _ratings_response(book_id: int, rows: list[tuple]) -> BookRatingsResponse:
    ratings = [
        RatingResponse(
            id=rating.id,
            book_id=rating.book_id,
            participant_id=rating.participant_id,
            participant_name=name,
            rating=rating.rating,
            review_text=rating.review_text,
            created_at=rating.created_at,
            updated_at=rating.updated_at,
        )
        for rating, name in rows
    ]
    average = round(sum(item.rating for item in ratings) / len(ratings), 2) if ratings else None
    return BookRatingsResponse(book_id=book_id, average=average, count=len(ratings), ratings=ratings)


@router.get("", response_model=list[schemas.BookResponse])
def list_books(club: CurrentParticipantClub, db: DatabaseSession):
    return crud.list_books(db, limit=500)


@router.get("/{book_id}/ratings", response_model=BookRatingsResponse)
def get_ratings(book_id: int, club: CurrentParticipantClub, db: DatabaseSession):
    if crud.get_book(db, book_id) is None:
        raise _not_found("Book not found")
    return _ratings_response(book_id, crud.get_book_ratings(db, book_id))


@router.put("/{book_id}/rating", response_model=BookRatingsResponse)
def submit_rating(
    book_id: int,
    value: RatingSubmit,
    participant: CurrentParticipant,
    member: CurrentParticipantMember,
    club: CurrentParticipantClub,
    db: DatabaseSession,
):
    if crud.get_book(db, book_id) is None:
        raise _not_found("Book not found")
    rating = crud.upsert_rating(db, book_id, participant.id, value)
    db.add(models.BookClubActivity(
        club_id=club.id,
        member_id=member.id,
        book_id=book_id,
        kind="rating",
        detail=f"{value.rating:g} stars",
        reference_id=rating.id,
    ))
    db.commit()
    return _ratings_response(book_id, crud.get_book_ratings(db, book_id))


@router.delete("/{book_id}/rating", status_code=status.HTTP_204_NO_CONTENT)
def remove_rating(
    book_id: int,
    participant: CurrentParticipant,
    club: CurrentParticipantClub,
    db: DatabaseSession,
) -> Response:
    if not crud.delete_rating(db, book_id, participant.id):
        raise _not_found("Rating not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
