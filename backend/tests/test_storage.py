import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app.core.config import settings
from app.services.storage import S3Storage


class S3StorageTestCase(unittest.TestCase):
    def setUp(self):
        self.original = {
            "STORAGE_BUCKET": settings.STORAGE_BUCKET,
            "STORAGE_ENDPOINT_URL": settings.STORAGE_ENDPOINT_URL,
            "STORAGE_REGION": settings.STORAGE_REGION,
            "STORAGE_ACCESS_KEY_ID": settings.STORAGE_ACCESS_KEY_ID,
            "STORAGE_SECRET_ACCESS_KEY": settings.STORAGE_SECRET_ACCESS_KEY,
        }
        settings.STORAGE_BUCKET = "documents"
        settings.STORAGE_ENDPOINT_URL = "http://minio:9000"
        settings.STORAGE_REGION = "us-east-1"
        settings.STORAGE_ACCESS_KEY_ID = "minio"
        settings.STORAGE_SECRET_ACCESS_KEY = "minio-secret"

    def tearDown(self):
        for name, value in self.original.items():
            setattr(settings, name, value)

    @patch("app.services.storage.boto3.client")
    def test_save_read_size_and_delete_use_configured_bucket(self, client_factory):
        client = client_factory.return_value
        client.get_object.return_value = {"Body": Mock(read=Mock(return_value=b"content"))}
        client.head_object.return_value = {"ContentLength": 7}
        storage = S3Storage()

        location = storage.save("object.txt", b"content", "text/plain")

        self.assertEqual(location, "object.txt")
        client.put_object.assert_called_once_with(
            Bucket="documents",
            Key="object.txt",
            Body=b"content",
            ContentType="text/plain",
        )
        self.assertEqual(storage.read(location), b"content")
        self.assertEqual(storage.size(location), 7)
        storage.delete(location)
        client.delete_object.assert_called_once_with(Bucket="documents", Key="object.txt")

    @patch("app.services.storage.boto3.client")
    def test_materialize_downloads_object_to_temporary_file(self, client_factory):
        client = client_factory.return_value

        def download_file(bucket, key, filename):
            self.assertEqual((bucket, key), ("documents", "lesson.pdf"))
            Path(filename).write_bytes(b"pdf")

        client.download_file.side_effect = download_file
        storage = S3Storage()

        with storage.materialize("lesson.pdf", ".pdf") as path:
            self.assertEqual(path.suffix, ".pdf")
            self.assertEqual(path.read_bytes(), b"pdf")
