import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from accounts import login_throttle
from accounts.models import LibtoolsUser
from database import Base
from dependencies import get_db
from main import app, bookclub_public_app
from security import hash_password


class SelfServeClubAdminVisibilityTests(unittest.TestCase):
    """Covers GET /api/admin/bookclub/self-serve-clubs — the read-only,
    platform-admin-only support/abuse triage view over self-serve clubs,
    which have no BookClubAccess rows and are otherwise invisible to the
    staff /bookclub tool (see docs/backend/bookclub.md)."""

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
        with self.sessions() as db:
            db.add(
                LibtoolsUser(
                    name="Admin",
                    username="admin",
                    password_hash=hash_password("admin-password"),
                    role="admin",
                )
            )
            db.add(
                LibtoolsUser(
                    name="Staffer",
                    username="staffer",
                    password_hash=hash_password("staffer-password"),
                    role="user",
                )
            )
            db.commit()
        self.admin = TestClient(app)
        response = self.admin.post("/auth/login", json={"username": "admin", "password": "admin-password"})
        self.assertEqual(response.status_code, 200, response.text)
        self.bookclub = TestClient(app, base_url="http://bookclub.libtools.app")

    def tearDown(self) -> None:
        self.admin.close()
        self.bookclub.close()
        login_throttle.reset()

    def create_self_serve_club(self, name="Mystery Lovers Club", email="alex@example.com") -> dict:
        response = self.bookclub.post(
            "/participant/clubs",
            json={
                "club_name": name,
                "facilitator_name": "Alex Facilitator",
                "facilitator_email": email,
                "password": "facilitator-pw-1",
                "confirm_password": "facilitator-pw-1",
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_empty_when_no_self_serve_clubs(self) -> None:
        response = self.admin.get("/api/admin/bookclub/self-serve-clubs")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_lists_self_serve_club_with_facilitator_and_participant_count(self) -> None:
        self.create_self_serve_club()
        register = self.bookclub.post(
            "/participant/auth/register",
            json={
                "club_slug": "mystery-lovers-club",
                "name": "Reader One",
                "email": "reader@example.com",
                "password": "reader-password-1",
                "confirm_password": "reader-password-1",
            },
        )
        self.assertEqual(register.status_code, 201, register.text)

        response = self.admin.get("/api/admin/bookclub/self-serve-clubs")
        self.assertEqual(response.status_code, 200)
        clubs = response.json()
        self.assertEqual(len(clubs), 1)
        club = clubs[0]
        self.assertEqual(club["name"], "Mystery Lovers Club")
        self.assertEqual(club["slug"], "mystery-lovers-club")
        self.assertEqual(club["facilitator_name"], "Alex Facilitator")
        self.assertEqual(club["facilitator_email"], "alex@example.com")
        self.assertEqual(club["participant_count"], 2)
        self.assertIsNotNone(club["created_at"])

    def test_library_run_clubs_are_excluded(self) -> None:
        created = self.admin.post("/bookclub/clubs", json={"name": "Staff-Run Club"})
        self.assertEqual(created.status_code, 201, created.text)
        response = self.admin.get("/api/admin/bookclub/self-serve-clubs")
        self.assertEqual(response.json(), [])

    def test_non_admin_is_forbidden(self) -> None:
        staffer = TestClient(app)
        login = staffer.post("/auth/login", json={"username": "staffer", "password": "staffer-password"})
        self.assertEqual(login.status_code, 200)
        response = staffer.get("/api/admin/bookclub/self-serve-clubs")
        self.assertEqual(response.status_code, 403)
        staffer.close()

    def test_signed_out_visitor_is_unauthorized(self) -> None:
        anonymous = TestClient(app)
        response = anonymous.get("/api/admin/bookclub/self-serve-clubs")
        self.assertEqual(response.status_code, 401)
        anonymous.close()


if __name__ == "__main__":
    unittest.main()
