from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from bookclub import crud, models, participant_auth
from bookclub.participant_schemas import (
    AnnouncementResponse,
    DiscussionPostCreate,
    DiscussionPostResponse,
    NotificationPreferencesResponse,
    NotificationPreferencesUpdate,
    PersonalActivityItem,
    PersonalActivityResponse,
    ParticipantMeetingResponse,
    ParticipantLibraryResponse,
    ParticipantProfileResponse,
    ParticipantProfileUpdate,
    ReadingProgressResponse,
    ReadingProgressUpdate,
    RsvpUpdate,
)
from dependencies import DatabaseSession


router = APIRouter(prefix="/participant", tags=["bookclub-participant-community"])


def _meeting_response(meeting, club, member, db) -> ParticipantMeetingResponse:
    participation = db.scalar(
        select(models.BookClubParticipation).where(
            models.BookClubParticipation.meeting_id == meeting.id,
            models.BookClubParticipation.member_id == member.id,
        )
    )
    return ParticipantMeetingResponse(
        meeting=meeting,
        rsvp_status=participation.rsvp_status if participation else None,
        google_calendar_url=crud.build_calendar_link(meeting, club.video_call_url),
        ics_calendar_url=f"/participant/meetings/{meeting.id}/calendar.ics",
        video_call_url=club.video_call_url,
        discussion_questions=[question.text for question in meeting.discussion_questions],
    )


@router.get("/announcements", response_model=list[AnnouncementResponse])
def list_announcements(
    club: participant_auth.CurrentParticipantClub,
    member: participant_auth.CurrentParticipantMember,
    db: DatabaseSession,
):
    rows = db.execute(
        select(models.BookClubAnnouncement, models.BookClubAnnouncementRead.id)
        .outerjoin(
            models.BookClubAnnouncementRead,
            (models.BookClubAnnouncementRead.announcement_id == models.BookClubAnnouncement.id)
            & (models.BookClubAnnouncementRead.member_id == member.id),
        )
        .where(models.BookClubAnnouncement.club_id == club.id)
        .order_by(
            models.BookClubAnnouncement.pinned.desc(),
            models.BookClubAnnouncement.published_at.desc(),
            models.BookClubAnnouncement.id.desc(),
        )
    ).all()
    return [
        AnnouncementResponse.model_validate(announcement).model_copy(
            update={"read": read_id is not None}
        )
        for announcement, read_id in rows
    ]


@router.put("/announcements/{announcement_id}/read", response_model=AnnouncementResponse)
def mark_announcement_read(
    announcement_id: int,
    club: participant_auth.CurrentParticipantClub,
    member: participant_auth.CurrentParticipantMember,
    db: DatabaseSession,
):
    announcement = db.scalar(
        select(models.BookClubAnnouncement).where(
            models.BookClubAnnouncement.id == announcement_id,
            models.BookClubAnnouncement.club_id == club.id,
        )
    )
    if announcement is None:
        raise HTTPException(status_code=404, detail="Announcement not found")
    existing = db.scalar(
        select(models.BookClubAnnouncementRead).where(
            models.BookClubAnnouncementRead.announcement_id == announcement_id,
            models.BookClubAnnouncementRead.member_id == member.id,
        )
    )
    if existing is None:
        db.add(
            models.BookClubAnnouncementRead(
                announcement_id=announcement_id, member_id=member.id
            )
        )
        db.commit()
    return AnnouncementResponse.model_validate(announcement).model_copy(
        update={"read": True}
    )


@router.get("/meetings/upcoming", response_model=ParticipantMeetingResponse | None)
def upcoming_meeting(
    club: participant_auth.CurrentParticipantClub,
    member: participant_auth.CurrentParticipantMember,
    db: DatabaseSession,
):
    meeting = db.scalar(
        select(models.BookClubMeeting)
        .options(
            selectinload(models.BookClubMeeting.book),
            selectinload(models.BookClubMeeting.discussion_questions),
        )
        .where(
            models.BookClubMeeting.club_id == club.id,
            models.BookClubMeeting.status == "planned",
            models.BookClubMeeting.meeting_date >= date.today(),
        )
        .order_by(models.BookClubMeeting.meeting_date, models.BookClubMeeting.id)
    )
    if meeting is None:
        return None
    return _meeting_response(meeting, club, member, db)


@router.get("/meetings/latest-completed", response_model=ParticipantMeetingResponse | None)
def latest_completed_meeting(
    club: participant_auth.CurrentParticipantClub,
    member: participant_auth.CurrentParticipantMember,
    db: DatabaseSession,
):
    meeting = db.scalar(
        select(models.BookClubMeeting)
        .options(
            selectinload(models.BookClubMeeting.book),
            selectinload(models.BookClubMeeting.discussion_questions),
        )
        .where(
            models.BookClubMeeting.club_id == club.id,
            models.BookClubMeeting.status == "completed",
        )
        .order_by(models.BookClubMeeting.meeting_date.desc(), models.BookClubMeeting.id.desc())
    )
    return _meeting_response(meeting, club, member, db) if meeting else None


@router.put("/meetings/{meeting_id}/rsvp", response_model=ParticipantMeetingResponse)
def save_rsvp(
    meeting_id: int,
    value: RsvpUpdate,
    club: participant_auth.CurrentParticipantClub,
    member: participant_auth.CurrentParticipantMember,
    db: DatabaseSession,
):
    meeting = db.scalar(
        select(models.BookClubMeeting)
        .options(
            selectinload(models.BookClubMeeting.book),
            selectinload(models.BookClubMeeting.discussion_questions),
        )
        .where(
            models.BookClubMeeting.id == meeting_id,
            models.BookClubMeeting.club_id == club.id,
        )
    )
    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting not found")
    if meeting.status != "planned" or meeting.meeting_date < date.today():
        raise HTTPException(status_code=409, detail="RSVPs are closed for this meeting")
    participation = db.scalar(
        select(models.BookClubParticipation).where(
            models.BookClubParticipation.meeting_id == meeting.id,
            models.BookClubParticipation.member_id == member.id,
        )
    )
    if participation is None:
        participation = models.BookClubParticipation(meeting=meeting, member=member)
        db.add(participation)
    participation.rsvp_status = value.status
    db.commit()
    return _meeting_response(meeting, club, member, db)


def _ics_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace(",", "\\,").replace(";", "\\;")


@router.get("/meetings/{meeting_id}/calendar.ics")
def download_calendar_event(
    meeting_id: int,
    club: participant_auth.CurrentParticipantClub,
    db: DatabaseSession,
) -> Response:
    meeting = db.scalar(
        select(models.BookClubMeeting)
        .options(selectinload(models.BookClubMeeting.book))
        .where(
            models.BookClubMeeting.id == meeting_id,
            models.BookClubMeeting.club_id == club.id,
        )
    )
    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting not found")
    time_range = (meeting.starts_at, meeting.ends_at)
    if all(time_range):
        date_lines = [
            f"DTSTART:{time_range[0].strftime('%Y%m%dT%H%M%S')}",
            f"DTEND:{time_range[1].strftime('%Y%m%dT%H%M%S')}",
        ]
    else:
        date_lines = [
            f"DTSTART;VALUE=DATE:{meeting.meeting_date.strftime('%Y%m%d')}",
            f"DTEND;VALUE=DATE:{(meeting.meeting_date + timedelta(days=1)).strftime('%Y%m%d')}",
        ]
    description = meeting.notes or ""
    if club.video_call_url:
        description = f"{description}\n\nJoin online: {club.video_call_url}".strip()
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Libtools//Book Club//EN",
        "CALSCALE:GREGORIAN",
        "BEGIN:VEVENT",
        f"UID:bookclub-{club.id}-{meeting.id}@libtools.app",
        f"DTSTAMP:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        *date_lines,
        f"SUMMARY:{_ics_escape(f'Book club: {meeting.book.title}')}",
        f"LOCATION:{_ics_escape(meeting.location or '')}",
        f"DESCRIPTION:{_ics_escape(description)}",
        "END:VEVENT",
        "END:VCALENDAR",
        "",
    ]
    return Response(
        content="\r\n".join(lines),
        media_type="text/calendar",
        headers={"Content-Disposition": f'attachment; filename="book-club-{meeting.id}.ics"'},
    )


@router.get("/books/{book_id}/reading-progress", response_model=ReadingProgressResponse)
def get_reading_progress(
    book_id: int,
    club: participant_auth.CurrentParticipantClub,
    member: participant_auth.CurrentParticipantMember,
    db: DatabaseSession,
):
    book = db.scalar(
        select(models.BookClubBook).where(
            models.BookClubBook.id == book_id, models.BookClubBook.club_id == club.id
        )
    )
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")
    progress = db.scalar(
        select(models.BookClubReadingProgress).where(
            models.BookClubReadingProgress.member_id == member.id,
            models.BookClubReadingProgress.book_id == book_id,
        )
    )
    return ReadingProgressResponse(
        book_id=book_id,
        status=progress.status if progress else None,
        updated_at=progress.updated_at if progress else None,
    )


@router.put("/books/{book_id}/reading-progress", response_model=ReadingProgressResponse)
def save_reading_progress(
    book_id: int,
    value: ReadingProgressUpdate,
    club: participant_auth.CurrentParticipantClub,
    member: participant_auth.CurrentParticipantMember,
    db: DatabaseSession,
):
    book = db.scalar(
        select(models.BookClubBook).where(
            models.BookClubBook.id == book_id, models.BookClubBook.club_id == club.id
        )
    )
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")
    progress = db.scalar(
        select(models.BookClubReadingProgress).where(
            models.BookClubReadingProgress.member_id == member.id,
            models.BookClubReadingProgress.book_id == book_id,
        )
    )
    if value.status is None:
        if progress is not None:
            db.delete(progress)
            db.commit()
        return ReadingProgressResponse(book_id=book_id)
    if progress is None:
        progress = models.BookClubReadingProgress(
            club_id=club.id, member_id=member.id, book_id=book_id, status=value.status
        )
        db.add(progress)
    else:
        progress.status = value.status
    db.commit()
    db.refresh(progress)
    return ReadingProgressResponse(
        book_id=book_id, status=progress.status, updated_at=progress.updated_at
    )


@router.get("/notification-preferences", response_model=NotificationPreferencesResponse)
def get_notification_preferences(
    member: participant_auth.CurrentParticipantMember,
    db: DatabaseSession,
):
    preference = db.scalar(
        select(models.BookClubNotificationPreference).where(
            models.BookClubNotificationPreference.member_id == member.id
        )
    )
    if preference is None:
        return NotificationPreferencesResponse(
            announcements=True,
            polls=True,
            meeting_reminders=True,
            discussion_replies=True,
            delivery_frequency="immediate",
        )
    return preference


def _profile_response(member, *, is_self: bool = False) -> ParticipantProfileResponse:
    return ParticipantProfileResponse(
        member_id=member.id,
        name=member.name,
        bio=member.bio,
        avatar_url=member.avatar_url,
        directory_visible=member.directory_visible,
        is_self=is_self,
    )


@router.get("/profile", response_model=ParticipantProfileResponse)
def get_profile(member: participant_auth.CurrentParticipantMember):
    return _profile_response(member, is_self=True)


@router.put("/profile", response_model=ParticipantProfileResponse)
def save_profile(
    value: ParticipantProfileUpdate,
    member: participant_auth.CurrentParticipantMember,
    db: DatabaseSession,
):
    for field, field_value in value.model_dump().items():
        setattr(member, field, field_value)
    db.commit()
    db.refresh(member)
    return _profile_response(member, is_self=True)


@router.get("/members", response_model=list[ParticipantProfileResponse])
def member_directory(
    club: participant_auth.CurrentParticipantClub,
    member: participant_auth.CurrentParticipantMember,
    db: DatabaseSession,
):
    members = list(
        db.scalars(
            select(models.BookClubMember)
            .where(
                models.BookClubMember.club_id == club.id,
                models.BookClubMember.active.is_(True),
                (
                    (models.BookClubMember.directory_visible.is_(True))
                    | (models.BookClubMember.id == member.id)
                ),
            )
            .order_by(models.BookClubMember.name, models.BookClubMember.id)
        )
    )
    return [_profile_response(item, is_self=item.id == member.id) for item in members]


@router.get("/books/library", response_model=ParticipantLibraryResponse)
def participant_library(
    club: participant_auth.CurrentParticipantClub,
    db: DatabaseSession,
):
    books = list(
        db.scalars(
            select(models.BookClubBook)
            .where(models.BookClubBook.club_id == club.id)
            .order_by(models.BookClubBook.title, models.BookClubBook.id)
        )
    )
    meetings = list(
        db.scalars(
            select(models.BookClubMeeting)
            .where(models.BookClubMeeting.club_id == club.id)
            .order_by(models.BookClubMeeting.meeting_date, models.BookClubMeeting.id)
        )
    )
    upcoming_ids = []
    completed_ids = set()
    for meeting in meetings:
        if meeting.status == "completed":
            completed_ids.add(meeting.book_id)
        elif meeting.status == "planned" and meeting.meeting_date >= date.today():
            upcoming_ids.append(meeting.book_id)
    current_ids = set(upcoming_ids[:1])
    up_next_ids = set(upcoming_ids[1:])
    winning_ids = set(
        db.scalars(
            select(models.BookClubVotingRound.winning_book_id).where(
                models.BookClubVotingRound.club_id == club.id,
                models.BookClubVotingRound.status == "closed",
                models.BookClubVotingRound.winning_book_id.is_not(None),
            )
        )
    )
    up_next_ids.update(winning_ids - current_ids - completed_ids)
    previous_ids = completed_ids | {book.id for book in books if book.is_past_selection}
    return ParticipantLibraryResponse(
        current=[book for book in books if book.id in current_ids],
        up_next=[book for book in books if book.id in up_next_ids],
        previously_read=[book for book in books if book.id in previous_ids],
    )


def _discussion_response(post, current_member_id: int) -> DiscussionPostResponse:
    return DiscussionPostResponse(
        id=post.id,
        book_id=post.book_id,
        parent_id=post.parent_id,
        body=post.body,
        author=_profile_response(post.member, is_self=post.member_id == current_member_id),
        created_at=post.created_at,
        updated_at=post.updated_at,
    )


def _participant_book(db, club_id: int, book_id: int):
    book = db.scalar(
        select(models.BookClubBook).where(
            models.BookClubBook.id == book_id,
            models.BookClubBook.club_id == club_id,
        )
    )
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")
    return book


@router.get("/books/{book_id}/discussion", response_model=list[DiscussionPostResponse])
def list_discussion_posts(
    book_id: int,
    club: participant_auth.CurrentParticipantClub,
    member: participant_auth.CurrentParticipantMember,
    db: DatabaseSession,
):
    _participant_book(db, club.id, book_id)
    posts = list(
        db.scalars(
            select(models.BookClubDiscussionPost)
            .options(selectinload(models.BookClubDiscussionPost.member))
            .where(
                models.BookClubDiscussionPost.club_id == club.id,
                models.BookClubDiscussionPost.book_id == book_id,
            )
            .order_by(models.BookClubDiscussionPost.created_at, models.BookClubDiscussionPost.id)
        )
    )
    return [_discussion_response(post, member.id) for post in posts]


@router.post(
    "/books/{book_id}/discussion",
    response_model=DiscussionPostResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_discussion_post(
    book_id: int,
    value: DiscussionPostCreate,
    club: participant_auth.CurrentParticipantClub,
    member: participant_auth.CurrentParticipantMember,
    db: DatabaseSession,
):
    _participant_book(db, club.id, book_id)
    if value.parent_id is not None:
        parent = db.scalar(
            select(models.BookClubDiscussionPost).where(
                models.BookClubDiscussionPost.id == value.parent_id,
                models.BookClubDiscussionPost.club_id == club.id,
                models.BookClubDiscussionPost.book_id == book_id,
                models.BookClubDiscussionPost.parent_id.is_(None),
            )
        )
        if parent is None:
            raise HTTPException(status_code=404, detail="Discussion post not found")
    post = models.BookClubDiscussionPost(
        club_id=club.id,
        book_id=book_id,
        member_id=member.id,
        parent_id=value.parent_id,
        body=value.body,
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    post.member = member
    return _discussion_response(post, member.id)


@router.delete("/discussion/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_discussion_post(
    post_id: int,
    club: participant_auth.CurrentParticipantClub,
    member: participant_auth.CurrentParticipantMember,
    db: DatabaseSession,
) -> Response:
    post = db.scalar(
        select(models.BookClubDiscussionPost).where(
            models.BookClubDiscussionPost.id == post_id,
            models.BookClubDiscussionPost.club_id == club.id,
            models.BookClubDiscussionPost.member_id == member.id,
        )
    )
    if post is None:
        raise HTTPException(status_code=404, detail="Discussion post not found")
    db.delete(post)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/notification-preferences", response_model=NotificationPreferencesResponse)
def save_notification_preferences(
    value: NotificationPreferencesUpdate,
    member: participant_auth.CurrentParticipantMember,
    db: DatabaseSession,
):
    preference = db.scalar(
        select(models.BookClubNotificationPreference).where(
            models.BookClubNotificationPreference.member_id == member.id
        )
    )
    if preference is None:
        preference = models.BookClubNotificationPreference(member_id=member.id)
        db.add(preference)
    for field, field_value in value.model_dump().items():
        setattr(preference, field, field_value)
    db.commit()
    db.refresh(preference)
    return preference


@router.get("/activity", response_model=PersonalActivityResponse)
def personal_activity(
    club: participant_auth.CurrentParticipantClub,
    participant: participant_auth.CurrentParticipant,
    member: participant_auth.CurrentParticipantMember,
    db: DatabaseSession,
):
    ratings = list(db.execute(
        select(models.BookClubRating, models.BookClubBook.title)
        .join(models.BookClubBook, models.BookClubBook.id == models.BookClubRating.book_id)
        .where(
            models.BookClubRating.club_id == club.id,
            models.BookClubRating.participant_id == participant.id,
        )
    ).all())
    book_votes = list(db.execute(
        select(models.BookClubVote, models.BookClubBook.title)
        .join(models.BookClubBookCandidate, models.BookClubBookCandidate.id == models.BookClubVote.candidate_id)
        .join(models.BookClubBook, models.BookClubBook.id == models.BookClubBookCandidate.book_id)
        .join(models.BookClubVotingRound, models.BookClubVotingRound.id == models.BookClubVote.voting_round_id)
        .where(
            models.BookClubVotingRound.club_id == club.id,
            models.BookClubVote.participant_id == participant.id,
        )
    ).all())
    date_votes = list(db.execute(
        select(models.BookClubDatePollVote, models.BookClubDatePollOption.option_date)
        .join(models.BookClubDatePollOption, models.BookClubDatePollOption.id == models.BookClubDatePollVote.option_id)
        .join(models.BookClubDatePoll, models.BookClubDatePoll.id == models.BookClubDatePollVote.poll_id)
        .where(
            models.BookClubDatePoll.club_id == club.id,
            models.BookClubDatePollVote.participant_id == participant.id,
        )
    ).all())
    proposals = list(db.execute(
        select(models.BookClubBookCandidate, models.BookClubBook.title)
        .join(models.BookClubBook, models.BookClubBook.id == models.BookClubBookCandidate.book_id)
        .join(models.BookClubVotingRound, models.BookClubVotingRound.id == models.BookClubBookCandidate.voting_round_id)
        .where(
            models.BookClubVotingRound.club_id == club.id,
            models.BookClubBookCandidate.proposed_by_participant_id == participant.id,
        )
    ).all())
    progress_rows = list(db.execute(
        select(models.BookClubReadingProgress, models.BookClubBook.title)
        .join(models.BookClubBook, models.BookClubBook.id == models.BookClubReadingProgress.book_id)
        .where(models.BookClubReadingProgress.member_id == member.id)
    ).all())
    attended_count = db.scalar(
        select(func.count(models.BookClubParticipation.id)).where(
            models.BookClubParticipation.member_id == member.id,
            models.BookClubParticipation.attended.is_(True),
        )
    ) or 0
    recent = []
    recent.extend(PersonalActivityItem(kind="rating", label=f"Rated {title}", detail=f"{rating.rating} stars", occurred_at=rating.updated_at) for rating, title in ratings)
    recent.extend(PersonalActivityItem(kind="book_vote", label=f"Voted for {title}", occurred_at=vote.created_at) for vote, title in book_votes)
    recent.extend(PersonalActivityItem(kind="date_vote", label="Voted on a meeting date", detail=option_date.isoformat(), occurred_at=vote.created_at) for vote, option_date in date_votes)
    recent.extend(PersonalActivityItem(kind="proposal", label=f"Proposed {title}", detail=candidate.status, occurred_at=candidate.created_at) for candidate, title in proposals)
    recent.extend(PersonalActivityItem(kind="progress", label=f"Updated {title}", detail=progress.status.replace("_", " "), occurred_at=progress.updated_at) for progress, title in progress_rows)
    recent.sort(key=lambda item: item.occurred_at, reverse=True)
    return PersonalActivityResponse(
        ratings_count=len(ratings),
        book_votes_count=len(book_votes),
        date_votes_count=len(date_votes),
        proposals_count=len(proposals),
        attended_meetings_count=int(attended_count),
        recent=recent[:8],
    )
