import re
import secrets
import urllib.parse
from collections.abc import Mapping
from datetime import date, datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel
from sqlalchemy import and_, case, delete, func, or_, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from bookclub import email_delivery, models, schemas
from bookclub.participant_models import ParticipantAccount
from bookclub.participant_schemas import RatingSubmit
from bookclub.scheduling import meeting_datetime_range, parse_meeting_time
from security import hash_password

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
        "key": "book_arrived",
        "name": "New member — book arrived at branch",
        "kind": "email",
        "subject": "Your Sci-Fi Book Club book has arrived",
        "body": (
            "Hi {{first_name}},\n\nYour copy of {{book_title}} by "
            "{{book_author}} has arrived at {{destination_branch}} and is "
            "ready for pickup!\n\nJosh"
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

ONBOARDING_TEMPLATE_KEYS = {
    "pickup": "onboarding_pickup",
    "transfer": "onboarding_transfer",
    "none": "onboarding_no_copy",
}


def onboarding_template_key(delivery_method: str) -> str:
    return ONBOARDING_TEMPLATE_KEYS[delivery_method]


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
    data = value.model_dump()
    if data["delivery_method"] != "transfer":
        data["destination_branch"] = None
    member = models.BookClubMember(club_id=_club_id(db), **data)
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
    if member.delivery_method != "transfer":
        member.destination_branch = None
    elif not member.destination_branch:
        raise ValueError("destination_branch is required for a transfer")
    return _commit(db, member)


def delete_member(db: Session, member_id: int) -> bool:
    member = get_member(db, member_id)
    if member is None:
        return False
    try:
        db.execute(
            update(models.BookClubMeeting)
            .where(
                models.BookClubMeeting.club_id == _club_id(db),
                models.BookClubMeeting.giveaway_winner_member_id == member_id,
            )
            .values(giveaway_winner_member_id=None)
        )
        db.execute(
            delete(models.BookClubParticipation).where(
                models.BookClubParticipation.member_id == member_id
            )
        )
        db.delete(member)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    return True


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
    data = value.model_dump(exclude={"book_id"})
    meeting = models.BookClubMeeting(
        **data,
        club_id=_club_id(db),
        book=book,
        book_title=book.title,
        book_author=book.author,
    )
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


def list_book_meetings(
    db: Session, book_id: int
) -> list[models.BookClubMeeting]:
    return list(
        db.scalars(
            select(models.BookClubMeeting)
            .options(selectinload(models.BookClubMeeting.participants))
            .where(
                models.BookClubMeeting.club_id == _club_id(db),
                models.BookClubMeeting.book_id == book_id,
            )
            .order_by(
                models.BookClubMeeting.meeting_date.desc(),
                models.BookClubMeeting.id.desc(),
            )
        )
    )


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
    return _commit(db, participation)


def remove_participation(db: Session, meeting_id: int, member_id: int) -> bool:
    participation = get_participation(db, meeting_id, member_id)
    if participation is None:
        return False
    try:
        db.delete(participation)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    return True


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


def get_previous_meeting(
    db: Session, meeting: models.BookClubMeeting
) -> models.BookClubMeeting | None:
    return db.scalar(
        select(models.BookClubMeeting)
        .where(models.BookClubMeeting.club_id == _club_id(db))
        .where(
            or_(
                models.BookClubMeeting.meeting_date < meeting.meeting_date,
                and_(
                    models.BookClubMeeting.meeting_date == meeting.meeting_date,
                    models.BookClubMeeting.id < meeting.id,
                ),
            )
        )
        .order_by(
            models.BookClubMeeting.meeting_date.desc(),
            models.BookClubMeeting.id.desc(),
        )
        .limit(1)
    )


def import_previous_attendees(
    db: Session, meeting: models.BookClubMeeting
) -> list[models.BookClubParticipation]:
    previous = get_previous_meeting(db, meeting)
    if previous is None:
        raise LookupError("There is no previous meeting to import attendees from")
    attended_ids = {
        participation.member_id
        for participation in list_participation(db, previous.id)
        if participation.attended
    }
    existing_ids = {
        participation.member_id
        for participation in list_participation(db, meeting.id)
    }
    for member_id in attended_ids - existing_ids:
        db.add(
            models.BookClubParticipation(
                meeting_id=meeting.id, member_id=member_id
            )
        )
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    return list_participation(db, meeting.id)


def member_participation_summary(
    db: Session,
) -> list[schemas.MemberParticipationSummary]:
    club_id = _club_id(db)
    member = models.BookClubMember
    participation = models.BookClubParticipation
    meeting = models.BookClubMeeting
    book = models.BookClubBook

    attended_date = case(
        (participation.attended.is_(True), meeting.meeting_date), else_=None
    )
    statement = (
        select(
            member,
            func.count(participation.id),
            func.sum(case((participation.attended.is_(True), 1), else_=0)),
            func.max(attended_date),
            func.sum(
                case(
                    (
                        participation.attended.is_(True),
                        func.coalesce(book.page_count, 0),
                    ),
                    else_=0,
                )
            ),
        )
        .outerjoin(participation, participation.member_id == member.id)
        .outerjoin(meeting, meeting.id == participation.meeting_id)
        .outerjoin(book, book.id == meeting.book_id)
        .where(member.club_id == club_id)
        .group_by(member.id)
        .order_by(member.name)
    )
    rows = db.execute(statement).all()

    giveaway_counts = dict(
        db.execute(
            select(meeting.giveaway_winner_member_id, func.count(meeting.id))
            .where(
                meeting.club_id == club_id,
                meeting.giveaway_winner_member_id.is_not(None),
            )
            .group_by(meeting.giveaway_winner_member_id)
        ).all()
    )

    all_meeting_dates = list(
        db.scalars(
            select(meeting.meeting_date)
            .where(meeting.club_id == club_id)
            .order_by(meeting.meeting_date)
        )
    )

    def meetings_since(reference_date: date) -> int:
        return sum(1 for entry in all_meeting_dates if entry > reference_date)

    summaries = []
    for (
        member_obj,
        meetings_total,
        attended_count,
        last_attended_date,
        pages_read,
    ) in rows:
        contacted_candidates = [
            value
            for value in (
                member_obj.onboarding_email_sent_at,
                member_obj.last_reminder_sent_at,
            )
            if value is not None
        ]
        reference_date = last_attended_date or member_obj.joined_on
        summaries.append(
            schemas.MemberParticipationSummary(
                member=member_obj,
                meetings_total=int(meetings_total or 0),
                attended_count=int(attended_count or 0),
                giveaways_won=giveaway_counts.get(member_obj.id, 0),
                pages_read=int(pages_read or 0),
                last_attended_date=last_attended_date,
                last_contacted_at=max(contacted_candidates) if contacted_candidates else None,
                meetings_since_last_attended=meetings_since(reference_date),
            )
        )
    return summaries


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


def render_onboarding_email(
    db: Session,
    meeting: models.BookClubMeeting,
    member: models.BookClubMember,
) -> schemas.TemplateRenderResponse:
    template_key = onboarding_template_key(member.delivery_method)
    template = get_template(db, template_key)
    if template is None:
        raise LookupError(f"Template {template_key} not found")
    return render_template(template, template_context(meeting, member))


def send_onboarding_email(
    db: Session,
    meeting: models.BookClubMeeting,
    member: models.BookClubMember,
) -> schemas.OnboardingSendResponse:
    rendered = render_onboarding_email(db, meeting, member)
    already_sent_before = member.onboarding_email_sent_at is not None
    sent = email_delivery.send_onboarding_email(
        recipient=member.email,
        subject=rendered.subject or "",
        body=rendered.body,
    )
    member.onboarding_email_sent_at = datetime.now(timezone.utc)
    _commit(db, member)
    return schemas.OnboardingSendResponse(
        member_id=member.id, sent=sent, already_sent_before=already_sent_before
    )


def mark_onboarding_email_sent(
    db: Session,
    member: models.BookClubMember,
) -> schemas.OnboardingSendResponse:
    """Record that the welcome email was sent outside the website (e.g. the
    staff member copied the composed text and sent it from their own inbox)."""
    already_sent_before = member.onboarding_email_sent_at is not None
    member.onboarding_email_sent_at = datetime.now(timezone.utc)
    _commit(db, member)
    return schemas.OnboardingSendResponse(
        member_id=member.id, sent=True, already_sent_before=already_sent_before
    )


def render_arrival_email(
    db: Session,
    meeting: models.BookClubMeeting,
    member: models.BookClubMember,
) -> schemas.TemplateRenderResponse:
    template = get_template(db, "book_arrived")
    if template is None:
        raise LookupError("Template book_arrived not found")
    return render_template(template, template_context(meeting, member))


def send_arrival_email(
    db: Session,
    meeting: models.BookClubMeeting,
    member: models.BookClubMember,
) -> schemas.OnboardingSendResponse:
    rendered = render_arrival_email(db, meeting, member)
    already_sent_before = member.arrival_email_sent_at is not None
    sent = email_delivery.send_onboarding_email(
        recipient=member.email,
        subject=rendered.subject or "",
        body=rendered.body,
    )
    member.arrival_email_sent_at = datetime.now(timezone.utc)
    _commit(db, member)
    return schemas.OnboardingSendResponse(
        member_id=member.id, sent=sent, already_sent_before=already_sent_before
    )


def mark_arrival_email_sent(
    db: Session,
    member: models.BookClubMember,
) -> schemas.OnboardingSendResponse:
    """Record that the arrival email was sent outside the website."""
    already_sent_before = member.arrival_email_sent_at is not None
    member.arrival_email_sent_at = datetime.now(timezone.utc)
    _commit(db, member)
    return schemas.OnboardingSendResponse(
        member_id=member.id, sent=True, already_sent_before=already_sent_before
    )


def transit_label_context(
    db: Session,
    member: models.BookClubMember,
    destination_branch: str,
    *,
    organizer_name: str | None = None,
    organizer_branch: str | None = None,
) -> dict[str, Any]:
    club = db.get(models.BookClub, _club_id(db))
    return {
        "member_name": member.name,
        "destination_branch": destination_branch,
        "organizer_name": organizer_name or club.organizer_name or "Facilitator",
        "organizer_branch": organizer_branch or club.organizer_branch or "the library",
    }


def mark_transit_label_printed(
    db: Session,
    member: models.BookClubMember,
    destination_branch: str,
) -> models.BookClubMember:
    member.delivery_method = "transfer"
    member.destination_branch = destination_branch
    member.transit_label_printed_at = datetime.now(timezone.utc)
    return _commit(db, member)


def send_reminder_batch(
    db: Session,
    meeting: models.BookClubMeeting,
    members: list[models.BookClubMember],
) -> schemas.ReminderSendResponse:
    rendered = render_reminder_email(db, meeting)
    already_sent_before = meeting.reminder_sent_at is not None
    sent = email_delivery.send_reminder_batch(
        recipients=[member.email for member in members],
        subject=rendered.subject or "",
        body=rendered.body,
    )
    now = datetime.now(timezone.utc)
    meeting.reminder_sent_at = now
    for member in members:
        member.last_reminder_sent_at = now
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    return schemas.ReminderSendResponse(
        sent=sent,
        recipient_count=len(members),
        already_sent_before=already_sent_before,
    )


def mark_reminder_sent(
    db: Session,
    meeting: models.BookClubMeeting,
) -> schemas.ReminderSendResponse:
    """Record that the reminder was sent outside the website (e.g. the
    staff member copied the composed text and sent it from their own inbox)."""
    already_sent_before = meeting.reminder_sent_at is not None
    now = datetime.now(timezone.utc)
    meeting.reminder_sent_at = now
    participants = list_participation(db, meeting.id)
    for participation in participants:
        participation.member.last_reminder_sent_at = now
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    return schemas.ReminderSendResponse(
        sent=True,
        recipient_count=len(participants),
        already_sent_before=already_sent_before,
    )


def render_reminder_email(
    db: Session,
    meeting: models.BookClubMeeting,
) -> schemas.TemplateRenderResponse:
    template = get_template(db, "monthly_reminder")
    if template is None:
        raise LookupError("Template monthly_reminder not found")
    return render_template(template, meeting_template_context(meeting))


def ensure_default_templates(db: Session) -> None:
    club_id = _club_id(db)
    club = db.get(models.BookClub, club_id)
    # DEFAULT_TEMPLATES is hardcoded library-specific content (physical
    # pickup/transfer copy, a named organizer) — meaningless, confusing
    # content for a private club, so it is never auto-seeded there.
    # Private clubs start with zero templates; facilitators create their
    # own. This is called from list_templates/get_template (and therefore
    # update_template), so guarding here covers every read path.
    if club is not None and club.club_type != "library":
        return
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


def build_calendar_link(
    meeting: models.BookClubMeeting,
    video_call_url: str | None,
    *,
    include_notes: bool = True,
) -> str:
    """A Google Calendar "add event" link for a meeting.

    meeting_time is free-text (e.g. "7:00 PM"), so this degrades to an
    all-day event rather than erroring when it can't be parsed.
    """
    time_range = meeting_datetime_range(
        meeting.meeting_date, meeting.meeting_time, meeting.meeting_duration_minutes
    )
    params: dict[str, str] = {
        "action": "TEMPLATE",
        "text": f"Book club: {meeting.book.title}",
    }
    if time_range is not None:
        start, end = time_range
        params["dates"] = (
            f"{start.strftime('%Y%m%dT%H%M%S')}/{end.strftime('%Y%m%dT%H%M%S')}"
        )
    else:
        start_date = meeting.meeting_date
        end_date = start_date + timedelta(days=1)
        params["dates"] = (
            f"{start_date.strftime('%Y%m%d')}/{end_date.strftime('%Y%m%d')}"
        )
    if meeting.location:
        params["location"] = meeting.location
    details_parts = [meeting.notes] if include_notes and meeting.notes else []
    if video_call_url:
        details_parts.append(f"Join via Zoom: {video_call_url}")
    if details_parts:
        params["details"] = "\n\n".join(details_parts)
    return f"https://calendar.google.com/calendar/render?{urllib.parse.urlencode(params)}"


def meeting_template_context(
    meeting: models.BookClubMeeting,
    *,
    organizer_name: str | None = None,
    organizer_branch: str | None = None,
) -> dict[str, Any]:
    """Meeting-level template variables only — no per-member fields.

    Used for the weekly reminder batch, which is one email BCC'd to many
    people rather than a personalized send.
    """
    club = meeting.club
    video_call_url = club.video_call_url
    return {
        "first_name": "everyone",
        "book_title": meeting.book.title,
        "book_author": meeting.book.author,
        "meeting_date": meeting.meeting_date.isoformat(),
        "meeting_time": meeting.meeting_time,
        "meeting_location": meeting.location,
        "organizer_name": organizer_name or club.organizer_name or "Facilitator",
        "organizer_branch": organizer_branch or club.organizer_branch or "the library",
        "video_call_url": video_call_url,
        "calendar_link": build_calendar_link(meeting, video_call_url),
    }


def template_context(
    meeting: models.BookClubMeeting,
    member: models.BookClubMember,
    *,
    organizer_name: str | None = None,
    organizer_branch: str | None = None,
) -> dict[str, Any]:
    club = meeting.club
    video_call_url = club.video_call_url
    return {
        "first_name": member.name.split()[0],
        "member_name": member.name,
        "email": member.email,
        "book_title": meeting.book.title,
        "book_author": meeting.book.author,
        "meeting_date": meeting.meeting_date.isoformat(),
        "meeting_time": meeting.meeting_time,
        "meeting_location": meeting.location,
        "destination_branch": member.destination_branch,
        "organizer_name": organizer_name or club.organizer_name or "Facilitator",
        "organizer_branch": organizer_branch or club.organizer_branch or "the library",
        "video_call_url": video_call_url,
        "calendar_link": build_calendar_link(meeting, video_call_url),
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


def get_book_ratings(db: Session, book_id: int) -> list[tuple[models.BookClubRating, str]]:
    rows = db.execute(
        select(models.BookClubRating, ParticipantAccount.name)
        .join(ParticipantAccount, ParticipantAccount.id == models.BookClubRating.participant_id)
        .where(
            models.BookClubRating.book_id == book_id,
            models.BookClubRating.club_id == _club_id(db),
        )
        .order_by(models.BookClubRating.created_at)
    ).all()
    return [(rating, name) for rating, name in rows]


def get_own_rating(db: Session, book_id: int, participant_id: int) -> models.BookClubRating | None:
    return db.scalar(
        select(models.BookClubRating).where(
            models.BookClubRating.book_id == book_id,
            models.BookClubRating.participant_id == participant_id,
            models.BookClubRating.club_id == _club_id(db),
        )
    )


def upsert_rating(
    db: Session, book_id: int, participant_id: int, value: RatingSubmit
) -> models.BookClubRating:
    rating = get_own_rating(db, book_id, participant_id)
    if rating is None:
        rating = models.BookClubRating(
            club_id=_club_id(db), book_id=book_id, participant_id=participant_id
        )
        db.add(rating)
    rating.rating = value.rating
    rating.review_text = value.review_text
    return _commit(db, rating)


def delete_rating(db: Session, book_id: int, participant_id: int) -> bool:
    rating = get_own_rating(db, book_id, participant_id)
    if rating is None:
        return False
    db.delete(rating)
    db.commit()
    return True


def get_current_voting_round(db: Session) -> models.BookClubVotingRound | None:
    return db.scalar(
        select(models.BookClubVotingRound)
        .where(models.BookClubVotingRound.club_id == _club_id(db))
        .order_by(models.BookClubVotingRound.created_at.desc())
    )


def get_open_voting_round(db: Session) -> models.BookClubVotingRound | None:
    return db.scalar(
        select(models.BookClubVotingRound).where(
            models.BookClubVotingRound.club_id == _club_id(db),
            models.BookClubVotingRound.status == "open",
        )
    )


def open_voting_round(
    db: Session, candidate_book_ids: list[int], proposer_id: int | None
) -> models.BookClubVotingRound:
    if get_open_voting_round(db) is not None:
        raise ValueError("A voting round is already open")
    round_ = models.BookClubVotingRound(club_id=_club_id(db), status="open")
    db.add(round_)
    db.flush()
    for book_id in candidate_book_ids:
        db.add(
            models.BookClubBookCandidate(
                voting_round_id=round_.id,
                book_id=book_id,
                proposed_by_participant_id=proposer_id,
                status="approved",
            )
        )
    return _commit(db, round_)


def add_candidate(
    db: Session, voting_round_id: int, book_id: int, proposer_id: int | None, *, auto_approve: bool
) -> models.BookClubBookCandidate:
    candidate = models.BookClubBookCandidate(
        voting_round_id=voting_round_id,
        book_id=book_id,
        proposed_by_participant_id=proposer_id,
        status="approved" if auto_approve else "pending",
    )
    db.add(candidate)
    return _commit(db, candidate)


def list_candidates(db: Session, voting_round_id: int) -> list[models.BookClubBookCandidate]:
    return list(
        db.scalars(
            select(models.BookClubBookCandidate)
            .options(selectinload(models.BookClubBookCandidate.book))
            .where(models.BookClubBookCandidate.voting_round_id == voting_round_id)
            .order_by(models.BookClubBookCandidate.created_at)
        )
    )


def get_candidate(db: Session, candidate_id: int) -> models.BookClubBookCandidate | None:
    return db.scalar(
        select(models.BookClubBookCandidate)
        .join(models.BookClubVotingRound)
        .where(
            models.BookClubBookCandidate.id == candidate_id,
            models.BookClubVotingRound.club_id == _club_id(db),
        )
    )


def set_candidate_status(
    db: Session, candidate_id: int, value: str
) -> models.BookClubBookCandidate | None:
    candidate = get_candidate(db, candidate_id)
    if candidate is None:
        return None
    candidate.status = value
    return _commit(db, candidate)


def candidate_proposer_names(
    db: Session, candidates: list[models.BookClubBookCandidate]
) -> dict[int, str]:
    participant_ids = {c.proposed_by_participant_id for c in candidates if c.proposed_by_participant_id}
    if not participant_ids:
        return {}
    rows = db.execute(
        select(ParticipantAccount.id, ParticipantAccount.name).where(
            ParticipantAccount.id.in_(participant_ids)
        )
    ).all()
    return dict(rows)


def vote_counts(db: Session, voting_round_id: int) -> dict[int, int]:
    rows = db.execute(
        select(models.BookClubVote.candidate_id, func.count())
        .where(models.BookClubVote.voting_round_id == voting_round_id)
        .group_by(models.BookClubVote.candidate_id)
    ).all()
    return dict(rows)


def get_own_vote(db: Session, voting_round_id: int, participant_id: int) -> models.BookClubVote | None:
    return db.scalar(
        select(models.BookClubVote).where(
            models.BookClubVote.voting_round_id == voting_round_id,
            models.BookClubVote.participant_id == participant_id,
        )
    )


def cast_vote(
    db: Session, voting_round_id: int, candidate_id: int, participant_id: int
) -> models.BookClubVote:
    vote = get_own_vote(db, voting_round_id, participant_id)
    if vote is None:
        vote = models.BookClubVote(
            voting_round_id=voting_round_id, participant_id=participant_id, candidate_id=candidate_id
        )
        db.add(vote)
    else:
        vote.candidate_id = candidate_id
    return _commit(db, vote)


def remove_vote(db: Session, voting_round_id: int, participant_id: int) -> bool:
    vote = get_own_vote(db, voting_round_id, participant_id)
    if vote is None:
        return False
    db.delete(vote)
    db.commit()
    return True


def close_voting_round(db: Session, voting_round_id: int) -> models.BookClubVotingRound:
    round_ = db.get(models.BookClubVotingRound, voting_round_id)
    if round_ is None or round_.club_id != _club_id(db):
        raise LookupError("Voting round not found")
    if round_.status != "open":
        raise ValueError("This voting round is already closed")
    counts = vote_counts(db, voting_round_id)
    approved = [c for c in list_candidates(db, voting_round_id) if c.status == "approved"]
    # Ties go to whichever approved candidate was proposed first (lowest id).
    winner = max(approved, key=lambda c: (counts.get(c.id, 0), -c.id), default=None) if approved else None
    round_.status = "closed"
    round_.closed_at = datetime.now(timezone.utc)
    round_.winning_book_id = winner.book_id if winner else None
    return _commit(db, round_)


def get_or_create_facilitator_participant(
    db: Session, club: models.BookClub, *, name: str, email: str
) -> ParticipantAccount:
    """Find-or-create the ParticipantAccount/BookClubMember pair a facilitator
    uses to preview their own club as a reader would see it. Matched by
    email, same as every other participant<->roster link in this package -
    if the facilitator already reads this (or another) club under this
    email, this reuses that identity instead of creating a duplicate.
    """
    cleaned_email = email.strip().casefold()
    participant = db.scalar(
        select(ParticipantAccount).where(
            func.lower(ParticipantAccount.email) == cleaned_email
        )
    )
    if participant is None:
        participant = ParticipantAccount(
            name=name,
            email=cleaned_email,
            password_hash=hash_password(secrets.token_urlsafe(32)),
            email_verified_at=datetime.now(timezone.utc),
        )
        db.add(participant)
        db.flush()
    member = db.scalar(
        select(models.BookClubMember).where(
            models.BookClubMember.club_id == club.id,
            func.lower(models.BookClubMember.email) == cleaned_email,
        )
    )
    if member is None:
        member = models.BookClubMember(
            club_id=club.id,
            name=name,
            email=cleaned_email,
            participant_account_id=participant.id,
            joined_on=date.today(),
            active=True,
            notes="Added automatically so the facilitator could preview the reader experience.",
        )
        db.add(member)
    else:
        member.participant_account_id = participant.id
        member.active = True
    db.commit()
    db.refresh(participant)
    return participant


# ---- meeting-date polling: a deliberately independent system from book
# voting above, not a shared generalized poll (see BookClubDatePoll's
# docstring in models.py). Mirrors the same shape, minus the candidate
# approval queue, since date options are facilitator-only.


def get_current_date_poll(db: Session) -> models.BookClubDatePoll | None:
    return db.scalar(
        select(models.BookClubDatePoll)
        .where(models.BookClubDatePoll.club_id == _club_id(db))
        .order_by(models.BookClubDatePoll.created_at.desc())
    )


def get_open_date_poll(db: Session) -> models.BookClubDatePoll | None:
    return db.scalar(
        select(models.BookClubDatePoll).where(
            models.BookClubDatePoll.club_id == _club_id(db),
            models.BookClubDatePoll.status == "open",
        )
    )


def open_date_poll(db: Session, option_dates: list) -> models.BookClubDatePoll:
    if get_open_date_poll(db) is not None:
        raise ValueError("A date poll is already open")
    poll = models.BookClubDatePoll(club_id=_club_id(db), status="open")
    db.add(poll)
    db.flush()
    for option_date in option_dates:
        db.add(models.BookClubDatePollOption(poll_id=poll.id, option_date=option_date))
    return _commit(db, poll)


def add_date_option(db: Session, poll_id: int, option_date) -> models.BookClubDatePollOption:
    option = models.BookClubDatePollOption(poll_id=poll_id, option_date=option_date)
    db.add(option)
    return _commit(db, option)


def list_date_options(db: Session, poll_id: int) -> list[models.BookClubDatePollOption]:
    return list(
        db.scalars(
            select(models.BookClubDatePollOption)
            .where(models.BookClubDatePollOption.poll_id == poll_id)
            .order_by(models.BookClubDatePollOption.option_date)
        )
    )


def get_date_option(db: Session, option_id: int) -> models.BookClubDatePollOption | None:
    return db.scalar(
        select(models.BookClubDatePollOption)
        .join(models.BookClubDatePoll)
        .where(
            models.BookClubDatePollOption.id == option_id,
            models.BookClubDatePoll.club_id == _club_id(db),
        )
    )


def date_poll_vote_counts(db: Session, poll_id: int) -> dict[int, int]:
    rows = db.execute(
        select(models.BookClubDatePollVote.option_id, func.count())
        .where(models.BookClubDatePollVote.poll_id == poll_id)
        .group_by(models.BookClubDatePollVote.option_id)
    ).all()
    return dict(rows)


def get_own_date_vote(db: Session, poll_id: int, participant_id: int) -> models.BookClubDatePollVote | None:
    return db.scalar(
        select(models.BookClubDatePollVote).where(
            models.BookClubDatePollVote.poll_id == poll_id,
            models.BookClubDatePollVote.participant_id == participant_id,
        )
    )


def cast_date_vote(
    db: Session, poll_id: int, option_id: int, participant_id: int
) -> models.BookClubDatePollVote:
    vote = get_own_date_vote(db, poll_id, participant_id)
    if vote is None:
        vote = models.BookClubDatePollVote(
            poll_id=poll_id, participant_id=participant_id, option_id=option_id
        )
        db.add(vote)
    else:
        vote.option_id = option_id
    return _commit(db, vote)


def remove_date_vote(db: Session, poll_id: int, participant_id: int) -> bool:
    vote = get_own_date_vote(db, poll_id, participant_id)
    if vote is None:
        return False
    db.delete(vote)
    db.commit()
    return True


def close_date_poll(db: Session, poll_id: int) -> models.BookClubDatePoll:
    poll = db.get(models.BookClubDatePoll, poll_id)
    if poll is None or poll.club_id != _club_id(db):
        raise LookupError("Date poll not found")
    if poll.status != "open":
        raise ValueError("This date poll is already closed")
    counts = date_poll_vote_counts(db, poll_id)
    options = list_date_options(db, poll_id)
    # Ties go to whichever date option was added first (lowest id).
    winner = max(options, key=lambda o: (counts.get(o.id, 0), -o.id), default=None) if options else None
    poll.status = "closed"
    poll.closed_at = datetime.now(timezone.utc)
    poll.winning_date = winner.option_date if winner else None
    return _commit(db, poll)


def list_broadcastable_participants(
    db: Session,
) -> list[tuple[models.BookClubMember, ParticipantAccount]]:
    return list(
        db.execute(
            select(models.BookClubMember, ParticipantAccount)
            .join(
                ParticipantAccount,
                ParticipantAccount.id == models.BookClubMember.participant_account_id,
            )
            .where(
                models.BookClubMember.club_id == _club_id(db),
                models.BookClubMember.active.is_(True),
                models.BookClubMember.participant_unsubscribed_at.is_(None),
                ParticipantAccount.active.is_(True),
            )
        ).all()
    )


def mark_participant_unsubscribed(db: Session, member: models.BookClubMember) -> None:
    if member.participant_unsubscribed_at is None:
        member.participant_unsubscribed_at = datetime.now(timezone.utc)
        db.commit()
