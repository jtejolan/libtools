from datetime import date
from typing import Annotated
from urllib.parse import urlencode

import qrcode
import qrcode.image.svg
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from accounts.auth import CurrentUser
from bookclub import catalogue, crud, models, participant_email_delivery, participant_tokens, schemas
from bookclub.date_poll_routes import build_poll_response
from bookclub.access import SelectedClub, require_selected_club
from bookclub.participant_schemas import (
    AddDateOptionRequest,
    AnnouncementCreate,
    AnnouncementResponse,
    AnnouncementUpdate,
    BroadcastEmailRequest,
    BroadcastEmailResponse,
    BookSuggestionResponse,
    CandidateResponse,
    CommunityAccountStatus,
    CommunityOverviewResponse,
    DatePollResponse,
    DiscussionModerationResponse,
    OpenDatePollRequest,
    OpenVotingRoundRequest,
    ProposeCandidateRequest,
    ReaderPreviewResponse,
    VotingRoundResponse,
    RsvpCounts,
)
from bookclub.participant_models import ParticipantAccount
from bookclub.participant_unsubscribe import issue_unsubscribe_token
from bookclub.voting_routes import build_round_response
from bookclub.participant_community_routes import _book_suggestion_response
from dependencies import DatabaseSession

# Community administration is part of the regular Book Club Manager. These
# routes use the same selected-club Libtools authorization as routes.py;
# bookclub.libtools.app is participant-only.

router = APIRouter(
    prefix="/bookclub/community",
    tags=["bookclub-community-management"],
    dependencies=[Depends(require_selected_club)],
)

Offset = Annotated[int, Query(ge=0)]
Limit = Annotated[int, Query(ge=1, le=500)]
PARTICIPANT_PORTAL_ORIGIN = "https://bookclub.libtools.app"


def _not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


@router.delete("/discussion/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
def moderate_discussion_post(post_id: int, club: SelectedClub, db: DatabaseSession) -> Response:
    post = db.scalar(select(models.BookClubDiscussionPost).where(
        models.BookClubDiscussionPost.id == post_id,
        models.BookClubDiscussionPost.club_id == club.id,
    ))
    if post is None:
        raise _not_found("Discussion post not found")
    db.query(models.BookClubActivity).filter(
        models.BookClubActivity.kind == "discussion",
        models.BookClubActivity.reference_id == post.id,
    ).delete(synchronize_session=False)
    db.delete(post)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/discussion", response_model=list[DiscussionModerationResponse])
def discussion_moderation_queue(club: SelectedClub, db: DatabaseSession):
    rows = db.execute(
        select(models.BookClubDiscussionPost, models.BookClubMember.name, models.BookClubBook.title)
        .join(models.BookClubMember, models.BookClubMember.id == models.BookClubDiscussionPost.member_id)
        .join(models.BookClubBook, models.BookClubBook.id == models.BookClubDiscussionPost.book_id)
        .where(models.BookClubDiscussionPost.club_id == club.id)
        .order_by(models.BookClubDiscussionPost.created_at.desc(), models.BookClubDiscussionPost.id.desc())
        .limit(200)
    ).all()
    return [DiscussionModerationResponse(
        id=post.id,
        book_id=post.book_id,
        book_title=title,
        author_name=name,
        body=post.body,
        spoiler=post.spoiler,
        parent_id=post.parent_id,
        created_at=post.created_at,
    ) for post, name, title in rows]


@router.get("/invite-qr.svg")
def invite_qr_code(club: SelectedClub) -> Response:
    if not club.public:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Make this club public before sharing an invitation",
        )
    invite_url = f"{PARTICIPANT_PORTAL_ORIGIN}/clubs/{club.slug}"
    image = qrcode.make(
        invite_url,
        image_factory=qrcode.image.svg.SvgPathFillImage,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        border=4,
    )
    return Response(
        content=image.to_string(),
        media_type="image/svg+xml",
        headers={"Cache-Control": "private, no-store"},
    )


@router.post("/reader-preview", response_model=ReaderPreviewResponse)
def start_reader_preview(user: CurrentUser, club: SelectedClub, db: DatabaseSession):
    if not user.email or user.email_verified_at is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Verify your account email before previewing the reader experience",
        )
    participant = crud.get_or_create_facilitator_participant(
        db, club, name=user.name, email=user.email
    )
    raw_token = participant_tokens.issue_token(
        db, participant, participant_tokens.READER_PREVIEW, participant_tokens.READER_PREVIEW_LIFETIME
    )
    db.commit()
    query = urlencode({"token": raw_token, "club": club.slug})
    return ReaderPreviewResponse(url=f"{PARTICIPANT_PORTAL_ORIGIN}/participant/auth/preview-login?{query}")


@router.get("/overview", response_model=CommunityOverviewResponse)
def community_overview(club: SelectedClub, db: DatabaseSession):
    account_rows = db.execute(
        select(models.BookClubMember, ParticipantAccount)
        .outerjoin(
            ParticipantAccount,
            ParticipantAccount.id == models.BookClubMember.participant_account_id,
        )
        .where(
            models.BookClubMember.club_id == club.id,
            models.BookClubMember.active.is_(True),
        )
        .order_by(models.BookClubMember.name)
    ).all()
    accounts = []
    for member, account in account_rows:
        account_status = (
            "not_registered"
            if account is None
            else "account_disabled"
            if not account.active
            else "active"
            if account.email_verified_at is not None
            else "pending_verification"
        )
        accounts.append(
            CommunityAccountStatus(
                member_id=member.id,
                name=member.name,
                email=member.email,
                status=account_status,
            )
        )

    linked = sum(item.status != "not_registered" for item in accounts)
    verified = sum(item.status == "active" for item in accounts)
    pending = sum(item.status == "pending_verification" for item in accounts)
    disabled = sum(item.status == "account_disabled" for item in accounts)
    upcoming = db.scalar(
        select(models.BookClubMeeting)
        .options(selectinload(models.BookClubMeeting.book))
        .where(
            models.BookClubMeeting.club_id == club.id,
            models.BookClubMeeting.status == "planned",
            models.BookClubMeeting.meeting_date >= date.today(),
        )
        .order_by(models.BookClubMeeting.meeting_date, models.BookClubMeeting.id)
    )
    rsvp_rows = []
    if upcoming is not None:
        rsvp_rows = list(
            db.execute(
                select(
                    models.BookClubParticipation.member_id,
                    models.BookClubParticipation.rsvp_status,
                )
                .join(models.BookClubMember)
                .where(
                    models.BookClubParticipation.meeting_id == upcoming.id,
                    models.BookClubMember.active.is_(True),
                )
            )
        )
    rsvp_by_member = {member_id: value for member_id, value in rsvp_rows}
    for account in accounts:
        account.rsvp_status = rsvp_by_member.get(account.member_id)
    rsvp_values = list(rsvp_by_member.values())
    counts = RsvpCounts(
        attending=rsvp_values.count("attending"),
        maybe=rsvp_values.count("maybe"),
        not_attending=rsvp_values.count("not_attending"),
        no_response=max(0, len(accounts) - sum(value is not None for value in rsvp_values)),
    )
    pending_proposals = db.scalar(
        select(func.count(models.BookClubBookCandidate.id))
        .join(
            models.BookClubVotingRound,
            models.BookClubVotingRound.id == models.BookClubBookCandidate.voting_round_id,
        )
        .where(
            models.BookClubVotingRound.club_id == club.id,
            models.BookClubVotingRound.status == "open",
            models.BookClubBookCandidate.status == "pending",
        )
    ) or 0
    pending_proposals += db.scalar(
        select(func.count(models.BookClubBookSuggestion.id)).where(
            models.BookClubBookSuggestion.club_id == club.id,
            models.BookClubBookSuggestion.status == "pending",
        )
    ) or 0
    return CommunityOverviewResponse(
        member_count=len(accounts),
        linked_account_count=linked,
        verified_account_count=verified,
        pending_verification_count=pending,
        disabled_account_count=disabled,
        unlinked_member_count=len(accounts) - linked,
        accounts=accounts,
        next_meeting=upcoming,
        rsvp_counts=counts,
        pending_book_proposals=pending_proposals,
    )


@router.get("/book-suggestions", response_model=list[BookSuggestionResponse])
def list_book_suggestions(club: SelectedClub, db: DatabaseSession):
    rows = list(db.execute(
        select(models.BookClubBookSuggestion, ParticipantAccount.name)
        .join(ParticipantAccount, ParticipantAccount.id == models.BookClubBookSuggestion.participant_id)
        .where(models.BookClubBookSuggestion.club_id == club.id)
        .order_by(
            (models.BookClubBookSuggestion.status == "pending").desc(),
            models.BookClubBookSuggestion.created_at.desc(),
        )
    ).all())
    return [_book_suggestion_response(item, name) for item, name in rows]


def _club_book_suggestion(db, club_id: int, suggestion_id: int):
    return db.scalar(select(models.BookClubBookSuggestion).where(
        models.BookClubBookSuggestion.id == suggestion_id,
        models.BookClubBookSuggestion.club_id == club_id,
    ))


@router.post("/book-suggestions/{suggestion_id}/accept", response_model=BookSuggestionResponse)
def accept_book_suggestion(
    suggestion_id: int, club: SelectedClub, db: DatabaseSession
):
    suggestion = _club_book_suggestion(db, club.id, suggestion_id)
    if suggestion is None:
        raise _not_found("Book suggestion not found")
    if suggestion.status == "pending":
        book = db.scalar(select(models.BookClubBook).where(
            models.BookClubBook.club_id == club.id,
            func.lower(models.BookClubBook.title) == suggestion.title.lower(),
            func.lower(models.BookClubBook.author) == suggestion.author.lower(),
        ))
        if book is None and suggestion.isbn:
            book = db.scalar(select(models.BookClubBook).where(
                models.BookClubBook.club_id == club.id,
                models.BookClubBook.isbn == suggestion.isbn,
            ))
        if book is None:
            book = crud.create_book(db, schemas.BookCreate(
                title=suggestion.title,
                author=suggestion.author,
                cover_image_url=suggestion.cover_image_url,
                description=suggestion.description,
                publication_date=suggestion.publication_date,
                isbn=suggestion.isbn,
                page_count=suggestion.page_count,
                catalogue_url=(
                    f"https://books.google.com/books?id={suggestion.google_books_id}"
                    if suggestion.google_books_id else None
                ),
            ))
        suggestion.book_id = book.id
        suggestion.status = "accepted"
        db.commit()
        db.refresh(suggestion)
    proposer_name = db.scalar(select(ParticipantAccount.name).where(
        ParticipantAccount.id == suggestion.participant_id
    ))
    return _book_suggestion_response(suggestion, proposer_name)


@router.post("/book-suggestions/{suggestion_id}/dismiss", response_model=BookSuggestionResponse)
def dismiss_book_suggestion(
    suggestion_id: int, club: SelectedClub, db: DatabaseSession
):
    suggestion = _club_book_suggestion(db, club.id, suggestion_id)
    if suggestion is None:
        raise _not_found("Book suggestion not found")
    if suggestion.status == "pending":
        suggestion.status = "dismissed"
        db.commit()
        db.refresh(suggestion)
    proposer_name = db.scalar(select(ParticipantAccount.name).where(
        ParticipantAccount.id == suggestion.participant_id
    ))
    return _book_suggestion_response(suggestion, proposer_name)


@router.get("/announcements", response_model=list[AnnouncementResponse])
def list_announcements(club: SelectedClub, db: DatabaseSession):
    return list(
        db.scalars(
            select(models.BookClubAnnouncement)
            .where(models.BookClubAnnouncement.club_id == club.id)
            .order_by(
                models.BookClubAnnouncement.pinned.desc(),
                models.BookClubAnnouncement.published_at.desc(),
                models.BookClubAnnouncement.id.desc(),
            )
        )
    )


@router.post(
    "/announcements",
    response_model=AnnouncementResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_announcement(value: AnnouncementCreate, club: SelectedClub, db: DatabaseSession):
    announcement = models.BookClubAnnouncement(club_id=club.id, **value.model_dump())
    db.add(announcement)
    db.commit()
    db.refresh(announcement)
    return announcement


@router.patch("/announcements/{announcement_id}", response_model=AnnouncementResponse)
def update_announcement(
    announcement_id: int,
    value: AnnouncementUpdate,
    club: SelectedClub,
    db: DatabaseSession,
):
    announcement = db.scalar(
        select(models.BookClubAnnouncement).where(
            models.BookClubAnnouncement.id == announcement_id,
            models.BookClubAnnouncement.club_id == club.id,
        )
    )
    if announcement is None:
        raise _not_found("Announcement not found")
    for field, field_value in value.model_dump(exclude_unset=True).items():
        setattr(announcement, field, field_value)
    db.commit()
    db.refresh(announcement)
    return announcement


@router.delete("/announcements/{announcement_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_announcement(
    announcement_id: int, club: SelectedClub, db: DatabaseSession
) -> Response:
    announcement = db.scalar(
        select(models.BookClubAnnouncement).where(
            models.BookClubAnnouncement.id == announcement_id,
            models.BookClubAnnouncement.club_id == club.id,
        )
    )
    if announcement is None:
        raise _not_found("Announcement not found")
    db.delete(announcement)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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


@router.post("/books/search", response_model=schemas.BookSearchResponse)
def search_books(value: schemas.BookSearchRequest):
    try:
        results = catalogue.search_catalogue_books(value.query)
    except catalogue.CatalogueImportError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    return schemas.BookSearchResponse(results=results)


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
def get_voting_round(db: DatabaseSession):
    round_ = crud.get_current_voting_round(db)
    if round_ is None:
        raise _not_found("No voting round yet")
    # Unlike the participant-facing GET, facilitators always see live vote
    # counts — the "hide the tally" concern is about influencing other
    # participants' votes, not about the facilitator running the poll.
    return build_round_response(db, round_, participant_id=None, show_counts=True)


@router.post(
    "/voting-round", response_model=VotingRoundResponse, status_code=status.HTTP_201_CREATED
)
def open_voting_round(value: OpenVotingRoundRequest, db: DatabaseSession):
    for book_id in value.candidate_book_ids:
        if crud.get_book(db, book_id) is None:
            raise _not_found(f"Book {book_id} not found")
    try:
        round_ = crud.open_voting_round(db, value.candidate_book_ids, None)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return build_round_response(db, round_, participant_id=None, show_counts=True)


@router.post(
    "/voting-round/candidates",
    response_model=CandidateResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_candidate(value: ProposeCandidateRequest, db: DatabaseSession):
    round_ = crud.get_open_voting_round(db)
    if round_ is None:
        raise _not_found("There is no open voting round")
    if crud.get_book(db, value.book_id) is None:
        raise _not_found("Book not found")
    candidate = crud.add_candidate(db, round_.id, value.book_id, None, auto_approve=True)
    return CandidateResponse(
        id=candidate.id,
        book=crud.get_book(db, candidate.book_id),
        status=candidate.status,
        proposed_by_participant_id=candidate.proposed_by_participant_id,
        proposed_by_name=None,
        vote_count=0,
        created_at=candidate.created_at,
    )


@router.post("/candidates/{candidate_id}/approve", response_model=VotingRoundResponse)
def approve_candidate(candidate_id: int, db: DatabaseSession):
    candidate = crud.set_candidate_status(db, candidate_id, "approved")
    if candidate is None:
        raise _not_found("Candidate not found")
    round_ = db.get(models.BookClubVotingRound, candidate.voting_round_id)
    return build_round_response(db, round_, participant_id=None, show_counts=True)


@router.post("/candidates/{candidate_id}/reject", response_model=VotingRoundResponse)
def reject_candidate(candidate_id: int, db: DatabaseSession):
    candidate = crud.set_candidate_status(db, candidate_id, "rejected")
    if candidate is None:
        raise _not_found("Candidate not found")
    round_ = db.get(models.BookClubVotingRound, candidate.voting_round_id)
    return build_round_response(db, round_, participant_id=None, show_counts=True)


@router.post("/voting-round/close", response_model=VotingRoundResponse)
def close_voting_round(db: DatabaseSession):
    round_ = crud.get_open_voting_round(db)
    if round_ is None:
        raise _not_found("There is no open voting round")
    try:
        round_ = crud.close_voting_round(db, round_.id)
    except LookupError as exc:
        raise _not_found(str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return build_round_response(db, round_, participant_id=None, show_counts=True)


@router.get("/date-poll", response_model=DatePollResponse)
def get_date_poll(db: DatabaseSession):
    poll = crud.get_current_date_poll(db)
    if poll is None:
        raise _not_found("No date poll yet")
    return build_poll_response(db, poll, participant_id=None, show_counts=True)


@router.post("/date-poll", response_model=DatePollResponse, status_code=status.HTTP_201_CREATED)
def open_date_poll(value: OpenDatePollRequest, db: DatabaseSession):
    try:
        poll = crud.open_date_poll(db, value.option_dates)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return build_poll_response(db, poll, participant_id=None, show_counts=True)


@router.post("/date-poll/options", response_model=DatePollResponse, status_code=status.HTTP_201_CREATED)
def add_date_option(value: AddDateOptionRequest, db: DatabaseSession):
    poll = crud.get_open_date_poll(db)
    if poll is None:
        raise _not_found("There is no open date poll")
    crud.add_date_option(db, poll.id, value.option_date)
    return build_poll_response(db, poll, participant_id=None, show_counts=True)


@router.post("/date-poll/close", response_model=DatePollResponse)
def close_date_poll(db: DatabaseSession):
    poll = crud.get_open_date_poll(db)
    if poll is None:
        raise _not_found("There is no open date poll")
    try:
        poll = crud.close_date_poll(db, poll.id)
    except LookupError as exc:
        raise _not_found(str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return build_poll_response(db, poll, participant_id=None, show_counts=True)


@router.post("/broadcast", response_model=BroadcastEmailResponse)
def send_broadcast(
    value: BroadcastEmailRequest,
    request: Request,
    club: SelectedClub,
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
    for member, recipient in recipients:
        token = issue_unsubscribe_token(member.id)
        unsubscribe_url = f"{base_url}/unsubscribe?token={token}"
        if participant_email_delivery.send_broadcast_email(
            recipient=member.email,
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
