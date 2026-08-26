import unittest

from pydantic import ValidationError

from app.core.config import Settings


class ProductionConfigTestCase(unittest.TestCase):
    def test_rejects_sample_jwt_secret_in_production(self):
        with self.assertRaises(ValidationError):
            Settings(ENV="production", JWT_SECRET_KEY="change-me-in-env")

    def test_rejects_short_jwt_secret_in_production(self):
        with self.assertRaises(ValidationError):
            Settings(ENV="production", JWT_SECRET_KEY="short-but-not-a-sample")

    def test_accepts_strong_jwt_secret_in_production(self):
        configured = Settings(ENV="production", JWT_SECRET_KEY="x" * 32)
        self.assertEqual(configured.ENV, "production")

    def test_admin_credentials_must_be_configured_together(self):
        with self.assertRaises(ValidationError):
            Settings(
                ENV="production",
                JWT_SECRET_KEY="x" * 32,
                ADMIN_EMAIL="admin@example.com",
            )


if __name__ == "__main__":
    unittest.main()
