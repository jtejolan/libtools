from typing import Annotated

from fastapi import Depends, HTTPException, status

from bookclub.models import BookClub
from bookclub.participant_auth import CurrentParticipant, CurrentParticipantClub

# crud.py's book/meeting/template functions are auth-agnostic — they never
# reference LibtoolsUser, only db.info["bookclub_id"] (set as a side effect
# of access.py's require_selected_club today). CurrentParticipantClub
# (participant_auth.py) is the "mechanical adapter" that resolves any
# signed-in participant's club and sets that same db.info key; this layers
# the owner-only check on top of it, so facilitator_routes.py can call the
# exact same crud.py functions routes.py does.


def require_facilitator(
    participant: CurrentParticipant,
    club: CurrentParticipantClub,
) -> BookClub:
    if participant.role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Facilitator access is required",
        )
    return club


CurrentFacilitator = Annotated[BookClub, Depends(require_facilitator)]
