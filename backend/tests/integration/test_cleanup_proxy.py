"""Real Caddy edge gate against a deliberately accepting legacy HTTP handler."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request


@unittest.skipUnless(os.getenv("RUN_CADDY_INTEGRATION") == "1", "Explicit real Caddy opt-in required")
class CleanupProxyTestCase(unittest.TestCase):
    def test_edge_gate_blocks_legacy_delete_and_keeps_other_routes_working(self):
        binary = os.getenv("CADDY_TEST_BINARY")
        self.assertTrue(binary, "A verified CADDY_TEST_BINARY is required")
        calls = []

        class Legacy(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps({"deletes": len(calls)}).encode())

            def do_DELETE(self):
                calls.append(self.path)
                self.do_GET()

        upstream = ThreadingHTTPServer(("127.0.0.1", 0), Legacy)
        thread = threading.Thread(target=upstream.serve_forever, daemon=True)
        thread.start()
        process = None
        repo = Path(__file__).resolve().parents[3]

        def free_port():
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
                return probe.getsockname()[1]

        api_port, frontend_port = free_port(), free_port()
        address = f"http://127.0.0.1:{api_port}"

        def request(path, method="GET", base=address):
            try:
                return urllib.request.urlopen(urllib.request.Request(base + path, method=method), timeout=2)
            except urllib.error.HTTPError as error:
                return error

        try:
            with tempfile.TemporaryDirectory(prefix="m3-real-caddy-") as directory:
                temp = Path(directory)
                guard = repo / "deploy/staging/delete-maintenance.caddy"
                config = (repo / "deploy/staging/Caddyfile").read_text(encoding="utf-8")
                config = config.replace("{\n", "{\n\tadmin off\n", 1)
                config = config.replace("backend:8000", f"127.0.0.1:{upstream.server_port}")
                config = config.replace("frontend:3000", f"127.0.0.1:{upstream.server_port}")
                config = config.replace("\timport security_headers", "\tbind 127.0.0.1\n\timport security_headers")
                config = config.replace("/etc/caddy/delete-maintenance.caddy", guard.as_posix())
                config_path = temp / "Caddyfile"
                config_path.write_bytes(config.encode())
                env = {**os.environ, "APP_DOMAIN": f"http://127.0.0.1:{frontend_port}", "API_DOMAIN": address,
                       "ACME_EMAIL": "test@example.com", "XDG_CONFIG_HOME": directory, "XDG_DATA_HOME": directory,
                       "APPDATA": directory, "LOCALAPPDATA": directory}
                command = [binary, "run", "--config", str(config_path), "--adapter", "caddyfile"]
                with (temp / "caddy.log").open("w", encoding="utf-8") as logs:
                    process = subprocess.Popen(command, env=env, stdout=logs, stderr=subprocess.STDOUT,
                                               creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                    try:
                        deadline = time.monotonic() + 60
                        while time.monotonic() < deadline:
                            if process.poll() is not None:
                                self.fail("Caddy startup failed: " + (temp / "caddy.log").read_text(encoding="utf-8"))
                            try:
                                with request("/health/live") as result:
                                    if result.status == 200:
                                        break
                            except OSError:
                                time.sleep(0.1)
                        else:
                            self.fail("Caddy readiness timeout")
                        # The upstream accepts a document DELETE; it has no M3 gate.
                        with request("/documents/legacy", "DELETE", f"http://127.0.0.1:{upstream.server_port}") as result:
                            self.assertEqual(result.status, 200)
                        self.assertEqual(len(calls), 1)
                        with request("/documents/legacy", "DELETE") as result:
                            self.assertEqual(result.status, 503)
                            self.assertEqual(result.headers["Retry-After"], "300")
                        self.assertEqual(len(calls), 1)
                        with request("/documents/legacy/bookmark", "DELETE") as result:
                            self.assertEqual(result.status, 200)
                        with request("/metrics") as result:
                            self.assertEqual(result.status, 404)
                    finally:
                        if process.poll() is None:
                            process.terminate()
                        process.wait(30)
        finally:
            upstream.shutdown()
            upstream.server_close()
            thread.join(5)
