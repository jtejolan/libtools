from fastapi import APIRouter, HTTPException, status

from bookclub import crud
from bookclub.models import BookClub
from bookclub.models import BookClubMember
from bookclub.participant_schemas import UnsubscribeRequest, UnsubscribeResponse
from bookclub.participant_unsubscribe import verify_unsubscribe_token
from dependencies import DatabaseSession

# Deliberately public — no CurrentParticipant/CurrentParticipantClub
# dependency. This must work from a cold email client with no active
# session, authenticated only by the signed token in the link itself.

router = APIRouter(prefix="/participant", tags=["bookclub-participant-unsubscribe"])


@router.post("/unsubscribe", response_model=UnsubscribeResponse)
def unsubscribe(value: UnsubscribeRequest, db: DatabaseSession):
    member_id = verify_unsubscribe_token(value.token)
    if member_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="This unsubscribe link is invalid."
        )
    member = db.get(BookClubMember, member_id)
    if member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found.")
    already_unsubscribed = member.participant_unsubscribed_at is not None
    crud.mark_participant_unsubscribed(db, member)
    club = db.get(BookClub, member.club_id)
    return UnsubscribeResponse(
        club_name=club.name, email=member.email, already_unsubscribed=already_unsubscribed
    )
