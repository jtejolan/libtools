import os
import unittest
from unittest.mock import patch

from main import _session_secret


class SessionSecretTests(unittest.TestCase):
    def test_uses_the_configured_secret_when_present(self) -> None:
        with patch.dict(os.environ, {"LIBTOOLS_SESSION_SECRET": "configured-secret"}):
            self.assertEqual(_session_secret(), "configured-secret")

    def test_falls_back_to_a_random_secret_outside_railway(self) -> None:
        with patch.dict(os.environ, {}):
            os.environ.pop("LIBTOOLS_SESSION_SECRET", None)
            os.environ.pop("RAILWAY_ENVIRONMENT", None)
            self.assertTrue(_session_secret())

    def test_refuses_to_start_on_railway_without_a_configured_secret(self) -> None:
        with patch.dict(os.environ, {"RAILWAY_ENVIRONMENT": "production"}):
            os.environ.pop("LIBTOOLS_SESSION_SECRET", None)
            with self.assertRaises(RuntimeError):
                _session_secret()


if __name__ == "__main__":
    unittest.main()
