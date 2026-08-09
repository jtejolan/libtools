import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from accounts import login_throttle
from bookclub.participant_unsubscribe import issue_unsubscribe_token, verify_unsubscribe_token
from database import Base
from dependencies import get_db
from main import app, bookclub_public_app


class BroadcastEmailTests(unittest.TestCase):
    """Covers facilitator broadcast email (facilitator_routes.py's
    /bookclub/community/broadcast) and the public unsubscribe endpoint
    (unsubscribe_routes.py) — no email delivery is actually configured in
    tests (no RESEND_API_KEY), so `delivery_configured` is always False,
    but the recipient-selection, rendering, and unsubscribe-state logic all
    run for real."""

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
        created = self.facilitator.post("/bookclub/clubs", json={"name": "Mystery Lovers Club"})
        self.assertEqual(created.status_code, 201, created.text)
        self.facilitator.post(f"/bookclub/clubs/{created.json()['id']}/select")
        self.reader_a = self.register_reader("reader-a@example.com")
        self.reader_b = self.register_reader("reader-b@example.com")

    def register_reader(self, email: str) -> TestClient:
        client = TestClient(app, base_url="http://bookclub.libtools.app")
        response = client.post(
            "/participant/auth/register",
            json={
                "club_slug": "mystery-lovers-club",
                "name": email.split("@")[0],
                "email": email,
                "password": "reader-password-1",
                "confirm_password": "reader-password-1",
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        return client

    def tearDown(self) -> None:
        self.facilitator.close()
        self.reader_a.close()
        self.reader_b.close()
        login_throttle.reset()

    def create_email_template(self, key="meeting_reminder") -> None:
        response = self.facilitator.post(
            "/bookclub/community/templates",
            json={
                "key": key,
                "name": "Meeting reminder",
                "kind": "email",
                "subject": "See you at {{club_name}}!",
                "body": "Hi there, don't forget our meeting for {{club_name}}.",
            },
        )
        self.assertEqual(response.status_code, 201, response.text)

    def test_broadcast_reaches_all_participants(self) -> None:
        self.create_email_template()
        response = self.facilitator.post("/bookclub/community/broadcast", json={"template_key": "meeting_reminder"})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["recipient_count"], 2)
        self.assertFalse(body["delivery_configured"])  # no RESEND_API_KEY in tests
        self.assertEqual(body["missing_variables"], [])

    def test_broadcast_auto_fills_club_name_variable(self) -> None:
        # club_name isn't passed explicitly — facilitator_routes.py injects
        # it automatically so it's never a "missing" placeholder.
        self.create_email_template()
        response = self.facilitator.post("/bookclub/community/broadcast", json={"template_key": "meeting_reminder"})
        self.assertEqual(response.json()["missing_variables"], [])

    def test_broadcast_reports_missing_variables(self) -> None:
        self.facilitator.post(
            "/bookclub/community/templates",
            json={
                "key": "custom",
                "name": "Custom",
                "kind": "email",
                "subject": "Hi {{first_name}}",
                "body": "Body text.",
            },
        )
        response = self.facilitator.post("/bookclub/community/broadcast", json={"template_key": "custom"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("first_name", response.json()["missing_variables"])

    def test_broadcast_rejects_print_template(self) -> None:
        self.facilitator.post(
            "/bookclub/community/templates",
            json={"key": "sign", "name": "Sign", "kind": "print", "body": "Print body"},
        )
        response = self.facilitator.post("/bookclub/community/broadcast", json={"template_key": "sign"})
        self.assertEqual(response.status_code, 422, response.text)

    def test_broadcast_template_not_found(self) -> None:
        response = self.facilitator.post("/bookclub/community/broadcast", json={"template_key": "nope"})
        self.assertEqual(response.status_code, 404, response.text)

    def test_only_facilitator_can_broadcast(self) -> None:
        self.create_email_template()
        response = self.reader_a.post("/bookclub/community/broadcast", json={"template_key": "meeting_reminder"})
        self.assertEqual(response.status_code, 404, response.text)

    def test_unsubscribed_participant_excluded_from_broadcast_count(self) -> None:
        self.create_email_template()
        # Get reader A's own token via the same signing module the
        # broadcast endpoint uses (simulates clicking the emailed link).
        me = self.reader_a.get("/participant/auth/me").json()
        token = issue_unsubscribe_token(me["member_id"])
        unsub = self.reader_a.post("/participant/unsubscribe", json={"token": token})
        self.assertEqual(unsub.status_code, 200, unsub.text)
        self.assertFalse(unsub.json()["already_unsubscribed"])

        response = self.facilitator.post("/bookclub/community/broadcast", json={"template_key": "meeting_reminder"})
        self.assertEqual(response.json()["recipient_count"], 1)

    def test_unsubscribe_is_idempotent(self) -> None:
        me = self.reader_a.get("/participant/auth/me").json()
        token = issue_unsubscribe_token(me["member_id"])
        first = self.reader_a.post("/participant/unsubscribe", json={"token": token})
        second = self.reader_a.post("/participant/unsubscribe", json={"token": token})
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertFalse(first.json()["already_unsubscribed"])
        self.assertTrue(second.json()["already_unsubscribed"])

    def test_unsubscribe_does_not_require_login(self) -> None:
        me = self.reader_a.get("/participant/auth/me").json()
        token = issue_unsubscribe_token(me["member_id"])
        self.reader_a.post("/participant/auth/logout")
        response = self.reader_a.post("/participant/unsubscribe", json={"token": token})
        self.assertEqual(response.status_code, 200, response.text)

    def test_unsubscribe_rejects_invalid_token(self) -> None:
        response = self.reader_a.post("/participant/unsubscribe", json={"token": "not-a-real-token"})
        self.assertEqual(response.status_code, 400, response.text)

    def test_unsubscribe_rejects_tampered_token(self) -> None:
        me = self.reader_a.get("/participant/auth/me").json()
        token = issue_unsubscribe_token(me["id"])
        tampered = token[:-1] + ("a" if token[-1] != "a" else "b")
        response = self.reader_a.post("/participant/unsubscribe", json={"token": tampered})
        self.assertEqual(response.status_code, 400, response.text)

    def test_verify_unsubscribe_token_roundtrip(self) -> None:
        token = issue_unsubscribe_token(42)
        self.assertEqual(verify_unsubscribe_token(token), 42)
        self.assertIsNone(verify_unsubscribe_token("garbage"))


if __name__ == "__main__":
    unittest.main()
