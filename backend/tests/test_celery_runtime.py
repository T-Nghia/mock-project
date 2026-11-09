"""Exercise Redis transport dependencies without a broker or cached imports."""

from pathlib import Path
import subprocess
import sys
import unittest


class CeleryRuntimeDependenciesTestCase(unittest.TestCase):
    def test_redis_transport_imports_with_a_supported_client_in_a_fresh_process(self):
        # A cold process catches a missing optional transport dependency even if
        # another test has already imported it. Metadata also catches a client
        # version that imports successfully but fails during worker startup.
        result = subprocess.run(
            [sys.executable, "-c", """
from importlib.metadata import requires, version
from kombu.transport import get_transport_cls
from packaging.requirements import Requirement

assert get_transport_cls("redis").driver_type == "redis"
for distribution in ("celery", "kombu"):
    for value in requires(distribution) or []:
        requirement = Requirement(value)
        if requirement.name == "redis" and (
            requirement.marker is None or requirement.marker.evaluate({"extra": "redis"})
        ):
            assert requirement.specifier.contains(version("redis")), (
                f"{distribution} requires {requirement}; installed redis={version('redis')}"
            )
"""],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            text=True,
            timeout=15,
        )
        # This probe imports only dependency modules/metadata; it never reads
        # application settings, environment URLs or credentials, or connects.
        self.assertEqual(result.returncode, 0, result.stderr)
