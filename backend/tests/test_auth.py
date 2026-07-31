import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
from lendery.auth import hash_password
from lendery.models import User
from lendery.routes import get_db
from main import app


class LenderyAuthenticationTests(unittest.TestCase):
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
            db.add_all(
                [
                    User(
                        username="admin",
                        password_hash=hash_password("admin-password"),
                        role="admin",
                    ),
                    User(
                        username="clerk",
                        password_hash=hash_password("clerk-password"),
                        role="clerk",
                    ),
                ]
            )
            db.commit()
        self.anonymous = TestClient(app)
        self.admin = TestClient(app)
        self.clerk = TestClient(app)
        self.login(self.admin, "admin", "admin-password")
        self.login(self.clerk, "clerk", "clerk-password")

    def tearDown(self) -> None:
        self.anonymous.close()
        self.admin.close()
        self.clerk.close()

    def login(
        self,
        client: TestClient,
        username: str,
        password: str,
    ) -> None:
        response = client.post(
            "/lendery/auth/login",
            json={"username": username, "password": password},
        )
        self.assertEqual(response.status_code, 200)

    def create_item(self) -> dict:
        response = self.admin.post(
            "/lendery/items",
            json={
                "name": "Projector kit",
                "barcode": "KIT-1",
                "components": [
                    {
                        "name": "Remote",
                        "quantity": 1,
                    }
                ],
            },
        )
        self.assertEqual(response.status_code, 201)
        return response.json()

    def test_login_me_and_logout(self) -> None:
        failed = self.anonymous.post(
            "/lendery/auth/login",
            json={"username": "clerk", "password": "wrong-password"},
        )
        self.assertEqual(failed.status_code, 401)

        self.login(self.anonymous, "clerk", "clerk-password")
        me = self.anonymous.get("/lendery/auth/me")
        self.assertEqual(
            me.json(),
            {"username": "clerk", "role": "clerk"},
        )

        self.assertEqual(
            self.anonymous.post("/lendery/auth/logout").status_code,
            204,
        )
        self.assertEqual(
            self.anonymous.get("/lendery/auth/me").status_code,
            401,
        )

    def test_inventory_requires_login(self) -> None:
        self.assertEqual(
            self.anonymous.get("/lendery/items").status_code,
            401,
        )

    def test_clerk_can_view_and_refresh(self) -> None:
        item = self.create_item()

        self.assertEqual(self.clerk.get("/lendery/items").status_code, 200)
        self.assertEqual(
            self.clerk.get(f"/lendery/items/{item['id']}").status_code,
            200,
        )
        self.assertEqual(
            self.clerk.post(
                f"/lendery/items/{item['id']}/availability/refresh"
            ).status_code,
            200,
        )

    def test_clerk_cannot_modify_inventory_or_components(self) -> None:
        item = self.create_item()
        component_id = item["components"][0]["id"]

        attempts = [
            self.clerk.post(
                "/lendery/items",
                json={"name": "New item", "barcode": "NEW-1"},
            ),
            self.clerk.patch(
                f"/lendery/items/{item['id']}",
                json={"name": "Changed"},
            ),
            self.clerk.delete(f"/lendery/items/{item['id']}"),
            self.clerk.post(
                f"/lendery/items/{item['id']}/components",
                json={"name": "Cable", "quantity": 1},
            ),
            self.clerk.patch(
                f"/lendery/components/{component_id}",
                json={"name": "Changed"},
            ),
            self.clerk.delete(f"/lendery/components/{component_id}"),
        ]

        self.assertTrue(
            all(response.status_code == 403 for response in attempts)
        )

    def test_admin_can_change_shared_passwords(self) -> None:
        response = self.admin.put(
            "/lendery/auth/password",
            json={
                "username": "clerk",
                "new_password": "new-clerk-password",
            },
        )
        self.assertEqual(response.status_code, 204)

        new_client = TestClient(app)
        try:
            self.login(new_client, "clerk", "new-clerk-password")
        finally:
            new_client.close()

    def test_clerk_cannot_change_passwords_or_open_docs(self) -> None:
        password_response = self.clerk.put(
            "/lendery/auth/password",
            json={
                "username": "clerk",
                "new_password": "another-password",
            },
        )
        self.assertEqual(password_response.status_code, 403)
        self.assertEqual(self.clerk.get("/docs").status_code, 403)
        self.assertEqual(self.admin.get("/docs").status_code, 200)


if __name__ == "__main__":
    unittest.main()
