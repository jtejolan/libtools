from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from bookclub import crud, models, participant_auth
from bookclub.participant_schemas import (
    AnnouncementResponse,
    NotificationPreferencesResponse,
    NotificationPreferencesUpdate,
    PersonalActivityItem,
    PersonalActivityResponse,
    ParticipantMeetingResponse,
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
    )


@router.get("/announcements", response_model=list[AnnouncementResponse])
def list_announcements(
    club: participant_auth.CurrentParticipantClub,
    db: DatabaseSession,
):
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


@router.get("/meetings/upcoming", response_model=ParticipantMeetingResponse | None)
def upcoming_meeting(
    club: participant_auth.CurrentParticipantClub,
    member: participant_auth.CurrentParticipantMember,
    db: DatabaseSession,
):
    meeting = db.scalar(
        select(models.BookClubMeeting)
        .options(selectinload(models.BookClubMeeting.book))
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
        .options(selectinload(models.BookClubMeeting.book))
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
            announcements=True, polls=True, meeting_reminders=True, discussion_replies=True
        )
    return preference


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
