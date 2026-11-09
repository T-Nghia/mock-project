"""Unit checks for fixture safety; these do not replace real PG/S3 acceptance."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location("security_harness", Path(__file__).with_name("run-security-local.py"))
harness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(harness)

MARKER = "next16-0123456789ab"


class FixtureSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="next16-harness-")
        self.addCleanup(self.temporary.cleanup)
        self.evidence = Path(self.temporary.name)
        self.calls = []
        self.removed_ids = set()

    def fake_docker(self, *parts, **kwargs):
        self.calls.append(parts)
        if parts[:1] == ("ps",):
            return "" if "owned" in self.removed_ids else "owned"
        if parts[:1] == ("inspect",):
            return json.dumps([{
                "Name": "/" + MARKER + "-backend",
                "Config": {"Labels": {"slrms.security-test": MARKER}},
            }])
        if parts[:2] == ("network", "ls"):
            return "" if "network-id" in self.removed_ids else "network-id"
        if parts[:2] == ("network", "inspect"):
            return json.dumps([{"Name": MARKER, "Labels": {"slrms.security-test": MARKER}}])
        if parts[:1] == ("rm",) or parts[:2] == ("network", "rm"):
            self.removed_ids.add(parts[-1])
        return ""

    def test_cleanup_targets_only_the_exact_owned_marker(self):
        with patch.object(harness, "docker", side_effect=self.fake_docker):
            result = harness.cleanup_owned(MARKER, self.evidence, capture_logs=False)
        self.assertEqual(result["removed"], ["owned"])
        self.assertEqual(result["networks_removed"], ["network-id"])
        self.assertIn(("ps", "--all", "--quiet", "--filter", "label=slrms.security-test=" + MARKER), self.calls)
        self.assertIn(("rm", "--force", "owned"), self.calls)
        self.assertIn(("network", "rm", "network-id"), self.calls)

    def test_changed_container_ownership_prevents_deletion_and_surfaces_failure(self):
        def changed(*parts, **kwargs):
            if parts[:1] == ("inspect",):
                self.calls.append(parts)
                return json.dumps([{"Name": "/foreign", "Config": {"Labels": {"slrms.security-test": "other"}}}])
            return self.fake_docker(*parts, **kwargs)
        with patch.object(harness, "docker", side_effect=changed):
            with self.assertRaisesRegex(RuntimeError, "ownership mismatch"):
                harness.cleanup_owned(MARKER, self.evidence, capture_logs=False)
        self.assertNotIn(("rm", "--force", "owned"), self.calls)
        self.assertTrue(json.loads((self.evidence / "cleanup.json").read_text())["errors"])

    def test_wrong_network_name_prevents_network_deletion(self):
        def changed(*parts, **kwargs):
            if parts[:2] == ("network", "inspect"):
                self.calls.append(parts)
                return json.dumps([{"Name": "shared", "Labels": {"slrms.security-test": MARKER}}])
            return self.fake_docker(*parts, **kwargs)
        with patch.object(harness, "docker", side_effect=changed):
            with self.assertRaisesRegex(RuntimeError, "ownership mismatch"):
                harness.cleanup_owned(MARKER, self.evidence, capture_logs=False)
        self.assertNotIn(("network", "rm", "network-id"), self.calls)

    def test_invalid_marker_cannot_query_or_remove_resources(self):
        with patch.object(harness, "docker") as command:
            with self.assertRaisesRegex(RuntimeError, "Invalid fixture ownership marker"):
                harness.cleanup_owned("", self.evidence)
        command.assert_not_called()

    def test_logs_are_bounded_and_redact_password_signing_key_and_tokens(self):
        password, signing_key = "fixture-password-value", "fixture-signing-key-value"
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ0ZXN0In0.signature"
        output = "x" * 40000 + "\n" + password + signing_key + jwt + " Bearer opaque-token\n"
        log = subprocess.CompletedProcess([], 0, stdout=output, stderr="")
        with patch.object(harness, "docker", side_effect=self.fake_docker):
            with patch.object(harness.subprocess, "run", return_value=log) as capture:
                harness.cleanup_owned(MARKER, self.evidence, (password, signing_key))
        self.assertEqual(capture.call_args.args[0], ["docker", "logs", "--tail", "200", "owned"])
        self.assertEqual(capture.call_args.kwargs["encoding"], "utf-8")
        self.assertEqual(capture.call_args.kwargs["errors"], "replace")
        data = next(self.evidence.glob("*.log")).read_text(encoding="utf-8")
        self.assertLessEqual(len(data.encode("utf-8")), harness.MAX_LOG_BYTES)
        for secret in [password, signing_key, jwt, "opaque-token"]:
            self.assertNotIn(secret, data)

    def test_log_failure_still_cleans_up_and_does_not_report_success(self):
        log = subprocess.CompletedProcess([], 1, stdout="", stderr="log capture error")
        with patch.object(harness, "docker", side_effect=self.fake_docker):
            with patch.object(harness.subprocess, "run", return_value=log):
                with self.assertRaisesRegex(RuntimeError, "log capture failed"):
                    harness.cleanup_owned(MARKER, self.evidence)
        self.assertIn(("rm", "--force", "owned"), self.calls)

    def test_unicode_log_capture_error_still_attempts_owned_removal(self):
        error = UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid byte")
        with patch.object(harness, "docker", side_effect=self.fake_docker):
            with patch.object(harness.subprocess, "run", side_effect=error):
                with self.assertRaises(RuntimeError):
                    harness.cleanup_owned(MARKER, self.evidence)
        self.assertIn(("rm", "--force", "owned"), self.calls)
        self.assertTrue(json.loads((self.evidence / "cleanup.json").read_text())["errors"])

    def test_os_log_capture_error_still_attempts_owned_removal(self):
        with patch.object(harness, "docker", side_effect=self.fake_docker):
            with patch.object(harness.subprocess, "run", side_effect=OSError("capture unavailable")):
                with self.assertRaises(RuntimeError):
                    harness.cleanup_owned(MARKER, self.evidence)
        self.assertIn(("rm", "--force", "owned"), self.calls)

    def test_docker_removal_failure_is_preserved(self):
        def failing(*parts, **kwargs):
            if parts[:1] == ("rm",):
                self.calls.append(parts)
                raise RuntimeError("controlled removal failure")
            return self.fake_docker(*parts, **kwargs)
        with patch.object(harness, "docker", side_effect=failing):
            with self.assertRaisesRegex(RuntimeError, "controlled removal failure"):
                harness.cleanup_owned(MARKER, self.evidence, capture_logs=False)
        result = json.loads((self.evidence / "cleanup.json").read_text())
        self.assertEqual(result["removed"], [])
        self.assertTrue(result["errors"])

    def test_normal_run_does_not_overwrite_interrupted_journal(self):
        root = self.evidence / "repo"
        evidence = root / ".cache/frontend-security-next16/real-backend"
        evidence.mkdir(parents=True)
        journal_path = evidence / "resources.json"
        original = json.dumps({"marker": MARKER, "containers": [], "network": None})
        journal_path.write_text(original, encoding="utf-8")

        def stop_before_fixtures(*parts, **kwargs):
            if parts[:2] == ("network", "create"):
                raise RuntimeError("controlled stop before fixture creation")
            return ""

        with patch.object(harness, "__file__", str(root / "e2e/scripts/run-security-local.py")):
            with patch.object(harness, "docker", side_effect=stop_before_fixtures):
                with patch.object(harness.socket, "socket"), patch.object(harness.signal, "signal"):
                    with patch("sys.argv", ["harness", "--backend-image", "backend", "--frontend-image", "frontend"]):
                        with self.assertRaises(RuntimeError):
                            harness.main()
        self.assertEqual(journal_path.read_text(encoding="utf-8"), original)

    def test_emergency_cleanup_does_not_capture_unredactable_logs(self):
        with patch.object(harness, "docker", side_effect=self.fake_docker):
            with patch.object(harness.subprocess, "run") as capture:
                harness.cleanup_owned(MARKER, self.evidence, capture_logs=False, filename="fallback-cleanup.json")
        capture.assert_not_called()
        self.assertTrue((self.evidence / "fallback-cleanup.json").exists())

    def interrupted_journal(self):
        path = self.evidence / "resources.json"
        data = {"marker": MARKER, "containers": [], "network": None}
        path.write_text(json.dumps(data), encoding="utf-8")
        return path, data

    def test_exclusive_journal_creation_refuses_overwrite_without_cleaning_old_resources(self):
        path, data = self.interrupted_journal()
        original = path.read_bytes()
        with patch.object(harness, "docker") as command:
            with self.assertRaisesRegex(RuntimeError, "Existing fixture journal"):
                harness.write_journal(path, {**data, "marker": "next16-fedcba987654"}, initial=True)
        command.assert_not_called()
        self.assertEqual(path.read_bytes(), original)

    def test_stale_recovery_archives_marker_then_allows_rerun_without_logs(self):
        path, old = self.interrupted_journal()
        with patch.object(harness, "docker", side_effect=self.fake_docker):
            with patch.object(harness.subprocess, "run") as capture:
                harness.recover_journal(path, self.evidence)
        capture.assert_not_called()
        self.assertFalse(path.exists())
        result = json.loads((self.evidence / "fallback-cleanup.json").read_text())
        self.assertEqual(result["removed"], ["owned"])
        self.assertEqual(json.loads((self.evidence / result["journal_archive"]).read_text()), old)
        new = {**old, "marker": "next16-fedcba987654"}
        harness.write_journal(path, new, initial=True)
        self.assertEqual(json.loads(path.read_text()), new)

    def test_failed_recovery_retains_old_marker_for_cleanup_retry(self):
        path, old = self.interrupted_journal()
        original = path.read_bytes()

        def unavailable(*parts, **kwargs):
            if parts[:1] == ("rm",):
                raise RuntimeError("controlled Docker removal failure")
            return self.fake_docker(*parts, **kwargs)

        with patch.object(harness, "docker", side_effect=unavailable):
            with self.assertRaisesRegex(RuntimeError, "controlled Docker removal failure"):
                harness.recover_journal(path, self.evidence)
        self.assertEqual(path.read_bytes(), original)
        with self.assertRaisesRegex(RuntimeError, "Existing fixture journal"):
            harness.write_journal(path, {**old, "marker": "next16-fedcba987654"}, initial=True)
        with patch.object(harness, "docker", side_effect=self.fake_docker):
            harness.recover_journal(path, self.evidence)
        self.assertFalse(path.exists())

    def test_recovery_ownership_mismatch_preserves_journal_and_resource(self):
        path, old = self.interrupted_journal()

        def changed(*parts, **kwargs):
            if parts[:1] == ("inspect",):
                self.calls.append(parts)
                return json.dumps([{"Name": "/foreign", "Config": {"Labels": {"slrms.security-test": "other"}}}])
            return self.fake_docker(*parts, **kwargs)

        with patch.object(harness, "docker", side_effect=changed):
            with self.assertRaisesRegex(RuntimeError, "ownership mismatch"):
                harness.recover_journal(path, self.evidence)
        self.assertEqual(json.loads(path.read_text()), old)
        self.assertNotIn(("rm", "--force", "owned"), self.calls)

    def test_journal_is_retained_if_resources_remain_after_cleanup(self):
        path, old = self.interrupted_journal()
        with patch.object(harness, "cleanup_owned", return_value={}):
            with patch.object(harness, "docker", side_effect=self.fake_docker):
                with self.assertRaisesRegex(RuntimeError, "resources remain"):
                    harness.recover_journal(path, self.evidence)
        self.assertEqual(json.loads(path.read_text()), old)

    def test_invalid_journal_refuses_recovery_without_docker_calls(self):
        path, data = self.interrupted_journal()
        data["marker"] = ""
        path.write_text(json.dumps(data), encoding="utf-8")
        with patch.object(harness, "docker") as command:
            with self.assertRaisesRegex(RuntimeError, "Invalid fixture journal marker"):
                harness.recover_journal(path, self.evidence)
        command.assert_not_called()
        self.assertEqual(json.loads(path.read_text()), data)

    def test_journal_update_cannot_replace_another_owner(self):
        path, old = self.interrupted_journal()
        with self.assertRaisesRegex(RuntimeError, "owner changed"):
            harness.write_journal(path, {**old, "marker": "next16-fedcba987654"})
        self.assertEqual(json.loads(path.read_text()), old)

    def test_journal_does_not_accept_credentials_fields(self):
        with self.assertRaisesRegex(RuntimeError, "Invalid fixture journal schema"):
            harness.write_journal(self.evidence / "resources.json", {
                "marker": MARKER, "containers": [], "network": None, "password": "not-a-real-secret",
            }, initial=True)
        self.assertFalse((self.evidence / "resources.json").exists())


if __name__ == "__main__":
    unittest.main()
