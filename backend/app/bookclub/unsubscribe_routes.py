from fastapi import APIRouter, HTTPException, status

from bookclub import crud
from bookclub.models import BookClub
from bookclub.participant_models import ParticipantAccount
from bookclub.participant_schemas import UnsubscribeRequest, UnsubscribeResponse
from bookclub.participant_unsubscribe import verify_unsubscribe_token
from dependencies import DatabaseSession

# Deliberately public — no CurrentParticipant/CurrentParticipantClub
# dependency. This must work from a cold email client with no active
# session, authenticated only by the signed token in the link itself.

router = APIRouter(prefix="/participant", tags=["bookclub-participant-unsubscribe"])


@router.post("/unsubscribe", response_model=UnsubscribeResponse)
def unsubscribe(value: UnsubscribeRequest, db: DatabaseSession):
    participant_id = verify_unsubscribe_token(value.token)
    if participant_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="This unsubscribe link is invalid."
        )
    participant = db.get(ParticipantAccount, participant_id)
    if participant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found.")
    already_unsubscribed = participant.unsubscribed_at is not None
    crud.mark_participant_unsubscribed(db, participant)
    club = db.get(BookClub, participant.club_id)
    return UnsubscribeResponse(
        club_name=club.name, email=participant.email, already_unsubscribed=already_unsubscribed
    )
