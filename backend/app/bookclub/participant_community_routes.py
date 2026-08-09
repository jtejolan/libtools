from datetime import date

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from bookclub import models, participant_auth
from bookclub.participant_schemas import (
    AnnouncementResponse,
    ParticipantMeetingResponse,
    RsvpUpdate,
)
from dependencies import DatabaseSession


router = APIRouter(prefix="/participant", tags=["bookclub-participant-community"])


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
    participation = db.scalar(
        select(models.BookClubParticipation).where(
            models.BookClubParticipation.meeting_id == meeting.id,
            models.BookClubParticipation.member_id == member.id,
        )
    )
    return ParticipantMeetingResponse(
        meeting=meeting,
        rsvp_status=participation.rsvp_status if participation else None,
    )


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
    return ParticipantMeetingResponse(meeting=meeting, rsvp_status=participation.rsvp_status)
