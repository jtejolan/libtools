import unittest
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from accounts import login_throttle
from bookclub.models import BookClub, BookClubMember
from bookclub.participant_models import ParticipantAccount
from database import Base
from dependencies import get_db
from main import app, bookclub_public_app


class BookClubParticipantApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        cls.sessions = sessionmaker(bind=cls.engine, autoflush=False, expire_on_commit=False)
        Base.metadata.create_all(cls.engine)

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
        with self.sessions() as db:
            db.add_all([
                BookClub(name="Sci-Fi Book Club", slug="sci-fi-book-club", public=True),
                BookClub(name="Private Club", slug="private-club", public=False),
            ])
            db.commit()
        self.client = TestClient(app, base_url="http://bookclub.libtools.app")

    def tearDown(self) -> None:
        self.client.close()
        login_throttle.reset()

    def register(self, email="reader@example.com", password="a-long-password-1"):
        return self.client.post("/participant/auth/register", json={
            "club_slug": "sci-fi-book-club", "name": "Reader One", "email": email,
            "password": password, "confirm_password": password,
        })

    def test_register_creates_one_account_and_one_linked_roster_member(self) -> None:
        response = self.register()
        self.assertEqual(response.status_code, 201, response.text)
        with self.sessions() as db:
            account = db.scalar(select(ParticipantAccount))
            member = db.scalar(select(BookClubMember))
            self.assertEqual(member.participant_account_id, account.id)
            self.assertEqual(response.json()["member_id"], member.id)
        self.assertEqual(self.client.get("/participant/auth/me").status_code, 200)

    def test_registration_claims_a_facilitator_preloaded_roster_entry(self) -> None:
        with self.sessions() as db:
            club = db.scalar(select(BookClub).where(BookClub.slug == "sci-fi-book-club"))
            db.add(BookClubMember(
                club_id=club.id, name="Preloaded Reader", email="reader@example.com",
                joined_on=date.today(), delivery_method="none",
            ))
            db.commit()
        response = self.register()
        self.assertEqual(response.status_code, 201, response.text)
        with self.sessions() as db:
            self.assertEqual(len(list(db.scalars(select(BookClubMember)))), 1)
            self.assertIsNotNone(db.scalar(select(BookClubMember)).participant_account_id)

    def test_global_account_can_claim_membership_in_another_club_on_login(self) -> None:
        first = self.register()
        self.assertEqual(first.status_code, 201, first.text)
        participant_id = first.json()["id"]
        with self.sessions() as db:
            other = BookClub(name="Mystery Club", slug="mystery-club", public=True)
            db.add(other)
            db.flush()
            db.add(BookClubMember(
                club_id=other.id, name="Reader One", email="reader@example.com",
                joined_on=date.today(), delivery_method="none",
            ))
            db.commit()
        self.client.post("/participant/auth/logout")
        response = self.client.post("/participant/auth/login", json={
            "club_slug": "mystery-club", "email": "reader@example.com", "password": "a-long-password-1",
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["id"], participant_id)
        with self.sessions() as db:
            self.assertEqual(len(list(db.scalars(select(ParticipantAccount)))), 1)

    def test_existing_global_email_is_directed_to_sign_in(self) -> None:
        self.assertEqual(self.register().status_code, 201)
        self.client.post("/participant/auth/logout")
        response = self.register()
        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn("Sign in", response.json()["detail"])

    def test_private_club_registration_is_not_exposed(self) -> None:
        response = self.client.post("/participant/auth/register", json={
            "club_slug": "private-club", "name": "Reader", "email": "reader@example.com",
            "password": "a-long-password-1", "confirm_password": "a-long-password-1",
        })
        self.assertEqual(response.status_code, 404, response.text)

    def test_participant_and_staff_sessions_use_distinct_cookies(self) -> None:
        self.assertEqual(self.register().status_code, 201)
        participant_cookie = self.client.cookies.get("bookclub_participant_session")
        self.assertTrue(participant_cookie)
        self.assertIsNone(self.client.cookies.get("libtools_session"))

    def test_participant_subdomain_redirects_facilitators_to_libtools(self) -> None:
        create = self.client.get("/create", follow_redirects=False)
        manage = self.client.get("/manage", follow_redirects=False)
        self.assertEqual(create.status_code, 302)
        self.assertEqual(create.headers["location"], "https://libtools.app/signup?next=/bookclub")
        self.assertEqual(manage.headers["location"], "https://libtools.app/bookclub/community")


if __name__ == "__main__":
    unittest.main()
