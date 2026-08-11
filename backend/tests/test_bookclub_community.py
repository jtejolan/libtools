import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from accounts import login_throttle
from bookclub.models import BookClubMember, BookClubParticipation
from bookclub.participant_models import ParticipantAccount
from database import Base
from dependencies import get_db
from main import app, bookclub_public_app


class BookClubCommunityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(cls.engine)
        cls.sessions = sessionmaker(bind=cls.engine, autoflush=False, expire_on_commit=False)

        def override_get_db():
            db: Session = cls.sessions()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        bookclub_public_app.dependency_overrides[get_db] = override_get_db

    @classmethod
    def tearDownClass(cls) -> None:
        app.dependency_overrides.clear()
        bookclub_public_app.dependency_overrides.clear()
        Base.metadata.drop_all(cls.engine)
        cls.engine.dispose()

    def setUp(self) -> None:
        login_throttle.reset()
        with self.engine.begin() as connection:
            for table in reversed(Base.metadata.sorted_tables):
                connection.execute(table.delete())
        self.facilitator = TestClient(app)
        registered = self.facilitator.post("/auth/register", json={
            "name": "Alex Facilitator", "username": "alex", "email": "alex@example.com",
            "password": "facilitator-pw-1", "confirm_password": "facilitator-pw-1",
        })
        self.assertEqual(registered.status_code, 201, registered.text)
        club = self.facilitator.post("/bookclub/clubs", json={"name": "Mystery Lovers Club"})
        self.assertEqual(club.status_code, 201, club.text)
        self.facilitator.post(f"/bookclub/clubs/{club.json()['id']}/select")

        self.reader = TestClient(app, base_url="http://bookclub.libtools.app")
        reader = self.reader.post("/participant/auth/register", json={
            "club_slug": "mystery-lovers-club", "name": "Reader One",
            "email": "reader@example.com", "password": "reader-password-1",
            "confirm_password": "reader-password-1",
        })
        self.assertEqual(reader.status_code, 201, reader.text)
        self.reader_member_id = reader.json()["member_id"]

    def tearDown(self) -> None:
        self.facilitator.close()
        self.reader.close()
        login_throttle.reset()

    def create_meeting(self) -> dict:
        book = self.facilitator.post(
            "/bookclub/community/books", json={"title": "Dune", "author": "Frank Herbert"}
        )
        self.assertEqual(book.status_code, 201, book.text)
        meeting = self.facilitator.post("/bookclub/community/meetings", json={
            "book_id": book.json()["id"],
            "meeting_date": str(date.today() + timedelta(days=14)),
            "meeting_time": "7:00 PM", "location": "Main Branch",
        })
        self.assertEqual(meeting.status_code, 201, meeting.text)
        return meeting.json()

    def test_overview_reports_activation_and_rsvp_statuses(self) -> None:
        unlinked = self.facilitator.post("/bookclub/members", json={
            "name": "Roster Only", "email": "roster@example.com", "joined_on": str(date.today())
        })
        self.assertEqual(unlinked.status_code, 201, unlinked.text)
        meeting = self.create_meeting()
        self.reader.put(
            f"/participant/meetings/{meeting['id']}/rsvp", json={"status": "attending"}
        )

        overview = self.facilitator.get("/bookclub/community/overview")
        self.assertEqual(overview.status_code, 200, overview.text)
        body = overview.json()
        self.assertEqual(body["member_count"], 2)
        self.assertEqual(body["linked_account_count"], 1)
        self.assertEqual(body["pending_verification_count"], 1)
        self.assertEqual(body["unlinked_member_count"], 1)
        self.assertEqual(body["rsvp_counts"]["attending"], 1)
        self.assertEqual(body["rsvp_counts"]["no_response"], 1)
        reader_status = next(item for item in body["accounts"] if item["member_id"] == self.reader_member_id)
        self.assertEqual(reader_status["rsvp_status"], "attending")

        access = self.facilitator.get("/bookclub/members/community-access")
        self.assertEqual(access.status_code, 200, access.text)
        access_by_member = {item["member_id"]: item for item in access.json()}
        self.assertEqual(
            access_by_member[self.reader_member_id]["status"],
            "verification_pending",
        )
        self.assertEqual(
            access_by_member[unlinked.json()["id"]]["status"],
            "invitation_not_accepted",
        )

        with self.sessions() as db:
            account = db.scalar(select(ParticipantAccount))
            account.email_verified_at = datetime.now(timezone.utc)
            db.commit()
        activated = self.facilitator.get("/bookclub/community/overview").json()
        self.assertEqual(activated["verified_account_count"], 1)
        self.assertEqual(activated["pending_verification_count"], 0)

    @patch("bookclub.routes.participant_email_delivery.send_verification_email", return_value=True)
    def test_facilitator_can_resend_participant_verification(self, send_verification) -> None:
        response = self.facilitator.post(
            f"/bookclub/members/{self.reader_member_id}/verification"
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["message"], "Verification email sent.")
        verification_url = send_verification.call_args.kwargs["verification_url"]
        self.assertTrue(
            verification_url.startswith("https://bookclub.libtools.app/verify-email?token=")
        )

        with self.sessions() as db:
            account = db.scalar(select(ParticipantAccount))
            account.active = False
            member = db.get(BookClubMember, self.reader_member_id)
            member.participant_unsubscribed_at = datetime.now(timezone.utc)
            db.commit()
        access = self.facilitator.get("/bookclub/members/community-access").json()
        reader_access = next(item for item in access if item["member_id"] == self.reader_member_id)
        self.assertEqual(reader_access["status"], "account_disabled")
        self.assertFalse(reader_access["announcements_enabled"])
        overview = self.facilitator.get("/bookclub/community/overview").json()
        self.assertEqual(overview["disabled_account_count"], 1)

    def test_facilitator_can_generate_an_invitation_qr_code(self) -> None:
        response = self.facilitator.get("/bookclub/community/invite-qr.svg")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.headers["content-type"].startswith("image/svg+xml"))
        self.assertEqual(response.headers["cache-control"], "private, no-store")
        self.assertIn("<svg", response.text)
        self.assertGreater(len(response.content), 500)

        club = self.facilitator.get("/bookclub/clubs/selected").json()
        updated = self.facilitator.patch(
            f"/bookclub/clubs/{club['id']}", json={"public": False}
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        unavailable = self.facilitator.get("/bookclub/community/invite-qr.svg")
        self.assertEqual(unavailable.status_code, 409, unavailable.text)

    def test_announcements_are_managed_by_facilitator_and_read_by_participant(self) -> None:
        created = self.facilitator.post("/bookclub/community/announcements", json={
            "title": "Bring your copy", "body": "We will compare editions.", "pinned": True,
        })
        self.assertEqual(created.status_code, 201, created.text)
        announcement_id = created.json()["id"]
        participant_list = self.reader.get("/participant/announcements")
        self.assertEqual(participant_list.status_code, 200, participant_list.text)
        self.assertEqual(participant_list.json()[0]["title"], "Bring your copy")
        self.assertTrue(participant_list.json()[0]["pinned"])

        updated = self.facilitator.patch(
            f"/bookclub/community/announcements/{announcement_id}",
            json={"body": "The room has changed."},
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["body"], "The room has changed.")
        deleted = self.facilitator.delete(f"/bookclub/community/announcements/{announcement_id}")
        self.assertEqual(deleted.status_code, 204, deleted.text)
        self.assertEqual(self.reader.get("/participant/announcements").json(), [])

    def test_rsvp_uses_existing_attendance_record_without_overwriting_attendance(self) -> None:
        meeting = self.create_meeting()
        saved = self.reader.put(
            f"/participant/meetings/{meeting['id']}/rsvp", json={"status": "maybe"}
        )
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(saved.json()["rsvp_status"], "maybe")
        roster = self.facilitator.get(f"/bookclub/meetings/{meeting['id']}/roster").json()
        self.assertEqual(roster[0]["rsvp_status"], "maybe")

        attended = self.facilitator.put(
            f"/bookclub/meetings/{meeting['id']}/members/{self.reader_member_id}",
            json={"attended": True},
        )
        self.assertEqual(attended.status_code, 200, attended.text)
        self.assertTrue(attended.json()["attended"])
        self.assertEqual(attended.json()["rsvp_status"], "maybe")
        with self.sessions() as db:
            self.assertEqual(db.scalar(select(BookClubParticipation)).rsvp_status, "maybe")

    def test_optional_reading_progress_preferences_calendar_and_activity(self) -> None:
        meeting = self.create_meeting()
        upcoming = self.reader.get("/participant/meetings/upcoming")
        self.assertEqual(upcoming.status_code, 200, upcoming.text)
        self.assertIn("calendar.google.com", upcoming.json()["google_calendar_url"])
        self.assertEqual(
            upcoming.json()["ics_calendar_url"],
            f"/participant/meetings/{meeting['id']}/calendar.ics",
        )
        calendar = self.reader.get(upcoming.json()["ics_calendar_url"])
        self.assertEqual(calendar.status_code, 200, calendar.text)
        self.assertTrue(calendar.headers["content-type"].startswith("text/calendar"))
        self.assertIn("SUMMARY:Book club: Dune", calendar.text)

        book_id = meeting["book_id"]
        empty_progress = self.reader.get(f"/participant/books/{book_id}/reading-progress")
        self.assertIsNone(empty_progress.json()["status"])
        saved_progress = self.reader.put(
            f"/participant/books/{book_id}/reading-progress",
            json={"status": "reading", "current_page": 120, "shared_with_club": True},
        )
        self.assertEqual(saved_progress.status_code, 200, saved_progress.text)
        self.assertEqual(saved_progress.json()["status"], "reading")
        self.assertEqual(saved_progress.json()["current_page"], 120)
        self.assertTrue(saved_progress.json()["shared_with_club"])
        detail = self.reader.get(f"/participant/books/{book_id}/detail")
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(detail.json()["shared_progress"][0]["current_page"], 120)
        feed = self.reader.get("/participant/club-activity")
        self.assertEqual(feed.json()[0]["kind"], "progress")
        activity = self.reader.get("/participant/activity")
        self.assertEqual(activity.status_code, 200, activity.text)
        self.assertEqual(activity.json()["recent"][0]["kind"], "progress")
        self.assertIn("Dune", activity.json()["recent"][0]["label"])
        cleared = self.reader.put(
            f"/participant/books/{book_id}/reading-progress", json={"status": None}
        )
        self.assertIsNone(cleared.json()["status"])
        self.assertEqual(self.reader.get("/participant/activity").json()["recent"], [])

        defaults = self.reader.get("/participant/notification-preferences")
        self.assertTrue(defaults.json()["announcements"])
        preferences = {
            "announcements": True,
            "polls": False,
            "meeting_reminders": True,
            "discussion_replies": False,
        }
        saved_preferences = self.reader.put(
            "/participant/notification-preferences", json=preferences
        )
        self.assertEqual(saved_preferences.status_code, 200, saved_preferences.text)
        current = self.reader.get("/participant/notification-preferences").json()
        for key, value in preferences.items():
            self.assertEqual(current[key], value)

    def test_participant_book_journey_and_stats_use_safe_aggregates(self) -> None:
        meeting = self.create_meeting()
        book_id = meeting["book_id"]
        book = self.facilitator.patch(f"/bookclub/books/{book_id}", json={
            "page_count": 412,
            "genres": "Science Fiction, Classics",
        })
        self.assertEqual(book.status_code, 200, book.text)
        completed = self.facilitator.patch(f"/bookclub/meetings/{meeting['id']}", json={
            "status": "completed",
            "discussion_notes": "The group debated power, ecology, and destiny.",
        })
        self.assertEqual(completed.status_code, 200, completed.text)
        attended = self.facilitator.put(
            f"/bookclub/meetings/{meeting['id']}/members/{self.reader_member_id}",
            json={"attended": True, "notes": "Private facilitator note"},
        )
        self.assertEqual(attended.status_code, 200, attended.text)
        self.reader.put(f"/participant/books/{book_id}/rating", json={"rating": 4.5})
        self.reader.put(f"/participant/books/{book_id}/reading-progress", json={
            "status": "finished", "current_page": 412,
        })

        journey = self.reader.get(f"/participant/books/{book_id}/detail")
        self.assertEqual(journey.status_code, 200, journey.text)
        self.assertEqual(journey.json()["sessions"][0]["attendance_count"], 1)
        self.assertEqual(journey.json()["reading_impact_pages"], 412)
        self.assertIn("ecology", journey.json()["sessions"][0]["discussion_notes"])
        self.assertNotIn("Private facilitator note", journey.text)

        personal = self.reader.get("/participant/stats/personal")
        self.assertEqual(personal.status_code, 200, personal.text)
        self.assertEqual(personal.json()["meetings_attended"], 1)
        self.assertEqual(personal.json()["books_read"], 1)
        self.assertEqual(personal.json()["pages_read"], 412)
        self.assertEqual(personal.json()["average_rating"], 4.5)
        self.assertEqual(personal.json()["finished_books"], 1)

        club = self.reader.get("/participant/stats/club")
        self.assertEqual(club.status_code, 200, club.text)
        self.assertEqual(club.json()["books_completed"], 1)
        self.assertEqual(club.json()["pages_read_together"], 412)
        self.assertEqual(club.json()["attendance_trend"][0]["attendance_count"], 1)
        self.assertEqual(club.json()["top_rated_books"][0]["title"], "Dune")
        self.assertNotIn("reader@example.com", club.text)

    def test_participant_member_experience_profile_library_discussion_and_read_state(self) -> None:
        meeting = self.create_meeting()
        question = self.facilitator.post(
            f"/bookclub/meetings/{meeting['id']}/questions",
            json={"text": "Which choice changed the story?"},
        )
        self.assertEqual(question.status_code, 201, question.text)
        upcoming = self.reader.get("/participant/meetings/upcoming")
        self.assertEqual(
            upcoming.json()["discussion_questions"],
            ["Which choice changed the story?"],
        )

        library = self.reader.get("/participant/books/library")
        self.assertEqual(library.status_code, 200, library.text)
        self.assertEqual(library.json()["current"][0]["title"], "Dune")
        self.assertEqual(library.json()["previously_read"], [])

        profile = self.reader.put("/participant/profile", json={
            "name": "Reader R.",
            "bio": "Mysteries, science fiction, and very long footnotes.",
            "avatar_url": "https://example.com/reader.jpg",
            "directory_visible": True,
        })
        self.assertEqual(profile.status_code, 200, profile.text)
        self.assertTrue(profile.json()["is_self"])
        self.assertEqual(self.reader.get("/participant/auth/me").json()["name"], "Reader R.")
        directory = self.reader.get("/participant/members")
        self.assertEqual(directory.status_code, 200, directory.text)
        self.assertEqual(directory.json()[0]["name"], "Reader R.")
        self.assertNotIn("email", directory.json()[0])

        book_id = meeting["book_id"]
        post = self.reader.post(f"/participant/books/{book_id}/discussion", json={
            "body": "The setting feels like another character.", "spoiler": True,
        })
        self.assertEqual(post.status_code, 201, post.text)
        reply = self.reader.post(f"/participant/books/{book_id}/discussion", json={
            "body": "Especially in the opening chapters.",
            "parent_id": post.json()["id"],
        })
        self.assertEqual(reply.status_code, 201, reply.text)
        discussion = self.reader.get(f"/participant/books/{book_id}/discussion")
        self.assertEqual(len(discussion.json()), 2)
        self.assertTrue(discussion.json()[0]["author"]["is_self"])
        self.assertTrue(discussion.json()[0]["spoiler"])
        reacted = self.reader.put(f"/participant/discussion/{post.json()['id']}/reaction")
        self.assertEqual(reacted.status_code, 200, reacted.text)
        self.assertEqual(reacted.json()["reaction_count"], 1)
        self.assertTrue(reacted.json()["reacted_by_me"])
        social_feed = self.reader.get("/participant/club-activity").json()
        self.assertTrue(any(item["kind"] == "discussion" for item in social_feed))

        announcement = self.facilitator.post("/bookclub/community/announcements", json={
            "title": "Room update", "body": "We are upstairs.", "pinned": False,
        })
        announcement_id = announcement.json()["id"]
        self.assertFalse(self.reader.get("/participant/announcements").json()[0]["read"])
        marked = self.reader.put(f"/participant/announcements/{announcement_id}/read")
        self.assertTrue(marked.json()["read"])
        self.assertTrue(self.reader.get("/participant/announcements").json()[0]["read"])

        preferences = self.reader.put("/participant/notification-preferences", json={
            "announcements": True,
            "polls": True,
            "meeting_reminders": True,
            "discussion_replies": True,
            "delivery_frequency": "daily_digest",
        })
        self.assertEqual(preferences.status_code, 200, preferences.text)
        self.assertEqual(preferences.json()["delivery_frequency"], "daily_digest")


if __name__ == "__main__":
    unittest.main()
