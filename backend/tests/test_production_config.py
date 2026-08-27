import unittest

from pydantic import ValidationError

from app.core.config import Settings


class ProductionConfigTestCase(unittest.TestCase):
    production_cookie = {
        "REFRESH_COOKIE_SECURE": True,
        "REFRESH_COOKIE_SAMESITE": "none",
        "DOCUMENT_PROCESSING_MODE": "celery",
    }

    def test_rejects_sample_jwt_secret_in_production(self):
        with self.assertRaises(ValidationError):
            Settings(
                ENV="production",
                JWT_SECRET_KEY="change-me-in-env",
                **self.production_cookie,
            )

    def test_rejects_short_jwt_secret_in_production(self):
        with self.assertRaises(ValidationError):
            Settings(
                ENV="production",
                JWT_SECRET_KEY="short-but-not-a-sample",
                **self.production_cookie,
            )

    def test_accepts_strong_jwt_secret_in_production(self):
        configured = Settings(
            ENV="production",
            JWT_SECRET_KEY="x" * 32,
            **self.production_cookie,
        )
        self.assertEqual(configured.ENV, "production")

    def test_admin_credentials_must_be_configured_together(self):
        with self.assertRaises(ValidationError):
            Settings(
                ENV="production",
                JWT_SECRET_KEY="x" * 32,
                ADMIN_EMAIL="admin@example.com",
                **self.production_cookie,
            )

    def test_requires_secure_cross_site_refresh_cookie_in_production(self):
        with self.assertRaises(ValidationError):
            Settings(
                ENV="production",
                JWT_SECRET_KEY="x" * 32,
                REFRESH_COOKIE_SECURE=False,
                REFRESH_COOKIE_SAMESITE="lax",
                DOCUMENT_PROCESSING_MODE="celery",
            )

    def test_requires_celery_document_processing_in_production(self):
        with self.assertRaises(ValidationError):
            Settings(
                ENV="production",
                JWT_SECRET_KEY="x" * 32,
                REFRESH_COOKIE_SECURE=True,
                REFRESH_COOKIE_SAMESITE="none",
                DOCUMENT_PROCESSING_MODE="background",
            )


if __name__ == "__main__":
    unittest.main()
