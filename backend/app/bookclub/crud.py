import re
import secrets
from collections.abc import Mapping
from datetime import date
from typing import Any

from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from bookclub import models, schemas

DEFAULT_TEMPLATES = (
    {
        "key": "onboarding_pickup",
        "name": "New member — pickup at PBRL",
        "kind": "email",
        "subject": "Welcome to the Sci-Fi Book Club",
        "body": (
            "Hi {{first_name}},\n\nWelcome to the Sci-Fi Book Club! "
            "Your copy of {{book_title}} by {{book_author}} will be held "
            "for pickup at {{organizer_branch}}. Our next meeting is "
            "{{meeting_date}}.\n\nJosh"
        ),
    },
    {
        "key": "onboarding_transfer",
        "name": "New member — transfer to another branch",
        "kind": "email",
        "subject": "Welcome to the Sci-Fi Book Club",
        "body": (
            "Hi {{first_name}},\n\nWelcome to the Sci-Fi Book Club! "
            "We will send your copy of {{book_title}} by {{book_author}} "
            "to {{destination_branch}}. Our next meeting is "
            "{{meeting_date}}.\n\nJosh"
        ),
    },
    {
        "key": "onboarding_no_copy",
        "name": "New member — no copy requested",
        "kind": "email",
        "subject": "Welcome to the Sci-Fi Book Club",
        "body": (
            "Hi {{first_name}},\n\nWelcome to the Sci-Fi Book Club! "
            "Our next book is {{book_title}} by {{book_author}}, and we "
            "will meet on {{meeting_date}}.\n\nJosh"
        ),
    },
    {
        "key": "monthly_reminder",
        "name": "Monthly meeting reminder",
        "kind": "email",
        "subject": "Sci-Fi Book Club reminder — {{book_title}}",
        "body": (
            "Hi {{first_name}},\n\nThis is a reminder that the Sci-Fi Book "
            "Club is discussing {{book_title}} by {{book_author}} on "
            "{{meeting_date}}.\n\nJosh"
        ),
    },
    {
        "key": "transit_label",
        "name": "Book transit label",
        "kind": "print",
        "subject": None,
        "body": (
            "SCI-FI BOOK CLUB BOOK\n\nPlease hold for {{member_name}} at "
            "{{destination_branch}}.\n\nPlease contact {{organizer_name}} at "
            "{{organizer_branch}} when this book arrives."
        ),
    },
)

PLACEHOLDER_PATTERN = re.compile(r"{{\s*([a-zA-Z][a-zA-Z0-9_]*)\s*}}")


def _data(
    value: BaseModel | Mapping[str, Any], *, exclude_unset: bool = False
) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        return value.model_dump(exclude_unset=exclude_unset)
    return dict(value)


def _commit(db: Session, instance: Any) -> Any:
    try:
        db.commit()
        db.refresh(instance)
    except SQLAlchemyError:
        db.rollback()
        raise
    return instance


def _club_id(db: Session) -> int:
    club_id = db.info.get("bookclub_id")
    if not isinstance(club_id, int):
        raise RuntimeError("A book club must be selected")
    return club_id


def create_member(
    db: Session, value: schemas.MemberCreate
) -> models.BookClubMember:
    member = models.BookClubMember(club_id=_club_id(db), **value.model_dump())
    db.add(member)
    return _commit(db, member)


def get_member(db: Session, member_id: int) -> models.BookClubMember | None:
    return db.scalar(
        select(models.BookClubMember).where(
            models.BookClubMember.id == member_id,
            models.BookClubMember.club_id == _club_id(db),
        )
    )


def list_members(
    db: Session,
    *,
    active: bool | None = None,
    search: str | None = None,
    offset: int = 0,
    limit: int = 100,
) -> list[models.BookClubMember]:
    statement = select(models.BookClubMember).where(
        models.BookClubMember.club_id == _club_id(db)
    )
    if active is not None:
        statement = statement.where(models.BookClubMember.active == active)
    if search:
        pattern = f"%{search.strip()}%"
        statement = statement.where(
            or_(
                models.BookClubMember.name.ilike(pattern),
                models.BookClubMember.email.ilike(pattern),
            )
        )
    statement = (
        statement.order_by(models.BookClubMember.name, models.BookClubMember.id)
        .offset(offset)
        .limit(limit)
    )
    return list(db.scalars(statement))


def update_member(
    db: Session, member_id: int, changes: schemas.MemberUpdate
) -> models.BookClubMember | None:
    member = get_member(db, member_id)
    if member is None:
        return None
    for field, value in _data(changes, exclude_unset=True).items():
        setattr(member, field, value)
    return _commit(db, member)


def create_book(
    db: Session, value: schemas.BookCreate
) -> models.BookClubBook:
    data = value.model_dump()
    for field in ("cover_image_url", "catalogue_url"):
        if data[field] is not None:
            data[field] = str(data[field])
    book = models.BookClubBook(club_id=_club_id(db), **data)
    db.add(book)
    return _commit(db, book)


def get_book(db: Session, book_id: int) -> models.BookClubBook | None:
    return db.scalar(
        select(models.BookClubBook).where(
            models.BookClubBook.id == book_id,
            models.BookClubBook.club_id == _club_id(db),
        )
    )


def list_books(
    db: Session,
    *,
    search: str | None = None,
    offset: int = 0,
    limit: int = 100,
) -> list[models.BookClubBook]:
    statement = select(models.BookClubBook).where(
        models.BookClubBook.club_id == _club_id(db)
    )
    if search:
        pattern = f"%{search.strip()}%"
        statement = statement.where(
            or_(
                models.BookClubBook.title.ilike(pattern),
                models.BookClubBook.author.ilike(pattern),
                models.BookClubBook.isbn.ilike(pattern),
                models.BookClubBook.genres.ilike(pattern),
            )
        )
    statement = (
        statement.order_by(
            models.BookClubBook.title,
            models.BookClubBook.author,
            models.BookClubBook.id,
        )
        .offset(offset)
        .limit(limit)
    )
    return list(db.scalars(statement))


def update_book(
    db: Session, book_id: int, changes: schemas.BookUpdate
) -> models.BookClubBook | None:
    book = get_book(db, book_id)
    if book is None:
        return None
    data = changes.model_dump(exclude_unset=True)
    for field in ("cover_image_url", "catalogue_url"):
        if field in data and data[field] is not None:
            data[field] = str(data[field])
    for field, value in data.items():
        setattr(book, field, value)
    if "title" in data or "author" in data:
        for meeting in book.meetings:
            meeting.book_title = book.title
            meeting.book_author = book.author
    return _commit(db, book)


def delete_book(db: Session, book_id: int) -> str:
    book = get_book(db, book_id)
    if book is None:
        return "not_found"
    meeting_count = db.scalar(
        select(func.count(models.BookClubMeeting.id)).where(
            models.BookClubMeeting.book_id == book_id,
            models.BookClubMeeting.club_id == _club_id(db),
        )
    )
    if meeting_count:
        return "in_use"
    try:
        db.delete(book)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    return "deleted"


def create_meeting(
    db: Session,
    value: schemas.MeetingCreate,
    book: models.BookClubBook,
) -> models.BookClubMeeting:
    data = value.model_dump(exclude={"add_active_members", "book_id"})
    meeting = models.BookClubMeeting(
        **data,
        club_id=_club_id(db),
        book=book,
        book_title=book.title,
        book_author=book.author,
    )
    if value.add_active_members:
        members = db.scalars(
            select(models.BookClubMember)
            .where(
                models.BookClubMember.active.is_(True),
                models.BookClubMember.club_id == _club_id(db),
            )
            .order_by(models.BookClubMember.id)
        )
        meeting.participants = [
            models.BookClubParticipation(member=member) for member in members
        ]
    db.add(meeting)
    return _commit(db, meeting)


def get_meeting(
    db: Session, meeting_id: int
) -> models.BookClubMeeting | None:
    return db.scalar(
        select(models.BookClubMeeting)
        .options(selectinload(models.BookClubMeeting.book))
        .where(models.BookClubMeeting.id == meeting_id)
        .where(models.BookClubMeeting.club_id == _club_id(db))
    )


def list_meetings(
    db: Session,
    *,
    from_date: date | None = None,
    offset: int = 0,
    limit: int = 100,
) -> list[models.BookClubMeeting]:
    statement = select(models.BookClubMeeting).options(
        selectinload(models.BookClubMeeting.book)
    ).where(models.BookClubMeeting.club_id == _club_id(db))
    if from_date is not None:
        statement = statement.where(
            models.BookClubMeeting.meeting_date >= from_date
        )
    statement = (
        statement.order_by(
            models.BookClubMeeting.meeting_date.desc(),
            models.BookClubMeeting.id.desc(),
        )
        .offset(offset)
        .limit(limit)
    )
    return list(db.scalars(statement))


def update_meeting(
    db: Session, meeting_id: int, changes: schemas.MeetingUpdate
) -> models.BookClubMeeting | None:
    meeting = get_meeting(db, meeting_id)
    if meeting is None:
        return None
    data = _data(changes, exclude_unset=True)
    book_id = data.pop("book_id", None)
    if book_id is not None:
        book = get_book(db, book_id)
        if book is None:
            raise LookupError("Book not found")
        meeting.book = book
        meeting.book_title = book.title
        meeting.book_author = book.author
    for field, value in data.items():
        setattr(meeting, field, value)
    return _commit(db, meeting)


def delete_meeting(db: Session, meeting_id: int) -> bool:
    meeting = get_meeting(db, meeting_id)
    if meeting is None:
        return False
    try:
        db.delete(meeting)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    return True


def get_participation(
    db: Session, meeting_id: int, member_id: int
) -> models.BookClubParticipation | None:
    statement = select(models.BookClubParticipation).where(
        models.BookClubParticipation.meeting_id == meeting_id,
        models.BookClubParticipation.member_id == member_id,
    )
    return db.scalar(statement)


def update_participation(
    db: Session,
    meeting: models.BookClubMeeting,
    member: models.BookClubMember,
    changes: schemas.ParticipationUpdate,
) -> models.BookClubParticipation:
    participation = get_participation(db, meeting.id, member.id)
    if participation is None:
        participation = models.BookClubParticipation(
            meeting=meeting, member=member
        )
        db.add(participation)
    for field, value in _data(changes, exclude_unset=True).items():
        setattr(participation, field, value)
    if participation.delivery_method != "transfer":
        participation.destination_branch = None
    elif not participation.destination_branch:
        raise ValueError("destination_branch is required for a transfer")
    return _commit(db, participation)


def list_participation(
    db: Session, meeting_id: int
) -> list[models.BookClubParticipation]:
    statement = (
        select(models.BookClubParticipation)
        .options(selectinload(models.BookClubParticipation.member))
        .where(models.BookClubParticipation.meeting_id == meeting_id)
        .join(models.BookClubMember)
        .order_by(models.BookClubMember.name, models.BookClubMember.id)
    )
    return list(db.scalars(statement))


def sync_roster(db: Session, meeting_id: int) -> tuple[int, int] | None:
    meeting = get_meeting(db, meeting_id)
    if meeting is None:
        return None
    existing_ids = set(
        db.scalars(
            select(models.BookClubParticipation.member_id).where(
                models.BookClubParticipation.meeting_id == meeting_id
            )
        )
    )
    members = list(
        db.scalars(
            select(models.BookClubMember).where(
                models.BookClubMember.active.is_(True),
                models.BookClubMember.club_id == _club_id(db),
                models.BookClubMember.id.not_in(existing_ids),
            )
        )
    )
    db.add_all(
        [
            models.BookClubParticipation(meeting=meeting, member=member)
            for member in members
        ]
    )
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    total = db.scalar(
        select(func.count(models.BookClubParticipation.id)).where(
            models.BookClubParticipation.meeting_id == meeting_id
        )
    )
    return len(members), int(total or 0)


def list_recipients(
    db: Session, meeting_id: int, recipient_filter: schemas.RecipientFilter
) -> list[models.BookClubMember]:
    statement = (
        select(models.BookClubMember)
        .join(models.BookClubParticipation)
        .where(
            models.BookClubParticipation.meeting_id == meeting_id,
            models.BookClubMember.active.is_(True),
        )
    )
    participation = models.BookClubParticipation
    filters = {
        "checked_out": participation.book_checked_out.is_(True),
        "not_checked_out": participation.book_checked_out.is_(False),
        "pickup": participation.delivery_method == "pickup",
        "transfer": participation.delivery_method == "transfer",
        "no_copy": participation.delivery_method == "none",
    }
    if recipient_filter != "all":
        statement = statement.where(filters[recipient_filter])
    return list(
        db.scalars(statement.order_by(models.BookClubMember.name)).unique()
    )


def member_history(
    db: Session, member_id: int
) -> list[models.BookClubParticipation]:
    statement = (
        select(models.BookClubParticipation)
        .options(
            selectinload(models.BookClubParticipation.meeting).selectinload(
                models.BookClubMeeting.book
            )
        )
        .where(models.BookClubParticipation.member_id == member_id)
        .join(models.BookClubMeeting)
        .order_by(
            models.BookClubMeeting.meeting_date.desc(),
            models.BookClubMeeting.id.desc(),
        )
    )
    return list(db.scalars(statement))


def draw_giveaway_winner(
    db: Session, meeting: models.BookClubMeeting, *, redraw: bool = False
) -> models.BookClubMember:
    if meeting.giveaway_winner_member_id is not None and not redraw:
        winner = get_member(db, meeting.giveaway_winner_member_id)
        if winner is not None:
            return winner
    attendees = list(
        db.scalars(
            select(models.BookClubMember)
            .join(models.BookClubParticipation)
            .where(
                models.BookClubParticipation.meeting_id == meeting.id,
                models.BookClubParticipation.attended.is_(True),
            )
        )
    )
    if not attendees:
        raise ValueError("No attendees are recorded for this meeting")
    winner = secrets.choice(attendees)
    meeting.giveaway_winner_member_id = winner.id
    _commit(db, meeting)
    return winner


def ensure_default_templates(db: Session) -> None:
    club_id = _club_id(db)
    existing = set(
        db.scalars(
            select(models.BookClubTemplate.key).where(
                models.BookClubTemplate.club_id == club_id
            )
        )
    )
    additions = [
        models.BookClubTemplate(club_id=club_id, **value)
        for value in DEFAULT_TEMPLATES
        if value["key"] not in existing
    ]
    if additions:
        db.add_all(additions)
        db.commit()


def list_templates(db: Session) -> list[models.BookClubTemplate]:
    ensure_default_templates(db)
    return list(
        db.scalars(
            select(models.BookClubTemplate).order_by(
                models.BookClubTemplate.kind, models.BookClubTemplate.name
            ).where(models.BookClubTemplate.club_id == _club_id(db))
        )
    )


def get_template(
    db: Session, key: str
) -> models.BookClubTemplate | None:
    ensure_default_templates(db)
    return db.scalar(
        select(models.BookClubTemplate).where(
            models.BookClubTemplate.key == key,
            models.BookClubTemplate.club_id == _club_id(db),
        )
    )


def create_template(
    db: Session, value: schemas.TemplateCreate
) -> models.BookClubTemplate:
    template = models.BookClubTemplate(
        club_id=_club_id(db), **value.model_dump()
    )
    db.add(template)
    return _commit(db, template)


def update_template(
    db: Session, key: str, changes: schemas.TemplateUpdate
) -> models.BookClubTemplate | None:
    template = get_template(db, key)
    if template is None:
        return None
    for field, value in _data(changes, exclude_unset=True).items():
        setattr(template, field, value)
    if template.kind == "email" and not template.subject:
        raise ValueError("email templates require a subject")
    return _commit(db, template)


def restore_template(
    db: Session, key: str
) -> models.BookClubTemplate | None:
    default = next((item for item in DEFAULT_TEMPLATES if item["key"] == key), None)
    if default is None:
        return None
    template = get_template(db, key)
    if template is None:
        template = models.BookClubTemplate(club_id=_club_id(db), **default)
        db.add(template)
    else:
        for field in ("name", "kind", "subject", "body"):
            setattr(template, field, default[field])
    return _commit(db, template)


def render_text(
    value: str | None, variables: Mapping[str, Any]
) -> tuple[str | None, set[str]]:
    if value is None:
        return None, set()
    missing: set[str] = set()

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        replacement = variables.get(key)
        if replacement is None:
            missing.add(key)
            return match.group(0)
        return str(replacement)

    return PLACEHOLDER_PATTERN.sub(replace, value), missing


def render_template(
    template: models.BookClubTemplate,
    variables: Mapping[str, Any],
    *,
    subject_override: str | None = None,
    body_override: str | None = None,
) -> schemas.TemplateRenderResponse:
    subject, subject_missing = render_text(
        subject_override if subject_override is not None else template.subject,
        variables,
    )
    body, body_missing = render_text(
        body_override if body_override is not None else template.body,
        variables,
    )
    return schemas.TemplateRenderResponse(
        subject=subject,
        body=body or "",
        missing_variables=sorted(subject_missing | body_missing),
    )


def template_context(
    meeting: models.BookClubMeeting,
    participation: models.BookClubParticipation,
    *,
    organizer_name: str | None = None,
    organizer_branch: str | None = None,
) -> dict[str, Any]:
    member = participation.member
    club = meeting.club
    return {
        "first_name": member.name.split()[0],
        "member_name": member.name,
        "email": member.email,
        "book_title": meeting.book.title,
        "book_author": meeting.book.author,
        "meeting_date": meeting.meeting_date.isoformat(),
        "meeting_time": meeting.meeting_time,
        "meeting_location": meeting.location,
        "destination_branch": participation.destination_branch,
        "organizer_name": organizer_name or club.organizer_name or "Facilitator",
        "organizer_branch": organizer_branch or club.organizer_branch or "the library",
    }


def create_question(
    db: Session,
    meeting: models.BookClubMeeting,
    value: schemas.DiscussionQuestionCreate,
) -> models.BookClubDiscussionQuestion:
    position = value.position
    if position is None:
        highest = db.scalar(
            select(func.max(models.BookClubDiscussionQuestion.position)).where(
                models.BookClubDiscussionQuestion.meeting_id == meeting.id
            )
        )
        position = int(highest or 0) + 1
    question = models.BookClubDiscussionQuestion(
        meeting=meeting, position=position, text=value.text
    )
    db.add(question)
    return _commit(db, question)


def list_questions(
    db: Session, meeting_id: int
) -> list[models.BookClubDiscussionQuestion]:
    return list(
        db.scalars(
            select(models.BookClubDiscussionQuestion)
            .where(models.BookClubDiscussionQuestion.meeting_id == meeting_id)
            .order_by(models.BookClubDiscussionQuestion.position)
        )
    )


def update_question(
    db: Session, question_id: int, changes: schemas.DiscussionQuestionUpdate
) -> models.BookClubDiscussionQuestion | None:
    question = db.scalar(
        select(models.BookClubDiscussionQuestion)
        .join(models.BookClubMeeting)
        .where(
            models.BookClubDiscussionQuestion.id == question_id,
            models.BookClubMeeting.club_id == _club_id(db),
        )
    )
    if question is None:
        return None
    data = changes.model_dump(exclude_unset=True)
    new_position = data.pop("position", None)
    if "text" in data:
        question.text = data["text"]
    if new_position is not None and new_position != question.position:
        other = db.scalar(
            select(models.BookClubDiscussionQuestion).where(
                models.BookClubDiscussionQuestion.meeting_id
                == question.meeting_id,
                models.BookClubDiscussionQuestion.position == new_position,
            )
        )
        old_position = question.position
        question.position = -question.id
        db.flush()
        if other is not None:
            other.position = old_position
            db.flush()
        question.position = new_position
    return _commit(db, question)


def delete_question(db: Session, question_id: int) -> bool:
    question = db.scalar(
        select(models.BookClubDiscussionQuestion)
        .join(models.BookClubMeeting)
        .where(
            models.BookClubDiscussionQuestion.id == question_id,
            models.BookClubMeeting.club_id == _club_id(db),
        )
    )
    if question is None:
        return False
    try:
        db.delete(question)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    return True
