from fastapi import APIRouter, HTTPException, Response, status

from bookclub import crud
from bookclub.participant_auth import CurrentParticipant, CurrentParticipantClub
from bookclub.participant_schemas import CastDateVoteRequest, DatePollOptionResponse, DatePollResponse
from dependencies import DatabaseSession

# Participant-facing "when should we meet next" polling. Deliberately a
# separate system from book voting (voting_routes.py) — see
# BookClubDatePoll's docstring in models.py. Facilitator-side management
# (open/close, add options) lives in facilitator_routes.py, which imports
# build_poll_response from here, same pattern as book voting.

router = APIRouter(prefix="/participant/date-poll", tags=["bookclub-participant-date-poll"])


def _not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def build_poll_response(
    db: DatabaseSession, poll, *, participant_id: int | None, show_counts: bool
) -> DatePollResponse:
    options = crud.list_date_options(db, poll.id)
    counts = crud.date_poll_vote_counts(db, poll.id) if show_counts else {}
    my_vote = crud.get_own_date_vote(db, poll.id, participant_id) if participant_id else None
    return DatePollResponse(
        id=poll.id,
        status=poll.status,
        winning_date=poll.winning_date,
        options=[
            DatePollOptionResponse(
                id=option.id,
                option_date=option.option_date,
                vote_count=counts.get(option.id, 0) if show_counts else None,
            )
            for option in options
        ],
        my_vote_option_id=my_vote.option_id if my_vote else None,
    )


@router.get("", response_model=DatePollResponse)
def get_date_poll(participant: CurrentParticipant, club: CurrentParticipantClub, db: DatabaseSession):
    poll = crud.get_current_date_poll(db)
    if poll is None:
        raise _not_found("No date poll yet")
    return build_poll_response(
        db, poll, participant_id=participant.id, show_counts=poll.status == "closed"
    )


@router.put("/vote", response_model=DatePollResponse)
def cast_vote(
    value: CastDateVoteRequest,
    participant: CurrentParticipant,
    club: CurrentParticipantClub,
    db: DatabaseSession,
):
    poll = crud.get_open_date_poll(db)
    if poll is None:
        raise _not_found("There is no open date poll")
    option = crud.get_date_option(db, value.option_id)
    if option is None or option.poll_id != poll.id:
        raise _not_found("Date option not found")
    crud.cast_date_vote(db, poll.id, value.option_id, participant.id)
    return build_poll_response(db, poll, participant_id=participant.id, show_counts=False)


@router.delete("/vote", status_code=status.HTTP_204_NO_CONTENT)
def remove_vote(
    participant: CurrentParticipant, club: CurrentParticipantClub, db: DatabaseSession
) -> Response:
    poll = crud.get_open_date_poll(db)
    if poll is None or not crud.remove_date_vote(db, poll.id, participant.id):
        raise _not_found("No vote to remove")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
