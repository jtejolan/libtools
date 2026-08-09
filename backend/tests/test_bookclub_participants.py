import unittest

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from accounts import login_throttle
from bookclub.facilitator_auth import require_facilitator
from bookclub.models import BookClub
from bookclub.participant_auth import require_participant_club
from bookclub.participant_models import ParticipantAccount
from bookclub import participant_tokens
from database import Base
from dependencies import get_db
from main import app, bookclub_public_app


class BookClubParticipantApiTests(unittest.TestCase):
    """Covers the bookclub.libtools.app participant auth stack.

    bookclub_public_app is a *separate* FastAPI instance mounted via
    Host("bookclub.libtools.app", ...) — dependency_overrides on `app`
    alone would not reach it, so the DB override has to be applied to both
    app objects (see docs/architecture.md's "three ASGI apps").
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(cls.engine)
        cls.sessions = sessionmaker(
            bind=cls.engine,
            autoflush=False,
            expire_on_commit=False,
        )

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
            club = BookClub(name="Sci-Fi Book Club", slug="sci-fi-book-club", public=True)
            private_club = BookClub(name="Staff Only Club", slug="staff-only-club", public=False)
            db.add_all([club, private_club])
            db.commit()
        # Default host ("testserver") matches neither lendery.libtools.app
        # nor bookclub.libtools.app, so this exercises the primary app.
        self.staff_client = TestClient(app)
        self.client = TestClient(app, base_url="http://bookclub.libtools.app")

    def tearDown(self) -> None:
        self.staff_client.close()
        self.client.close()
        login_throttle.reset()

    def register(self, *, club_slug="sci-fi-book-club", email="reader@example.com", password="a-long-password-1"):
        return self.client.post(
            "/participant/auth/register",
            json={
                "club_slug": club_slug,
                "name": "Reader One",
                "email": email,
                "password": password,
                "confirm_password": password,
            },
        )

    def test_register_creates_account_and_starts_session(self) -> None:
        response = self.register()
        self.assertEqual(response.status_code, 201, response.text)
        body = response.json()
        self.assertEqual(body["club_slug"], "sci-fi-book-club")
        self.assertFalse(body["email_verified"])

        me = self.client.get("/participant/auth/me")
        self.assertEqual(me.status_code, 200, me.text)
        self.assertEqual(me.json()["email"], "reader@example.com")

    def test_register_against_private_club_is_not_found(self) -> None:
        response = self.register(club_slug="staff-only-club")
        self.assertEqual(response.status_code, 404, response.text)

    def test_duplicate_email_in_same_club_conflicts(self) -> None:
        first = self.register()
        self.assertEqual(first.status_code, 201, first.text)
        second = self.register()
        self.assertEqual(second.status_code, 409, second.text)

    def test_same_email_in_different_clubs_is_allowed(self) -> None:
        with self.sessions() as db:
            db.add(BookClub(name="Mystery Club", slug="mystery-club", public=True))
            db.commit()
        first = self.register(club_slug="sci-fi-book-club")
        self.assertEqual(first.status_code, 201, first.text)
        second = self.register(club_slug="mystery-club")
        self.assertEqual(second.status_code, 201, second.text)

    def test_logout_ends_session(self) -> None:
        self.register()
        logout = self.client.post("/participant/auth/logout")
        self.assertEqual(logout.status_code, 204)
        me = self.client.get("/participant/auth/me")
        self.assertEqual(me.status_code, 401)

    def test_login_wrong_password_is_rejected(self) -> None:
        self.register(password="the-correct-password-1")
        self.client.post("/participant/auth/logout")
        response = self.client.post(
            "/participant/auth/login",
            json={"club_slug": "sci-fi-book-club", "email": "reader@example.com", "password": "wrong-password"},
        )
        self.assertEqual(response.status_code, 401)

    def test_login_success(self) -> None:
        self.register(password="the-correct-password-1")
        self.client.post("/participant/auth/logout")
        response = self.client.post(
            "/participant/auth/login",
            json={"club_slug": "sci-fi-book-club", "email": "reader@example.com", "password": "the-correct-password-1"},
        )
        self.assertEqual(response.status_code, 200, response.text)

    def test_participant_login_lockout_after_repeated_failures(self) -> None:
        self.register(password="the-correct-password-1")
        self.client.post("/participant/auth/logout")
        for _ in range(login_throttle.MAX_ATTEMPTS):
            response = self.client.post(
                "/participant/auth/login",
                json={"club_slug": "sci-fi-book-club", "email": "reader@example.com", "password": "wrong-password"},
            )
            self.assertEqual(response.status_code, 401)
        locked_out = self.client.post(
            "/participant/auth/login",
            json={"club_slug": "sci-fi-book-club", "email": "reader@example.com", "password": "the-correct-password-1"},
        )
        self.assertEqual(locked_out.status_code, 429, locked_out.text)
        self.assertIn("Retry-After", locked_out.headers)

    def test_verify_email_round_trip(self) -> None:
        register_response = self.register()
        participant_id = register_response.json()["id"]
        with self.sessions() as db:
            account = db.get(ParticipantAccount, participant_id)
            raw_token = participant_tokens.issue_token(
                db, account, participant_tokens.EMAIL_VERIFICATION, participant_tokens.EMAIL_VERIFICATION_LIFETIME
            )
            db.commit()

        response = self.client.post("/participant/auth/verify-email", json={"token": raw_token})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["email_verified"])

        reused = self.client.post("/participant/auth/verify-email", json={"token": raw_token})
        self.assertEqual(reused.status_code, 400)

    def test_password_reset_confirm_invalidates_existing_session(self) -> None:
        register_response = self.register(password="the-old-password-1")
        participant_id = register_response.json()["id"]
        with self.sessions() as db:
            account = db.get(ParticipantAccount, participant_id)
            raw_token = participant_tokens.issue_token(
                db, account, participant_tokens.PASSWORD_RESET, participant_tokens.PASSWORD_RESET_LIFETIME
            )
            db.commit()

        confirm = self.client.post(
            "/participant/auth/password-reset/confirm",
            json={"token": raw_token, "password": "the-new-password-1", "confirm_password": "the-new-password-1"},
        )
        self.assertEqual(confirm.status_code, 200, confirm.text)
        self.assertEqual(confirm.json()["club_slug"], "sci-fi-book-club")

        # The session that existed before the reset must no longer work.
        stale = self.client.get("/participant/auth/me")
        self.assertEqual(stale.status_code, 401)

        relogin = self.client.post(
            "/participant/auth/login",
            json={"club_slug": "sci-fi-book-club", "email": "reader@example.com", "password": "the-new-password-1"},
        )
        self.assertEqual(relogin.status_code, 200, relogin.text)

    def test_participant_and_staff_sessions_use_distinct_cookies(self) -> None:
        self.staff_client.post(
            "/auth/register",
            json={
                "name": "Fac Ilitator",
                "username": "facilitator",
                "password": "a-long-password-1",
                "confirm_password": "a-long-password-1",
            },
        )
        self.register()
        staff_cookie_names = {cookie.name for cookie in self.staff_client.cookies.jar}
        participant_cookie_names = {cookie.name for cookie in self.client.cookies.jar}
        self.assertIn("libtools_session", staff_cookie_names)
        self.assertIn("bookclub_participant_session", participant_cookie_names)
        self.assertTrue(staff_cookie_names.isdisjoint(participant_cookie_names))

    def create_club(self, *, club_name="Fantasy Readers", facilitator_email="owner@example.com"):
        return self.client.post(
            "/participant/clubs",
            json={
                "club_name": club_name,
                "club_description": "We read epic fantasy.",
                "facilitator_name": "Sam Owner",
                "facilitator_email": facilitator_email,
                "password": "owner-password-1",
                "confirm_password": "owner-password-1",
            },
        )

    def test_create_club_creates_self_serve_club_with_owner(self) -> None:
        response = self.create_club()
        self.assertEqual(response.status_code, 201, response.text)
        body = response.json()
        self.assertEqual(body["role"], "owner")
        self.assertEqual(body["club_slug"], "fantasy-readers")

        with self.sessions() as db:
            club = db.scalar(select(BookClub).where(BookClub.slug == "fantasy-readers"))
            self.assertIsNotNone(club)
            self.assertEqual(club.club_type, "self_serve")

        me = self.client.get("/participant/auth/me")
        self.assertEqual(me.status_code, 200, me.text)
        self.assertEqual(me.json()["role"], "owner")

    def test_create_club_retries_on_slug_collision(self) -> None:
        first = self.create_club(club_name="Sci-Fi Book Club", facilitator_email="owner1@example.com")
        self.assertEqual(first.status_code, 201, first.text)
        self.client.post("/participant/auth/logout")
        # "Sci-Fi Book Club" already exists as a fixture club (slug
        # sci-fi-book-club) — this collides twice (once with the fixture,
        # once with the club just created above) before landing on -3.
        second = self.create_club(club_name="Sci-Fi Book Club", facilitator_email="owner2@example.com")
        self.assertEqual(second.status_code, 201, second.text)
        self.assertNotEqual(first.json()["club_slug"], second.json()["club_slug"])

    def test_create_club_is_rate_limited(self) -> None:
        for i in range(login_throttle.MAX_ATTEMPTS):
            self.create_club(club_name=f"Club {i}", facilitator_email=f"owner{i}@example.com")
            self.client.post("/participant/auth/logout")
        locked_out = self.create_club(club_name="One Too Many", facilitator_email="toomany@example.com")
        self.assertEqual(locked_out.status_code, 429, locked_out.text)


class RequireFacilitatorTests(unittest.TestCase):
    """Direct unit tests of the require_facilitator dependency function,
    the "mechanical adapter" that lets facilitator_routes.py reuse crud.py
    unchanged (see docs/backend/bookclub.md)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(cls.engine)
        cls.sessions = sessionmaker(bind=cls.engine, autoflush=False, expire_on_commit=False)

    @classmethod
    def tearDownClass(cls) -> None:
        Base.metadata.drop_all(cls.engine)
        cls.engine.dispose()

    def setUp(self) -> None:
        with self.engine.begin() as connection:
            for table in reversed(Base.metadata.sorted_tables):
                connection.execute(table.delete())

    def test_owner_participant_is_granted_access_and_sets_db_info(self) -> None:
        with self.sessions() as db:
            club = BookClub(name="Owned Club", slug="owned-club", club_type="self_serve")
            db.add(club)
            db.flush()
            owner = ParticipantAccount(
                club_id=club.id, name="Owner", email="owner@example.com",
                password_hash="x", role="owner",
            )
            db.add(owner)
            db.commit()
            db.refresh(owner)

            resolved = require_facilitator(owner, require_participant_club(owner, db))
            self.assertEqual(resolved.id, club.id)
            self.assertEqual(db.info["bookclub_id"], club.id)

    def test_member_participant_is_rejected(self) -> None:
        with self.sessions() as db:
            club = BookClub(name="Owned Club", slug="owned-club-2", club_type="self_serve")
            db.add(club)
            db.flush()
            member = ParticipantAccount(
                club_id=club.id, name="Member", email="member@example.com",
                password_hash="x", role="member",
            )
            db.add(member)
            db.commit()
            db.refresh(member)

            with self.assertRaises(HTTPException) as ctx:
                require_facilitator(member, require_participant_club(member, db))
            self.assertEqual(ctx.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
