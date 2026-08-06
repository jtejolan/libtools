"""Free-text meeting-time parsing, shared by the ORM model (for the
`starts_at`/`ends_at` computed properties `MeetingResponse` reads via
`from_attributes`) and crud.py's calendar-link building. Lives outside both
so neither has to import the other just for this.
"""

from datetime import date, datetime, time, timedelta

_MEETING_TIME_FORMATS = ("%I:%M %p", "%I:%M%p", "%H:%M", "%I %p", "%I%p")


def parse_meeting_time(meeting_time: str | None) -> time | None:
    if not meeting_time:
        return None
    cleaned = meeting_time.strip().upper().replace(".", "")
    for fmt in _MEETING_TIME_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).time()
        except ValueError:
            continue
    return None


def meeting_datetime_range(
    meeting_date: date,
    meeting_time: str | None,
    duration_minutes: int,
) -> tuple[datetime, datetime] | None:
    """(start, end) for a meeting, or None when meeting_time doesn't parse."""
    parsed_time = parse_meeting_time(meeting_time)
    if parsed_time is None:
        return None
    start = datetime.combine(meeting_date, parsed_time)
    return start, start + timedelta(minutes=duration_minutes)
