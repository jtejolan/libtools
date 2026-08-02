import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from accounts.models import LibtoolsUser, ToolAccess
from database import Base
from dependencies import get_db
from main import app
from security import hash_password


class LenderyAuthorizationTests(unittest.TestCase):
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
            users = {
                "admin": LibtoolsUser(
                    username="admin",
                    password_hash=hash_password("admin-password"),
                    role="admin",
                ),
                "manager": LibtoolsUser(
                    username="manager",
                    password_hash=hash_password("manager-password"),
                    role="user",
                ),
                "viewer": LibtoolsUser(
                    username="viewer",
                    password_hash=hash_password("viewer-password"),
                    role="user",
                ),
                "other": LibtoolsUser(
                    username="other",
                    password_hash=hash_password("other-password"),
                    role="user",
                ),
            }
            db.add_all(users.values())
            db.flush()
            db.add_all(
                [
                    ToolAccess(
                        user_id=users["manager"].id,
                        tool_key="lendery_manage",
                    ),
                    ToolAccess(
                        user_id=users["viewer"].id,
                        tool_key="lendery_view",
                    ),
                ]
            )
            db.commit()
        self.anonymous = TestClient(app)
        self.admin = self.logged_in("admin", "admin-password")
        self.manager = self.logged_in("manager", "manager-password")
        self.viewer = self.logged_in("viewer", "viewer-password")
        self.other = self.logged_in("other", "other-password")

    def tearDown(self) -> None:
        for client in (
            self.anonymous,
            self.admin,
            self.manager,
            self.viewer,
            self.other,
        ):
            client.close()

    def logged_in(self, username: str, password: str) -> TestClient:
        client = TestClient(app)
        response = client.post(
            "/auth/login",
            json={"username": username, "password": password},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return client

    def create_item(self) -> dict:
        response = self.manager.post(
            "/lendery/items",
            json={
                "name": "Projector kit",
                "barcode": "KIT-1",
                "components": [{"name": "Remote", "quantity": 1}],
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_inventory_requires_personal_account_and_permission(self) -> None:
        self.assertEqual(self.anonymous.get("/lendery/items").status_code, 401)
        self.assertEqual(self.other.get("/lendery/items").status_code, 403)

    def test_viewer_can_view_and_refresh(self) -> None:
        item = self.create_item()
        self.assertEqual(self.viewer.get("/lendery/items").status_code, 200)
        self.assertEqual(
            self.viewer.get(f"/lendery/items/{item['id']}").status_code,
            200,
        )
        self.assertEqual(
            self.viewer.post(
                f"/lendery/items/{item['id']}/availability/refresh"
            ).status_code,
            200,
        )

    def test_viewer_cannot_change_inventory(self) -> None:
        item = self.create_item()
        component_id = item["components"][0]["id"]
        attempts = [
            self.viewer.post(
                "/lendery/items",
                json={"name": "New item", "barcode": "NEW-1"},
            ),
            self.viewer.patch(
                f"/lendery/items/{item['id']}", json={"name": "Changed"}
            ),
            self.viewer.delete(f"/lendery/items/{item['id']}"),
            self.viewer.post(
                f"/lendery/items/{item['id']}/components",
                json={"name": "Cable", "quantity": 1},
            ),
            self.viewer.patch(
                f"/lendery/components/{component_id}", json={"name": "Changed"}
            ),
            self.viewer.post(
                f"/lendery/components/{component_id}/image",
                files={"image": ("photo.jpg", b"not-used", "image/jpeg")},
            ),
            self.viewer.delete(
                f"/lendery/components/{component_id}/image"
            ),
            self.viewer.delete(f"/lendery/components/{component_id}"),
        ]
        self.assertTrue(all(response.status_code == 403 for response in attempts))

    def test_manager_can_change_inventory_but_docs_need_platform_admin(self) -> None:
        item = self.create_item()
        changed = self.manager.patch(
            f"/lendery/items/{item['id']}", json={"name": "Updated kit"}
        )
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertEqual(self.manager.get("/docs").status_code, 403)
        self.assertEqual(self.admin.get("/docs").status_code, 200)

    def test_shared_lendery_login_endpoints_are_removed(self) -> None:
        self.assertEqual(
            self.anonymous.post(
                "/lendery/auth/login",
                json={"username": "clerk", "password": "old-password"},
            ).status_code,
            404,
        )


if __name__ == "__main__":
    unittest.main()
