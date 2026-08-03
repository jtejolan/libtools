import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from accounts.models import LibtoolsUser, ToolAccess
from accounts.bootstrap import initialize_platform_accounts
from bookclub.models import BookClub, BookClubBook, BookClubMeeting
from database import Base
from dependencies import get_db
from lendery.models import Component, LenderyItem, MaintenanceCase
from main import app
from security import hash_password


class PlatformAccountTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(cls.engine)
        cls.sessions = sessionmaker(
            bind=cls.engine, autoflush=False, expire_on_commit=False
        )

        def override_get_db():
            db: Session = cls.sessions()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db

    @classmethod
    def tearDownClass(cls) -> None:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(cls.engine)
        cls.engine.dispose()

    def setUp(self) -> None:
        with self.engine.begin() as connection:
            for table in reversed(Base.metadata.sorted_tables):
                connection.execute(table.delete())
        with self.sessions() as db:
            admin = LibtoolsUser(
                username="admin",
                password_hash=hash_password("admin-password"),
                role="admin",
            )
            db.add(admin)
            db.commit()
        self.admin = TestClient(app)
        response = self.admin.post(
            "/auth/login",
            json={"username": "admin", "password": "admin-password"},
        )
        self.assertEqual(response.status_code, 200)

    def tearDown(self) -> None:
        self.admin.close()

    def create_user(self, username: str) -> dict:
        response = self.admin.post(
            "/api/admin/users",
            json={
                "username": username,
                "password": "starting-password",
                "confirm_password": "starting-password",
                "tools": ["bookclub"],
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_signed_in_homepage_redirects_to_dashboard(self) -> None:
        response = self.admin.get("/", follow_redirects=False)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], "/dashboard")
        self.assertEqual(response.headers["cache-control"], "private, no-store")

        public_homepage = self.admin.get("/home")
        self.assertEqual(public_homepage.status_code, 200)
        self.assertIn("Library Tools", public_homepage.text)

    def test_account_creation_login_and_offline_recovery(self) -> None:
        created = self.create_user("Taylor")
        self.assertTrue(created["recovery_code"])
        self.assertEqual(created["tools"], ["bookclub"])

        user = TestClient(app)
        try:
            login = user.post(
                "/auth/login",
                json={"username": "taylor", "password": "starting-password"},
            )
            self.assertEqual(login.status_code, 200)
            user.post("/auth/logout")

            recovered = user.post(
                "/auth/recover",
                json={
                    "username": "Taylor",
                    "recovery_code": created["recovery_code"].lower(),
                    "password": "replacement-password",
                    "confirm_password": "replacement-password",
                },
            )
            self.assertEqual(recovered.status_code, 200, recovered.text)
            self.assertNotEqual(
                recovered.json()["recovery_code"], created["recovery_code"]
            )
            self.assertEqual(
                user.post(
                    "/auth/login",
                    json={
                        "username": "Taylor",
                        "password": "replacement-password",
                    },
                ).status_code,
                200,
            )
        finally:
            user.close()

    def test_initial_admin_bootstrap_assigns_each_tool_once(self) -> None:
        with self.engine.begin() as connection:
            for table in reversed(Base.metadata.sorted_tables):
                connection.execute(table.delete())

        with patch.dict(
            "os.environ",
            {
                "LIBTOOLS_ADMIN_NAME": "admin",
                "LIBTOOLS_ADMIN_PASSWORD": "bootstrap-password",
            },
        ):
            with self.sessions() as db:
                initialize_platform_accounts(db)
                admin = db.scalar(
                    select(LibtoolsUser).where(LibtoolsUser.username == "admin")
                )
                assigned_tools = list(
                    db.scalars(
                        select(ToolAccess.tool_key)
                        .where(ToolAccess.user_id == admin.id)
                        .order_by(ToolAccess.tool_key)
                    )
                )

        self.assertEqual(
            assigned_tools,
            ["bookclub", "lendery_manage", "storytime"],
        )

    def test_lendery_view_is_default_and_edit_access_can_be_toggled(self) -> None:
        created = self.admin.post(
            "/api/admin/users",
            json={
                "username": "Inventory Viewer",
                "password": "viewer-password",
                "confirm_password": "viewer-password",
                "tools": [],
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(created.json()["tools"], [])
        client = TestClient(app)
        try:
            self.assertEqual(
                client.post(
                    "/auth/login",
                    json={
                        "username": "Inventory Viewer",
                        "password": "viewer-password",
                    },
                ).status_code,
                200,
            )
            self.assertEqual(client.get("/lendery/items").status_code, 200)
            self.assertEqual(client.get("/auth/me").status_code, 200)
            self.assertEqual(
                client.post(
                    "/lendery/items",
                    json={"name": "Projector", "barcode": "P-1"},
                ).status_code,
                403,
            )

            enabled = self.admin.patch(
                f"/api/admin/users/{created.json()['id']}",
                json={"tools": ["lendery_manage"]},
            )
            self.assertEqual(enabled.status_code, 200, enabled.text)
            self.assertEqual(enabled.json()["tools"], ["lendery_manage"])
            self.assertEqual(
                client.post(
                    "/lendery/items",
                    json={"name": "Projector", "barcode": "P-2"},
                ).status_code,
                201,
            )

            disabled = self.admin.patch(
                f"/api/admin/users/{created.json()['id']}",
                json={"tools": []},
            )
            self.assertEqual(disabled.status_code, 200, disabled.text)
            self.assertEqual(client.get("/lendery/items").status_code, 200)
            self.assertEqual(
                client.post(
                    "/lendery/items",
                    json={"name": "Projector", "barcode": "P-3"},
                ).status_code,
                403,
            )
        finally:
            client.close()

    def test_dashboard_summary_combines_live_workspace_data(self) -> None:
        meeting_date = date.today() + timedelta(days=5)
        with self.sessions() as db:
            admin = db.scalar(
                select(LibtoolsUser).where(LibtoolsUser.username == "admin")
            )
            unavailable = LenderyItem(
                name="Unavailable projector",
                barcode="DASH-1",
                availability_status="unavailable",
            )
            missing_part = LenderyItem(
                name="Kit with missing part",
                barcode="DASH-2",
                availability_status="available",
            )
            checked_out = LenderyItem(
                name="Repair queue item",
                barcode="DASH-3",
                availability_status="checked_out",
            )
            removed = LenderyItem(
                name="Removed item",
                barcode="DASH-4",
                lifecycle_status="removed",
                availability_status="unavailable",
            )
            db.add_all([unavailable, missing_part, checked_out, removed])
            db.flush()
            db.add(
                Component(
                    item_id=missing_part.id,
                    name="Power cable",
                    missing_reported_at=datetime.now(timezone.utc),
                )
            )
            db.add(
                MaintenanceCase(
                    item_id=checked_out.id,
                    title="Replace cracked case",
                    status="open",
                    opened_by_user_id=admin.id,
                    opened_by_name=admin.username,
                )
            )
            club = BookClub(name="Tuesday Readers", slug="tuesday-readers")
            db.add(club)
            db.flush()
            book = BookClubBook(
                club_id=club.id,
                title="Kindred",
                author="Octavia E. Butler",
            )
            db.add(book)
            db.flush()
            db.add(
                BookClubMeeting(
                    club_id=club.id,
                    meeting_date=meeting_date,
                    meeting_time="7:00 PM",
                    location="Meeting Room A",
                    book_id=book.id,
                    book_title=book.title,
                    book_author=book.author,
                )
            )
            db.commit()

        response = self.admin.get("/auth/dashboard-summary")
        self.assertEqual(response.status_code, 200, response.text)
        summary = response.json()
        self.assertEqual(summary["lendery"]["total_items"], 3)
        self.assertEqual(summary["lendery"]["checked_out_items"], 1)
        self.assertEqual(summary["lendery"]["attention_count"], 3)
        self.assertEqual(summary["bookclub"]["club_count"], 1)
        self.assertEqual(summary["bookclub"]["next_meeting"]["days_until"], 5)
        self.assertEqual(
            summary["bookclub"]["next_meeting"]["book_title"], "Kindred"
        )

    def test_dashboard_summary_hides_editor_attention_from_viewers(self) -> None:
        created = self.admin.post(
            "/api/admin/users",
            json={
                "username": "Dashboard Viewer",
                "password": "viewer-password",
                "confirm_password": "viewer-password",
                "tools": [],
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        viewer = TestClient(app)
        try:
            self.assertEqual(
                viewer.post(
                    "/auth/login",
                    json={
                        "username": "Dashboard Viewer",
                        "password": "viewer-password",
                    },
                ).status_code,
                200,
            )
            response = viewer.get("/auth/dashboard-summary")
            self.assertEqual(response.status_code, 200, response.text)
            self.assertIsNone(response.json()["lendery"]["attention_count"])
            self.assertFalse(response.json()["bookclub"]["has_access"])
        finally:
            viewer.close()

    def test_book_club_records_are_isolated_by_account(self) -> None:
        first = self.create_user("First Facilitator")
        second = self.create_user("Second Facilitator")
        clients = [TestClient(app), TestClient(app)]
        slugs = []
        try:
            for client, user in zip(clients, (first, second), strict=True):
                login = client.post(
                    "/auth/login",
                    json={
                        "username": user["username"],
                        "password": "starting-password",
                    },
                )
                self.assertEqual(login.status_code, 200)
                club = client.post(
                    "/bookclub/clubs",
                    json={"name": f"{user['username']} Club"},
                )
                self.assertEqual(club.status_code, 201, club.text)
                slugs.append(club.json()["slug"])
                selected = client.post(
                    f"/bookclub/clubs/{club.json()['id']}/select"
                )
                self.assertEqual(selected.status_code, 200)
                member = client.post(
                    "/bookclub/members",
                    json={
                        "name": "Shared Reader",
                        "email": "reader@example.com",
                        "joined_on": "2026-08-01",
                    },
                )
                self.assertEqual(member.status_code, 201, member.text)

            self.assertEqual(len(clients[0].get("/bookclub/members").json()), 1)
            self.assertEqual(len(clients[1].get("/bookclub/members").json()), 1)
            book = clients[0].post(
                "/bookclub/books",
                json={"title": "Kindred", "author": "Octavia E. Butler"},
            )
            self.assertEqual(book.status_code, 201, book.text)
            meeting = clients[0].post(
                "/bookclub/meetings",
                json={
                    "book_id": book.json()["id"],
                    "meeting_date": "2026-09-10",
                },
            )
            self.assertEqual(meeting.status_code, 201, meeting.text)
            public = clients[0].get(f"/api/public/clubs/{slugs[0]}")
            self.assertEqual(public.status_code, 200, public.text)
            self.assertEqual(
                public.json()["upcoming_meeting"]["book"]["title"], "Kindred"
            )
            forbidden = clients[0].post(
                f"/bookclub/clubs/{clients[1].get('/bookclub/clubs').json()[0]['id']}/select"
            )
            self.assertEqual(forbidden.status_code, 404)
        finally:
            for client in clients:
                client.close()


if __name__ == "__main__":
    unittest.main()
