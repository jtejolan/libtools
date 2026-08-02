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


def create_member(
    db: Session, value: schemas.MemberCreate
) -> models.BookClubMember:
    member = models.BookClubMember(**value.model_dump())
    db.add(member)
    return _commit(db, member)


def get_member(db: Session, member_id: int) -> models.BookClubMember | None:
    return db.get(models.BookClubMember, member_id)


def list_members(
    db: Session,
    *,
    active: bool | None = None,
    search: str | None = None,
    offset: int = 0,
    limit: int = 100,
) -> list[models.BookClubMember]:
    statement = select(models.BookClubMember)
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


def create_meeting(
    db: Session, value: schemas.MeetingCreate
) -> models.BookClubMeeting:
    data = value.model_dump(exclude={"add_active_members"})
    meeting = models.BookClubMeeting(**data)
    if value.add_active_members:
        members = db.scalars(
            select(models.BookClubMember)
            .where(models.BookClubMember.active.is_(True))
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
    return db.get(models.BookClubMeeting, meeting_id)


def list_meetings(
    db: Session,
    *,
    from_date: date | None = None,
    offset: int = 0,
    limit: int = 100,
) -> list[models.BookClubMeeting]:
    statement = select(models.BookClubMeeting)
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
    for field, value in _data(changes, exclude_unset=True).items():
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
        .options(selectinload(models.BookClubParticipation.meeting))
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
    existing = set(db.scalars(select(models.BookClubTemplate.key)))
    additions = [
        models.BookClubTemplate(**value)
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
            )
        )
    )


def get_template(
    db: Session, key: str
) -> models.BookClubTemplate | None:
    ensure_default_templates(db)
    return db.scalar(
        select(models.BookClubTemplate).where(
            models.BookClubTemplate.key == key
        )
    )


def create_template(
    db: Session, value: schemas.TemplateCreate
) -> models.BookClubTemplate:
    template = models.BookClubTemplate(**value.model_dump())
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
        template = models.BookClubTemplate(**default)
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
    organizer_name: str = "Josh",
    organizer_branch: str = "PBRL",
) -> dict[str, Any]:
    member = participation.member
    return {
        "first_name": member.name.split()[0],
        "member_name": member.name,
        "email": member.email,
        "book_title": meeting.book_title,
        "book_author": meeting.book_author,
        "meeting_date": meeting.meeting_date.isoformat(),
        "meeting_time": meeting.meeting_time,
        "meeting_location": meeting.location,
        "destination_branch": participation.destination_branch,
        "organizer_name": organizer_name,
        "organizer_branch": organizer_branch,
    }


QUESTION_POOLS = {
    "balanced": [
        "What was your overall reaction to {title}?",
        "Which moment or idea from {title} stayed with you most?",
        "Which character changed the most, and what drove that change?",
        "Which relationship was most important to the story?",
        "What central themes did you see in the book?",
        "Did the ending change how you understood the rest of the story?",
        "What do you think {author} wanted readers to question?",
        "How did the setting shape the choices available to the characters?",
        "Was there a decision you would have made differently?",
        "Who would you recommend this book to, and why?",
    ],
    "themes": [
        "What is the strongest theme in {title}, and where does it emerge?",
        "Did the book complicate or confirm your views on its main ideas?",
        "Which competing values create the story's central tension?",
        "How does the ending reinforce or challenge the book's themes?",
        "What real-world questions does {title} invite us to consider?",
    ],
    "characters": [
        "Which character in {title} did you understand best, and why?",
        "Whose motivation was hardest to accept or understand?",
        "How did the characters change one another?",
        "Which character made the most consequential choice?",
        "Did your opinion of any character change while reading?",
    ],
    "science_fiction": [
        "What speculative idea in {title} felt most plausible?",
        "How does the imagined technology or society affect everyday life?",
        "What present-day concern is the speculative setting examining?",
        "Which rule of the book's world mattered most to the story?",
        "Did the science-fiction elements deepen the human story?",
    ],
    "style": [
        "How would you describe {author}'s writing style in {title}?",
        "How did the point of view shape what you knew or believed?",
        "What effect did the book's pacing have on your experience?",
        "Was there an image, motif, or structural choice that stood out?",
        "How well did the style suit the story being told?",
    ],
}


def build_question_texts(
    meeting: models.BookClubMeeting, request: schemas.GenerateQuestionsRequest
) -> list[str]:
    selected = list(QUESTION_POOLS[request.focus])
    if request.focus != "balanced":
        selected.extend(QUESTION_POOLS["balanced"])
    if request.spoiler_free:
        selected = [
            question
            for question in selected
            if "ending" not in question.lower()
        ]
        selected.insert(
            1,
            "Without sharing spoilers, what early element of {title} drew you in?",
        )
    if request.tone == "in_depth":
        selected.insert(
            1,
            "What assumptions does {title} ask the reader to examine?",
        )
    fallback = [
        "What question would you most like to ask {author} about {title}?",
        "What part of {title} produced the most disagreement for you?",
        "What would you want to discuss that the group has not raised yet?",
    ]
    selected.extend(fallback)
    while len(selected) < request.count:
        selected.extend(QUESTION_POOLS["balanced"])
    return [
        question.format(
            title=meeting.book_title, author=meeting.book_author
        )
        for question in selected[: request.count]
    ]


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


def generate_questions(
    db: Session,
    meeting: models.BookClubMeeting,
    request: schemas.GenerateQuestionsRequest,
) -> list[models.BookClubDiscussionQuestion]:
    if request.replace_existing:
        for question in list_questions(db, meeting.id):
            db.delete(question)
        db.flush()
        start = 1
    else:
        highest = db.scalar(
            select(func.max(models.BookClubDiscussionQuestion.position)).where(
                models.BookClubDiscussionQuestion.meeting_id == meeting.id
            )
        )
        start = int(highest or 0) + 1
    questions = [
        models.BookClubDiscussionQuestion(
            meeting=meeting, position=start + index, text=text
        )
        for index, text in enumerate(build_question_texts(meeting, request))
    ]
    db.add_all(questions)
    db.commit()
    for question in questions:
        db.refresh(question)
    return questions


def update_question(
    db: Session, question_id: int, changes: schemas.DiscussionQuestionUpdate
) -> models.BookClubDiscussionQuestion | None:
    question = db.get(models.BookClubDiscussionQuestion, question_id)
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
    question = db.get(models.BookClubDiscussionQuestion, question_id)
    if question is None:
        return False
    try:
        db.delete(question)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    return True
