import os
import unittest
import uuid

from app.services.storage import S3Storage


@unittest.skipUnless(os.getenv("RUN_S3_INTEGRATION") == "1", "S3 integration is opt-in")
class S3StorageIntegrationTestCase(unittest.TestCase):
    def test_round_trip_against_s3_compatible_storage(self):
        storage = S3Storage()
        key = f"ci/{uuid.uuid4()}.txt"
        content = b"S3 integration content"
        try:
            self.assertEqual(storage.save(key, content, "text/plain"), key)
            self.assertEqual(storage.size(key), len(content))
            self.assertEqual(storage.read(key), content)
            with storage.materialize(key, ".txt") as path:
                self.assertEqual(path.read_bytes(), content)
        finally:
            storage.delete(key)


if __name__ == "__main__":
    unittest.main()
