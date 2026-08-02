import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from accounts.models import LibtoolsUser, ToolAccess
from accounts.bootstrap import initialize_platform_accounts
from database import Base
from dependencies import get_db
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

    def test_lendery_access_is_a_personal_account_permission(self) -> None:
        created = self.admin.post(
            "/api/admin/users",
            json={
                "username": "Inventory Viewer",
                "password": "viewer-password",
                "confirm_password": "viewer-password",
                "tools": ["lendery_view"],
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
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
        finally:
            client.close()

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
