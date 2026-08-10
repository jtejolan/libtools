from fastapi import APIRouter, HTTPException, Response, status

from bookclub import crud, schemas
from bookclub.participant_auth import CurrentParticipant, CurrentParticipantClub
from bookclub.participant_schemas import (
    CandidateResponse,
    CastVoteRequest,
    ProposeCandidateRequest,
    ProposeNewBookRequest,
    VotingRoundResponse,
)
from dependencies import DatabaseSession

# Participant-facing "what should we read next" voting. Facilitator-side
# management (open/close a round, approve/reject proposals) lives in
# facilitator_routes.py, which imports build_round_response from here to
# avoid re-deriving the same response shape.

router = APIRouter(prefix="/participant/voting-round", tags=["bookclub-participant-voting"])


def _not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def build_round_response(
    db: DatabaseSession,
    round_,
    *,
    participant_id: int | None,
    show_counts: bool,
) -> VotingRoundResponse:
    candidates = crud.list_candidates(db, round_.id)
    counts = crud.vote_counts(db, round_.id) if show_counts else {}
    names = crud.candidate_proposer_names(db, candidates)
    my_vote = crud.get_own_vote(db, round_.id, participant_id) if participant_id else None
    winning_book = crud.get_book(db, round_.winning_book_id) if round_.winning_book_id else None
    return VotingRoundResponse(
        id=round_.id,
        status=round_.status,
        winning_book=winning_book,
        candidates=[
            CandidateResponse(
                id=candidate.id,
                book=candidate.book,
                status=candidate.status,
                proposed_by_participant_id=candidate.proposed_by_participant_id,
                proposed_by_name=names.get(candidate.proposed_by_participant_id),
                # counts.get(..., 0) not counts.get(...): a candidate with
                # zero votes is absent from the GROUP BY result entirely, so
                # a bare .get() would return None — indistinguishable from
                # "hidden because the round is open", which is a different
                # thing. Zero votes should render as 0, not "hidden".
                vote_count=counts.get(candidate.id, 0) if show_counts else None,
                created_at=candidate.created_at,
            )
            for candidate in candidates
        ],
        my_vote_candidate_id=my_vote.candidate_id if my_vote else None,
    )


@router.get("", response_model=VotingRoundResponse)
def get_voting_round(participant: CurrentParticipant, club: CurrentParticipantClub, db: DatabaseSession):
    round_ = crud.get_current_voting_round(db)
    if round_ is None:
        raise _not_found("No voting round yet")
    # Vote counts stay hidden from ordinary participants while a round is
    # open, so an early tally doesn't bandwagon later votes — always
    # visible once closed.
    return build_round_response(
        db, round_, participant_id=participant.id, show_counts=round_.status == "closed"
    )


@router.post("/candidates", response_model=CandidateResponse, status_code=status.HTTP_201_CREATED)
def propose_candidate(
    value: ProposeCandidateRequest,
    participant: CurrentParticipant,
    club: CurrentParticipantClub,
    db: DatabaseSession,
):
    round_ = crud.get_open_voting_round(db)
    if round_ is None:
        raise _not_found("There is no open voting round")
    if crud.get_book(db, value.book_id) is None:
        raise _not_found("Book not found")
    candidate = crud.add_candidate(
        db, round_.id, value.book_id, participant.id, auto_approve=False
    )
    return CandidateResponse(
        id=candidate.id,
        book=crud.get_book(db, candidate.book_id),
        status=candidate.status,
        proposed_by_participant_id=candidate.proposed_by_participant_id,
        proposed_by_name=participant.name,
        vote_count=None,
        created_at=candidate.created_at,
    )


@router.post("/candidates/new-book", response_model=CandidateResponse, status_code=status.HTTP_201_CREATED)
def propose_new_book(
    value: ProposeNewBookRequest,
    participant: CurrentParticipant,
    club: CurrentParticipantClub,
    db: DatabaseSession,
):
    round_ = crud.get_open_voting_round(db)
    if round_ is None:
        raise _not_found("There is no open voting round")
    # A participant-typed title has no ISBN, so it can never collide with
    # create_book's ISBN uniqueness constraint - always a fresh book row,
    # even if it duplicates an existing title/author.
    book = crud.create_book(db, schemas.BookCreate(title=value.title, author=value.author))
    candidate = crud.add_candidate(
        db, round_.id, book.id, participant.id, auto_approve=False
    )
    return CandidateResponse(
        id=candidate.id,
        book=book,
        status=candidate.status,
        proposed_by_participant_id=candidate.proposed_by_participant_id,
        proposed_by_name=participant.name,
        vote_count=None,
        created_at=candidate.created_at,
    )


@router.put("/vote", response_model=VotingRoundResponse)
def cast_vote(
    value: CastVoteRequest,
    participant: CurrentParticipant,
    club: CurrentParticipantClub,
    db: DatabaseSession,
):
    round_ = crud.get_open_voting_round(db)
    if round_ is None:
        raise _not_found("There is no open voting round")
    candidate = crud.get_candidate(db, value.candidate_id)
    if candidate is None or candidate.voting_round_id != round_.id or candidate.status != "approved":
        raise _not_found("Candidate not found")
    crud.cast_vote(db, round_.id, value.candidate_id, participant.id)
    return build_round_response(db, round_, participant_id=participant.id, show_counts=False)


@router.delete("/vote", status_code=status.HTTP_204_NO_CONTENT)
def remove_vote(
    participant: CurrentParticipant, club: CurrentParticipantClub, db: DatabaseSession
) -> Response:
    round_ = crud.get_open_voting_round(db)
    if round_ is None or not crud.remove_vote(db, round_.id, participant.id):
        raise _not_found("No vote to remove")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
