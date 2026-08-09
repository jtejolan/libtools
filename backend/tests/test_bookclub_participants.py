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
from security import hash_password


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

    def test_existing_account_can_join_another_open_club(self) -> None:
        first = self.register()
        self.assertEqual(first.status_code, 201, first.text)
        with self.sessions() as db:
            db.add(BookClub(name="Open Mystery Club", slug="open-mystery", public=True))
            db.commit()
        joined = self.client.post("/participant/auth/clubs/open-mystery/join")
        self.assertEqual(joined.status_code, 200, joined.text)
        self.assertEqual(joined.json()["club_slug"], "open-mystery")
        with self.sessions() as db:
            memberships = list(db.scalars(select(BookClubMember)))
            self.assertEqual(len(memberships), 2)
            self.assertEqual(len({member.participant_account_id for member in memberships}), 1)

    def test_invitation_only_requires_a_preloaded_roster_email(self) -> None:
        with self.sessions() as db:
            club = db.scalar(select(BookClub).where(BookClub.slug == "sci-fi-book-club"))
            club.enrollment_policy = "invite_only"
            db.commit()
        rejected = self.register()
        self.assertEqual(rejected.status_code, 403, rejected.text)
        self.assertIn("invitation only", rejected.json()["detail"].lower())

        with self.sessions() as db:
            club = db.scalar(select(BookClub).where(BookClub.slug == "sci-fi-book-club"))
            db.add(BookClubMember(
                club_id=club.id, name="Invited Reader", email="reader@example.com",
                joined_on=date.today(), delivery_method="none",
            ))
            db.commit()
        accepted = self.register()
        self.assertEqual(accepted.status_code, 201, accepted.text)

    def test_closed_club_keeps_public_page_but_rejects_new_accounts(self) -> None:
        with self.sessions() as db:
            club = db.scalar(select(BookClub).where(BookClub.slug == "sci-fi-book-club"))
            club.enrollment_policy = "closed"
            db.commit()
        public = self.client.get("/api/public/clubs/sci-fi-book-club")
        self.assertEqual(public.status_code, 200, public.text)
        self.assertEqual(public.json()["enrollment_policy"], "closed")
        rejected = self.register()
        self.assertEqual(rejected.status_code, 403, rejected.text)

    def test_public_page_includes_invitation_design_and_calendar_ui(self) -> None:
        page = self.client.get("/clubs/sci-fi-book-club")
        self.assertEqual(page.status_code, 200, page.text)
        self.assertIn('/static/public-club.css?v=1', page.text)
        self.assertIn('/static/public-club.js?v=5', page.text)
        self.assertIn('id="account-benefits"', page.text)
        self.assertIn('id="meeting-details"', page.text)

    def test_global_login_lists_and_selects_all_clubs(self) -> None:
        first = self.register()
        self.assertEqual(first.status_code, 201, first.text)
        with self.sessions() as db:
            other = BookClub(
                name="Mystery Club", slug="mystery-club", public=True,
                organizer_branch="Central Library",
            )
            db.add(other)
            db.flush()
            db.add(BookClubMember(
                club_id=other.id, name="Reader One", email="reader@example.com",
                joined_on=date.today(), delivery_method="none",
            ))
            db.commit()
        self.client.post("/participant/auth/logout")

        response = self.client.post("/participant/auth/login/global", json={
            "email": "reader@example.com", "password": "a-long-password-1",
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            [club["slug"] for club in response.json()],
            ["mystery-club", "sci-fi-book-club"],
        )
        self.assertEqual(self.client.get("/participant/auth/me").json()["club_slug"], "mystery-club")

        selected = self.client.post("/participant/auth/clubs/sci-fi-book-club/select")
        self.assertEqual(selected.status_code, 200, selected.text)
        self.assertEqual(selected.json()["club_slug"], "sci-fi-book-club")
        self.assertEqual(
            len(self.client.get("/participant/auth/clubs").json()),
            2,
        )

    def test_global_login_rejects_an_account_without_a_public_membership(self) -> None:
        with self.sessions() as db:
            private = db.scalar(select(BookClub).where(BookClub.slug == "private-club"))
            account = ParticipantAccount(
                name="Private Reader",
                email="private@example.com",
                password_hash=hash_password("a-long-password-1"),
            )
            db.add(account)
            db.flush()
            db.add(BookClubMember(
                club_id=private.id, name=account.name, email=account.email,
                joined_on=date.today(), delivery_method="none",
                participant_account_id=account.id,
            ))
            db.commit()
        response = self.client.post("/participant/auth/login/global", json={
            "email": "private@example.com", "password": "a-long-password-1",
        })
        self.assertEqual(response.status_code, 403, response.text)

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
