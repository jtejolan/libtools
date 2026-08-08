from typing import Annotated

from fastapi import Depends, HTTPException, status

from bookclub.models import BookClub
from bookclub.participant_auth import CurrentParticipant
from dependencies import DatabaseSession

# crud.py's book/meeting/template functions are auth-agnostic — they never
# reference LibtoolsUser, only db.info["bookclub_id"] (set as a side effect
# of access.py's require_selected_club today). This dependency is the
# "mechanical adapter" that lets facilitator_routes.py call the exact same
# crud.py functions routes.py does, just resolving the current club from an
# owner-role ParticipantAccount session instead of a LibtoolsUser session.


def require_facilitator(
    participant: CurrentParticipant,
    db: DatabaseSession,
) -> BookClub:
    if participant.role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Facilitator access is required",
        )
    club = db.get(BookClub, participant.club_id)
    if club is None:
        raise HTTPException(status_code=404, detail="Book club not found")
    db.info["bookclub_id"] = club.id
    db.info["bookclub"] = club
    return club


CurrentFacilitator = Annotated[BookClub, Depends(require_facilitator)]
