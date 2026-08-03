from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.exc import IntegrityError

from bookclub import catalogue, crud, models, schemas
from bookclub.access import require_selected_club
from dependencies import DatabaseSession

router = APIRouter(
    prefix="/bookclub",
    tags=["book club"],
    dependencies=[Depends(require_selected_club)],
)

Offset = Annotated[int, Query(ge=0)]
Limit = Annotated[int, Query(ge=1, le=500)]


def _not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


@router.post(
    "/members",
    response_model=schemas.MemberResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_member(value: schemas.MemberCreate, db: DatabaseSession):
    try:
        return crud.create_member(db, value)
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A member with this email already exists",
        ) from exc


@router.get("/members", response_model=list[schemas.MemberResponse])
def list_members(
    db: DatabaseSession,
    active: bool | None = None,
    search: str | None = None,
    offset: Offset = 0,
    limit: Limit = 100,
):
    return crud.list_members(
        db, active=active, search=search, offset=offset, limit=limit
    )


@router.get("/members/{member_id}", response_model=schemas.MemberResponse)
def get_member(member_id: int, db: DatabaseSession):
    member = crud.get_member(db, member_id)
    if member is None:
        raise _not_found("Member not found")
    return member


@router.patch("/members/{member_id}", response_model=schemas.MemberResponse)
def update_member(
    member_id: int, changes: schemas.MemberUpdate, db: DatabaseSession
):
    try:
        member = crud.update_member(db, member_id, changes)
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A member with this email already exists",
        ) from exc
    if member is None:
        raise _not_found("Member not found")
    return member


@router.get(
    "/members/{member_id}/history",
    response_model=list[schemas.MemberHistoryResponse],
)
def member_history(member_id: int, db: DatabaseSession):
    if crud.get_member(db, member_id) is None:
        raise _not_found("Member not found")
    return [
        schemas.MemberHistoryResponse(
            meeting=entry.meeting,
            delivery_method=entry.delivery_method,
            destination_branch=entry.destination_branch,
            book_checked_out=entry.book_checked_out,
            attended=entry.attended,
        )
        for entry in crud.member_history(db, member_id)
    ]


@router.post(
    "/books",
    response_model=schemas.BookResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_book(value: schemas.BookCreate, db: DatabaseSession):
    try:
        return crud.create_book(db, value)
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A book with this ISBN already exists",
        ) from exc


@router.get("/books", response_model=list[schemas.BookResponse])
def list_books(
    db: DatabaseSession,
    search: str | None = None,
    offset: Offset = 0,
    limit: Limit = 100,
):
    return crud.list_books(
        db, search=search, offset=offset, limit=limit
    )


@router.post("/books/import", response_model=schemas.BookImportResponse)
def import_book(value: schemas.BookImportRequest):
    try:
        return catalogue.fetch_catalogue_book(str(value.catalogue_url))
    except catalogue.CatalogueImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc


@router.get("/books/{book_id}", response_model=schemas.BookResponse)
def get_book(book_id: int, db: DatabaseSession):
    book = crud.get_book(db, book_id)
    if book is None:
        raise _not_found("Book not found")
    return book


@router.patch("/books/{book_id}", response_model=schemas.BookResponse)
def update_book(
    book_id: int, changes: schemas.BookUpdate, db: DatabaseSession
):
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


@router.delete(
    "/books/{book_id}", status_code=status.HTTP_204_NO_CONTENT
)
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


@router.post(
    "/meetings",
    response_model=schemas.MeetingResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_meeting(value: schemas.MeetingCreate, db: DatabaseSession):
    book = crud.get_book(db, value.book_id)
    if book is None:
        raise _not_found("Book not found")
    return crud.create_meeting(db, value, book)


@router.get("/meetings", response_model=list[schemas.MeetingResponse])
def list_meetings(
    db: DatabaseSession,
    from_date: date | None = None,
    offset: Offset = 0,
    limit: Limit = 100,
):
    return crud.list_meetings(
        db, from_date=from_date, offset=offset, limit=limit
    )


@router.get(
    "/meetings/{meeting_id}", response_model=schemas.MeetingResponse
)
def get_meeting(meeting_id: int, db: DatabaseSession):
    meeting = crud.get_meeting(db, meeting_id)
    if meeting is None:
        raise _not_found("Meeting not found")
    return meeting


@router.patch(
    "/meetings/{meeting_id}", response_model=schemas.MeetingResponse
)
def update_meeting(
    meeting_id: int, changes: schemas.MeetingUpdate, db: DatabaseSession
):
    try:
        meeting = crud.update_meeting(db, meeting_id, changes)
    except LookupError as exc:
        raise _not_found(str(exc)) from exc
    if meeting is None:
        raise _not_found("Meeting not found")
    return meeting


@router.delete(
    "/meetings/{meeting_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_meeting(meeting_id: int, db: DatabaseSession) -> Response:
    if not crud.delete_meeting(db, meeting_id):
        raise _not_found("Meeting not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/meetings/{meeting_id}/roster/sync",
    response_model=schemas.RosterSyncResponse,
)
def sync_roster(meeting_id: int, db: DatabaseSession):
    result = crud.sync_roster(db, meeting_id)
    if result is None:
        raise _not_found("Meeting not found")
    added, total = result
    return schemas.RosterSyncResponse(added=added, total=total)


@router.get(
    "/meetings/{meeting_id}/roster",
    response_model=list[schemas.ParticipationResponse],
)
def list_roster(meeting_id: int, db: DatabaseSession):
    if crud.get_meeting(db, meeting_id) is None:
        raise _not_found("Meeting not found")
    return crud.list_participation(db, meeting_id)


@router.put(
    "/meetings/{meeting_id}/members/{member_id}",
    response_model=schemas.ParticipationResponse,
)
def update_participation(
    meeting_id: int,
    member_id: int,
    changes: schemas.ParticipationUpdate,
    db: DatabaseSession,
):
    meeting = crud.get_meeting(db, meeting_id)
    if meeting is None:
        raise _not_found("Meeting not found")
    member = crud.get_member(db, member_id)
    if member is None:
        raise _not_found("Member not found")
    try:
        return crud.update_participation(db, meeting, member, changes)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc


@router.get(
    "/meetings/{meeting_id}/recipients",
    response_model=list[schemas.MemberResponse],
)
def list_recipients(
    meeting_id: int,
    db: DatabaseSession,
    recipient_filter: schemas.RecipientFilter = Query(
        default="all", alias="filter"
    ),
):
    if crud.get_meeting(db, meeting_id) is None:
        raise _not_found("Meeting not found")
    return crud.list_recipients(db, meeting_id, recipient_filter)


@router.post(
    "/meetings/{meeting_id}/giveaway/draw",
    response_model=schemas.GiveawayWinnerResponse,
)
def draw_giveaway(
    meeting_id: int, db: DatabaseSession, redraw: bool = False
):
    meeting = crud.get_meeting(db, meeting_id)
    if meeting is None:
        raise _not_found("Meeting not found")
    try:
        winner = crud.draw_giveaway_winner(db, meeting, redraw=redraw)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    return schemas.GiveawayWinnerResponse(meeting_id=meeting.id, member=winner)


@router.get("/templates", response_model=list[schemas.TemplateResponse])
def list_templates(db: DatabaseSession):
    return crud.list_templates(db)


@router.post(
    "/templates",
    response_model=schemas.TemplateResponse,
    status_code=status.HTTP_201_CREATED,
)
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
def update_template(
    key: str, changes: schemas.TemplateUpdate, db: DatabaseSession
):
    try:
        template = crud.update_template(db, key, changes)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    if template is None:
        raise _not_found("Template not found")
    return template


@router.post(
    "/templates/{key}/restore", response_model=schemas.TemplateResponse
)
def restore_template(key: str, db: DatabaseSession):
    template = crud.restore_template(db, key)
    if template is None:
        raise _not_found("No default exists for this template")
    return template


@router.post(
    "/templates/{key}/render",
    response_model=schemas.TemplateRenderResponse,
)
def render_template(
    key: str, request: schemas.TemplateRenderRequest, db: DatabaseSession
):
    template = crud.get_template(db, key)
    if template is None:
        raise _not_found("Template not found")
    return crud.render_template(
        template,
        request.variables,
        subject_override=request.subject_override,
        body_override=request.body_override,
    )


@router.post(
    "/meetings/{meeting_id}/transit-labels/render",
    response_model=list[schemas.TransitLabelResponse],
)
def render_transit_labels(
    meeting_id: int,
    request: schemas.TransitLabelRequest,
    db: DatabaseSession,
):
    meeting = crud.get_meeting(db, meeting_id)
    if meeting is None:
        raise _not_found("Meeting not found")
    template = crud.get_template(db, "transit_label")
    if template is None:
        raise _not_found("Transit label template not found")
    selected = (
        None if request.member_ids is None else set(request.member_ids)
    )
    labels = []
    for participation in crud.list_participation(db, meeting_id):
        if participation.delivery_method != "transfer":
            continue
        if selected is not None and participation.member_id not in selected:
            continue
        context = crud.template_context(meeting, participation)
        rendered = crud.render_template(
            template,
            context,
            body_override=request.body_override,
        )
        labels.append(
            schemas.TransitLabelResponse(
                member_id=participation.member_id,
                member_name=participation.member.name,
                destination_branch=participation.destination_branch or "",
                body=rendered.body,
                missing_variables=rendered.missing_variables,
            )
        )
    return labels


@router.post(
    "/meetings/{meeting_id}/emails/preview",
    response_model=list[schemas.EmailPreviewResponse],
)
def preview_emails(
    meeting_id: int,
    request: schemas.EmailPreviewRequest,
    db: DatabaseSession,
):
    meeting = crud.get_meeting(db, meeting_id)
    if meeting is None:
        raise _not_found("Meeting not found")
    selected = (
        None if request.member_ids is None else set(request.member_ids)
    )
    previews = []
    onboarding_keys = {
        "pickup": "onboarding_pickup",
        "transfer": "onboarding_transfer",
        "none": "onboarding_no_copy",
    }
    templates: dict[str, models.BookClubTemplate | None] = {}
    for participation in crud.list_participation(db, meeting_id):
        if selected is not None and participation.member_id not in selected:
            continue
        template_key = (
            onboarding_keys[participation.delivery_method]
            if request.email_type == "onboarding"
            else "monthly_reminder"
        )
        if template_key not in templates:
            templates[template_key] = crud.get_template(db, template_key)
        template = templates[template_key]
        if template is None:
            raise _not_found(f"Template {template_key} not found")
        rendered = crud.render_template(
            template,
            crud.template_context(meeting, participation),
            subject_override=request.subject_override,
            body_override=request.body_override,
        )
        previews.append(
            schemas.EmailPreviewResponse(
                member_id=participation.member_id,
                member_name=participation.member.name,
                email=participation.member.email,
                template_key=template_key,
                subject=rendered.subject or "",
                body=rendered.body,
                missing_variables=rendered.missing_variables,
            )
        )
    return previews


@router.get(
    "/meetings/{meeting_id}/questions",
    response_model=list[schemas.DiscussionQuestionResponse],
)
def list_questions(meeting_id: int, db: DatabaseSession):
    if crud.get_meeting(db, meeting_id) is None:
        raise _not_found("Meeting not found")
    return crud.list_questions(db, meeting_id)


@router.post(
    "/meetings/{meeting_id}/questions",
    response_model=schemas.DiscussionQuestionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_question(
    meeting_id: int,
    value: schemas.DiscussionQuestionCreate,
    db: DatabaseSession,
):
    meeting = crud.get_meeting(db, meeting_id)
    if meeting is None:
        raise _not_found("Meeting not found")
    try:
        return crud.create_question(db, meeting, value)
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That question position is already in use",
        ) from exc


@router.patch(
    "/questions/{question_id}",
    response_model=schemas.DiscussionQuestionResponse,
)
def update_question(
    question_id: int,
    changes: schemas.DiscussionQuestionUpdate,
    db: DatabaseSession,
):
    question = crud.update_question(db, question_id, changes)
    if question is None:
        raise _not_found("Discussion question not found")
    return question


@router.delete(
    "/questions/{question_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_question(question_id: int, db: DatabaseSession) -> Response:
    if not crud.delete_question(db, question_id):
        raise _not_found("Discussion question not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
