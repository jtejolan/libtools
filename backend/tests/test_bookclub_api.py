import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
from lendery.auth import hash_password
from lendery.models import User
from lendery.routes import get_db
from main import app


class BookClubApiTests(unittest.TestCase):
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
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(cls.engine)
        cls.engine.dispose()

    def setUp(self) -> None:
        with self.engine.begin() as connection:
            for table in reversed(Base.metadata.sorted_tables):
                connection.execute(table.delete())
        with self.sessions() as db:
            db.add(
                User(
                    username="admin",
                    password_hash=hash_password("admin-password"),
                    role="admin",
                )
            )
            db.commit()
        response = self.client.post(
            "/lendery/auth/login",
            json={"username": "admin", "password": "admin-password"},
        )
        self.assertEqual(response.status_code, 200)

    def create_member(self, name: str, email: str) -> dict:
        response = self.client.post(
            "/bookclub/members",
            json={
                "name": name,
                "email": email,
                "joined_on": "2026-08-01",
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def create_meeting(self) -> dict:
        response = self.client.post(
            "/bookclub/meetings",
            json={
                "meeting_date": "2026-09-10",
                "meeting_time": "7:00 PM",
                "location": "PBRL",
                "book_title": "The Left Hand of Darkness",
                "book_author": "Ursula K. Le Guin",
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_member_roster_filters_attendance_and_giveaway(self) -> None:
        alex = self.create_member("Alex Reader", "ALEX@example.com")
        blair = self.create_member("Blair Reader", "blair@example.com")
        meeting = self.create_meeting()

        roster = self.client.get(
            f"/bookclub/meetings/{meeting['id']}/roster"
        )
        self.assertEqual(roster.status_code, 200)
        self.assertEqual(len(roster.json()), 2)

        alex_update = self.client.put(
            f"/bookclub/meetings/{meeting['id']}/members/{alex['id']}",
            json={
                "delivery_method": "transfer",
                "destination_branch": "Maple Library",
                "book_checked_out": True,
                "attended": True,
            },
        )
        self.assertEqual(alex_update.status_code, 200, alex_update.text)
        self.client.put(
            f"/bookclub/meetings/{meeting['id']}/members/{blair['id']}",
            json={"delivery_method": "pickup", "attended": True},
        )

        received = self.client.get(
            f"/bookclub/meetings/{meeting['id']}/recipients?filter=checked_out"
        ).json()
        self.assertEqual([member["id"] for member in received], [alex["id"]])

        with patch("bookclub.crud.secrets.choice", return_value=None) as choose:
            choose.side_effect = lambda entries: entries[0]
            winner = self.client.post(
                f"/bookclub/meetings/{meeting['id']}/giveaway/draw"
            )
        self.assertEqual(winner.status_code, 200, winner.text)
        self.assertIn(winner.json()["member"]["id"], {alex["id"], blair["id"]})

        saved = self.client.post(
            f"/bookclub/meetings/{meeting['id']}/giveaway/draw"
        )
        self.assertEqual(saved.json(), winner.json())

        history = self.client.get(
            f"/bookclub/members/{alex['id']}/history"
        )
        self.assertEqual(history.status_code, 200)
        self.assertTrue(history.json()[0]["attended"])
        self.assertTrue(history.json()[0]["book_checked_out"])

    def test_sync_adds_new_regular_to_existing_meeting(self) -> None:
        self.create_member("First Reader", "first@example.com")
        meeting = self.create_meeting()
        self.create_member("Later Reader", "later@example.com")

        response = self.client.post(
            f"/bookclub/meetings/{meeting['id']}/roster/sync"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"added": 1, "total": 2})

    def test_templates_are_editable_renderable_and_restorable(self) -> None:
        templates = self.client.get("/bookclub/templates")
        self.assertEqual(templates.status_code, 200)
        self.assertEqual(len(templates.json()), 5)

        updated = self.client.patch(
            "/bookclub/templates/monthly_reminder",
            json={
                "subject": "Next: {{book_title}}",
                "body": "Hello {{first_name}} — see you {{meeting_date}}.",
            },
        )
        self.assertEqual(updated.status_code, 200, updated.text)

        preview = self.client.post(
            "/bookclub/templates/monthly_reminder/render",
            json={
                "variables": {
                    "first_name": "Alex",
                    "book_title": "Dune",
                }
            },
        )
        self.assertEqual(preview.json()["subject"], "Next: Dune")
        self.assertEqual(preview.json()["missing_variables"], ["meeting_date"])
        self.assertIn("{{meeting_date}}", preview.json()["body"])

        restored = self.client.post(
            "/bookclub/templates/monthly_reminder/restore"
        )
        self.assertEqual(restored.status_code, 200)
        self.assertIn("Sci-Fi Book Club reminder", restored.json()["subject"])

    def test_transit_labels_render_in_a_batch(self) -> None:
        alex = self.create_member("Alex Reader", "alex@example.com")
        self.create_member("Local Reader", "local@example.com")
        meeting = self.create_meeting()
        self.client.put(
            f"/bookclub/meetings/{meeting['id']}/members/{alex['id']}",
            json={
                "delivery_method": "transfer",
                "destination_branch": "Maple Library",
            },
        )

        response = self.client.post(
            f"/bookclub/meetings/{meeting['id']}/transit-labels/render",
            json={},
        )
        self.assertEqual(response.status_code, 200, response.text)
        labels = response.json()
        self.assertEqual(len(labels), 1)
        self.assertIn("Alex Reader", labels[0]["body"])
        self.assertIn("Maple Library", labels[0]["body"])
        self.assertIn("Josh at PBRL", labels[0]["body"])
        self.assertEqual(labels[0]["missing_variables"], [])

        previews = self.client.post(
            f"/bookclub/meetings/{meeting['id']}/emails/preview",
            json={"email_type": "onboarding", "member_ids": [alex["id"]]},
        )
        self.assertEqual(previews.status_code, 200, previews.text)
        self.assertEqual(previews.json()[0]["template_key"], "onboarding_transfer")
        self.assertIn("Maple Library", previews.json()[0]["body"])
        self.assertEqual(previews.json()[0]["missing_variables"], [])

    def test_questions_can_be_generated_edited_and_replaced(self) -> None:
        meeting = self.create_meeting()
        generated = self.client.post(
            f"/bookclub/meetings/{meeting['id']}/questions/generate",
            json={
                "count": 4,
                "focus": "science_fiction",
                "spoiler_free": True,
            },
        )
        self.assertEqual(generated.status_code, 201, generated.text)
        self.assertEqual(len(generated.json()), 4)
        self.assertTrue(
            all("ending" not in item["text"].lower() for item in generated.json())
        )

        question_id = generated.json()[0]["id"]
        edited = self.client.patch(
            f"/bookclub/questions/{question_id}",
            json={"text": "What surprised the group most?"},
        )
        self.assertEqual(edited.status_code, 200)

        replaced = self.client.post(
            f"/bookclub/meetings/{meeting['id']}/questions/generate",
            json={"count": 2, "replace_existing": True},
        )
        self.assertEqual(replaced.status_code, 201)
        self.assertEqual(len(replaced.json()), 2)
        saved = self.client.get(
            f"/bookclub/meetings/{meeting['id']}/questions"
        )
        self.assertEqual(len(saved.json()), 2)


if __name__ == "__main__":
    unittest.main()
