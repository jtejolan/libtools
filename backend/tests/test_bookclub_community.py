import unittest
from datetime import date, datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from accounts import login_throttle
from bookclub.models import BookClubParticipation
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

        with self.sessions() as db:
            account = db.scalar(select(ParticipantAccount))
            account.email_verified_at = datetime.now(timezone.utc)
            db.commit()
        activated = self.facilitator.get("/bookclub/community/overview").json()
        self.assertEqual(activated["verified_account_count"], 1)
        self.assertEqual(activated["pending_verification_count"], 0)

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


if __name__ == "__main__":
    unittest.main()
