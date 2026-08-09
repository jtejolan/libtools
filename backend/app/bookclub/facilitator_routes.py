from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.exc import IntegrityError

from bookclub import catalogue, crud, models, participant_email_delivery, schemas
from bookclub.date_poll_routes import build_poll_response
from bookclub.facilitator_auth import require_facilitator
from bookclub.participant_auth import CurrentParticipant, CurrentParticipantClub
from bookclub.participant_schemas import (
    AddDateOptionRequest,
    BroadcastEmailRequest,
    BroadcastEmailResponse,
    CandidateResponse,
    DatePollResponse,
    OpenDatePollRequest,
    OpenVotingRoundRequest,
    ProposeCandidateRequest,
    VotingRoundResponse,
)
from bookclub.participant_unsubscribe import issue_unsubscribe_token
from bookclub.voting_routes import build_round_response
from dependencies import DatabaseSession

# Thin wrapper endpoints for self-serve facilitators (owner-role
# ParticipantAccounts), calling the exact same crud.py functions the staff
# routes.py uses — require_facilitator sets db.info["bookclub_id"] the same
# way require_selected_club does, so nothing below needs to know which auth
# path resolved the club. Deliberately excludes member-roster,
# onboarding/arrival-email, reminder-broadcast, giveaway, and transit-label
# endpoints — none of that applies to self-serve clubs (see
# docs/backend/bookclub.md). Broadcast email to participants is a later,
# separate phase, not reused from here.

router = APIRouter(
    prefix="/facilitator",
    tags=["bookclub-facilitator"],
    dependencies=[Depends(require_facilitator)],
)

Offset = Annotated[int, Query(ge=0)]
Limit = Annotated[int, Query(ge=1, le=500)]


def _not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


@router.post("/books", response_model=schemas.BookResponse, status_code=status.HTTP_201_CREATED)
def create_book(value: schemas.BookCreate, db: DatabaseSession):
    try:
        return crud.create_book(db, value)
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A book with this ISBN already exists",
        ) from exc


@router.get("/books", response_model=list[schemas.BookResponse])
def list_books(db: DatabaseSession, search: str | None = None, offset: Offset = 0, limit: Limit = 100):
    return crud.list_books(db, search=search, offset=offset, limit=limit)


@router.post("/books/import", response_model=schemas.BookImportResponse)
def import_book(value: schemas.BookImportRequest):
    try:
        return catalogue.fetch_catalogue_book(str(value.catalogue_url))
    except catalogue.CatalogueImportError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@router.get("/books/{book_id}", response_model=schemas.BookResponse)
def get_book(book_id: int, db: DatabaseSession):
    book = crud.get_book(db, book_id)
    if book is None:
        raise _not_found("Book not found")
    return book


@router.patch("/books/{book_id}", response_model=schemas.BookResponse)
def update_book(book_id: int, changes: schemas.BookUpdate, db: DatabaseSession):
    try:
        book = crud.update_book(db, book_id, changes)
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A book with this ISBN already exists",
        ) from exc
    if book is None:
        raise _not_found("Book not found")
    return book


@router.delete("/books/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_book(book_id: int, db: DatabaseSession) -> Response:
    result = crud.delete_book(db, book_id)
    if result == "not_found":
        raise _not_found("Book not found")
    if result == "in_use":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This book is used by a meeting and cannot be deleted",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/meetings", response_model=schemas.MeetingResponse, status_code=status.HTTP_201_CREATED)
def create_meeting(value: schemas.MeetingCreate, db: DatabaseSession):
    book = crud.get_book(db, value.book_id)
    if book is None:
        raise _not_found("Book not found")
    return crud.create_meeting(db, value, book)


@router.get("/meetings", response_model=list[schemas.MeetingResponse])
def list_meetings(db: DatabaseSession, from_date: date | None = None, offset: Offset = 0, limit: Limit = 100):
    return crud.list_meetings(db, from_date=from_date, offset=offset, limit=limit)


@router.get("/meetings/{meeting_id}", response_model=schemas.MeetingResponse)
def get_meeting(meeting_id: int, db: DatabaseSession):
    meeting = crud.get_meeting(db, meeting_id)
    if meeting is None:
        raise _not_found("Meeting not found")
    return meeting


@router.patch("/meetings/{meeting_id}", response_model=schemas.MeetingResponse)
def update_meeting(meeting_id: int, changes: schemas.MeetingUpdate, db: DatabaseSession):
    try:
        meeting = crud.update_meeting(db, meeting_id, changes)
    except LookupError as exc:
        raise _not_found(str(exc)) from exc
    if meeting is None:
        raise _not_found("Meeting not found")
    return meeting


@router.delete("/meetings/{meeting_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_meeting(meeting_id: int, db: DatabaseSession) -> Response:
    if not crud.delete_meeting(db, meeting_id):
        raise _not_found("Meeting not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/templates", response_model=list[schemas.TemplateResponse])
def list_templates(db: DatabaseSession):
    return crud.list_templates(db)


@router.post("/templates", response_model=schemas.TemplateResponse, status_code=status.HTTP_201_CREATED)
def create_template(value: schemas.TemplateCreate, db: DatabaseSession):
    try:
        return crud.create_template(db, value)
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A template with this key already exists",
        ) from exc


@router.get("/templates/{key}", response_model=schemas.TemplateResponse)
def get_template(key: str, db: DatabaseSession):
    template = crud.get_template(db, key)
    if template is None:
        raise _not_found("Template not found")
    return template


@router.patch("/templates/{key}", response_model=schemas.TemplateResponse)
def update_template(key: str, changes: schemas.TemplateUpdate, db: DatabaseSession):
    try:
        template = crud.update_template(db, key, changes)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    if template is None:
        raise _not_found("Template not found")
    return template


@router.get("/voting-round", response_model=VotingRoundResponse)
def get_voting_round(participant: CurrentParticipant, db: DatabaseSession):
    round_ = crud.get_current_voting_round(db)
    if round_ is None:
        raise _not_found("No voting round yet")
    # Unlike the participant-facing GET, facilitators always see live vote
    # counts — the "hide the tally" concern is about influencing other
    # participants' votes, not about the facilitator running the poll.
    return build_round_response(db, round_, participant_id=participant.id, show_counts=True)


@router.post(
    "/voting-round", response_model=VotingRoundResponse, status_code=status.HTTP_201_CREATED
)
def open_voting_round(value: OpenVotingRoundRequest, participant: CurrentParticipant, db: DatabaseSession):
    for book_id in value.candidate_book_ids:
        if crud.get_book(db, book_id) is None:
            raise _not_found(f"Book {book_id} not found")
    try:
        round_ = crud.open_voting_round(db, value.candidate_book_ids, participant.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return build_round_response(db, round_, participant_id=participant.id, show_counts=True)


@router.post(
    "/voting-round/candidates",
    response_model=CandidateResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_candidate(value: ProposeCandidateRequest, participant: CurrentParticipant, db: DatabaseSession):
    round_ = crud.get_open_voting_round(db)
    if round_ is None:
        raise _not_found("There is no open voting round")
    if crud.get_book(db, value.book_id) is None:
        raise _not_found("Book not found")
    candidate = crud.add_candidate(db, round_.id, value.book_id, participant.id, auto_approve=True)
    return CandidateResponse(
        id=candidate.id,
        book=crud.get_book(db, candidate.book_id),
        status=candidate.status,
        proposed_by_participant_id=candidate.proposed_by_participant_id,
        proposed_by_name=participant.name,
        vote_count=0,
        created_at=candidate.created_at,
    )


@router.post("/candidates/{candidate_id}/approve", response_model=VotingRoundResponse)
def approve_candidate(candidate_id: int, participant: CurrentParticipant, db: DatabaseSession):
    candidate = crud.set_candidate_status(db, candidate_id, "approved")
    if candidate is None:
        raise _not_found("Candidate not found")
    round_ = db.get(models.BookClubVotingRound, candidate.voting_round_id)
    return build_round_response(db, round_, participant_id=participant.id, show_counts=True)


@router.post("/candidates/{candidate_id}/reject", response_model=VotingRoundResponse)
def reject_candidate(candidate_id: int, participant: CurrentParticipant, db: DatabaseSession):
    candidate = crud.set_candidate_status(db, candidate_id, "rejected")
    if candidate is None:
        raise _not_found("Candidate not found")
    round_ = db.get(models.BookClubVotingRound, candidate.voting_round_id)
    return build_round_response(db, round_, participant_id=participant.id, show_counts=True)


@router.post("/voting-round/close", response_model=VotingRoundResponse)
def close_voting_round(participant: CurrentParticipant, db: DatabaseSession):
    round_ = crud.get_open_voting_round(db)
    if round_ is None:
        raise _not_found("There is no open voting round")
    try:
        round_ = crud.close_voting_round(db, round_.id)
    except LookupError as exc:
        raise _not_found(str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return build_round_response(db, round_, participant_id=participant.id, show_counts=True)


@router.get("/date-poll", response_model=DatePollResponse)
def get_date_poll(participant: CurrentParticipant, db: DatabaseSession):
    poll = crud.get_current_date_poll(db)
    if poll is None:
        raise _not_found("No date poll yet")
    return build_poll_response(db, poll, participant_id=participant.id, show_counts=True)


@router.post("/date-poll", response_model=DatePollResponse, status_code=status.HTTP_201_CREATED)
def open_date_poll(value: OpenDatePollRequest, participant: CurrentParticipant, db: DatabaseSession):
    try:
        poll = crud.open_date_poll(db, value.option_dates)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return build_poll_response(db, poll, participant_id=participant.id, show_counts=True)


@router.post("/date-poll/options", response_model=DatePollResponse, status_code=status.HTTP_201_CREATED)
def add_date_option(value: AddDateOptionRequest, participant: CurrentParticipant, db: DatabaseSession):
    poll = crud.get_open_date_poll(db)
    if poll is None:
        raise _not_found("There is no open date poll")
    crud.add_date_option(db, poll.id, value.option_date)
    return build_poll_response(db, poll, participant_id=participant.id, show_counts=True)


@router.post("/date-poll/close", response_model=DatePollResponse)
def close_date_poll(participant: CurrentParticipant, db: DatabaseSession):
    poll = crud.get_open_date_poll(db)
    if poll is None:
        raise _not_found("There is no open date poll")
    try:
        poll = crud.close_date_poll(db, poll.id)
    except LookupError as exc:
        raise _not_found(str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return build_poll_response(db, poll, participant_id=participant.id, show_counts=True)


@router.post("/broadcast", response_model=BroadcastEmailResponse)
def send_broadcast(
    value: BroadcastEmailRequest,
    request: Request,
    club: CurrentParticipantClub,
    db: DatabaseSession,
):
    template = crud.get_template(db, value.template_key)
    if template is None:
        raise _not_found("Template not found")
    if template.kind != "email":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Only email templates can be broadcast",
        )
    variables = {"club_name": club.name, **value.variables}
    rendered = crud.render_template(template, variables)
    base_url = str(request.base_url).rstrip("/")

    recipients = crud.list_broadcastable_participants(db)
    sent_count = 0
    for recipient in recipients:
        token = issue_unsubscribe_token(recipient.id)
        unsubscribe_url = f"{base_url}/unsubscribe?token={token}"
        if participant_email_delivery.send_broadcast_email(
            recipient=recipient.email,
            subject=rendered.subject or template.name,
            body=rendered.body,
            unsubscribe_url=unsubscribe_url,
        ):
            sent_count += 1

    return BroadcastEmailResponse(
        recipient_count=len(recipients),
        sent_count=sent_count,
        delivery_configured=participant_email_delivery.DELIVERY_CONFIGURED,
        missing_variables=rendered.missing_variables,
    )
