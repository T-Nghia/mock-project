"""Loopback-only HTTP fault proxy in front of a real, dedicated MinIO server."""

from collections import deque
from http.client import HTTPConnection, HTTPSConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import socket
import threading
from urllib.parse import urlsplit


class S3FaultProxy:
    def __init__(self, endpoint):
        self.upstream = urlsplit(endpoint)
        self.faults = deque()
        self.deny_deletes = False
        self.forbidden_buckets = set()
        self.forbidden_requests = []
        self.request_seen = threading.Event()
        self.release = threading.Event()
        self.deleted = threading.Event()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_):
                pass  # Authorization/signatures must never enter logs.

            def forward(self):
                mode = outer.faults.popleft() if self.command == "DELETE" and outer.faults else None
                if self.command == "DELETE" and outer.deny_deletes:
                    mode = "403"
                bucket = urlsplit(self.path).path.split("/")[1]
                if bucket in outer.forbidden_buckets:
                    outer.forbidden_requests.append((self.command, self.path))
                    mode = "403"
                if mode in {"503", "timeout", "403"}:
                    outer.request_seen.set()
                    if mode == "timeout":
                        outer.release.wait(5)
                    code = "AccessDenied" if mode == "403" else "ServiceUnavailable"
                    payload = f"<Error><Code>{code}</Code><Message>Injected test failure</Message></Error>".encode()
                    self.send_response(403 if mode == "403" else 503)
                    self.send_header("Content-Type", "application/xml")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    try:
                        self.wfile.write(payload)
                    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                        pass
                    return
                connection_class = HTTPSConnection if outer.upstream.scheme == "https" else HTTPConnection
                connection = connection_class(outer.upstream.hostname, outer.upstream.port, timeout=10)
                try:
                    body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                    connection.request(self.command, self.path, body=body, headers=dict(self.headers))
                    response = connection.getresponse()
                    data = response.read()
                    if mode == "lost-response":
                        if response.status < 300:
                            outer.deleted.set()
                        self.close_connection = True
                        self.connection.shutdown(socket.SHUT_RDWR)
                        self.connection.close()
                        return
                    self.send_response(response.status)
                    for name, value in response.getheaders():
                        if name.lower() not in {"transfer-encoding", "connection", "content-length"}:
                            self.send_header(name, value)
                    self.send_header("Content-Length", response.getheader("Content-Length", "0") if self.command == "HEAD" else str(len(data)))
                    self.end_headers()
                    if self.command != "HEAD":
                        self.wfile.write(data)
                finally:
                    connection.close()

            do_GET = do_HEAD = do_PUT = do_POST = do_DELETE = forward

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        self.endpoint = f"http://127.0.0.1:{self.server.server_port}"
        return self

    def __exit__(self, *_):
        self.release.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)
