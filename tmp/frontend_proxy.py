from __future__ import annotations

import http.client
import mimetypes
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


REPO_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"
BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 8001


def _content_type_for(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(str(path))
    if guessed:
        return guessed
    if path.suffix == ".js":
        return "application/javascript"
    if path.suffix == ".css":
        return "text/css"
    if path.suffix == ".svg":
        return "image/svg+xml"
    return "application/octet-stream"


class FrontendProxyHandler(BaseHTTPRequestHandler):
    server_version = "AEMGuidesFrontendProxy/1.0"

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        print(f"{self.address_string()} - {format % args}")

    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/api/"):
            self._proxy()
            return
        self._serve_spa()

    def do_POST(self) -> None:  # noqa: N802
        if self.path.startswith("/api/"):
            self._proxy()
            return
        self.send_error(404, "Not found")

    def do_PUT(self) -> None:  # noqa: N802
        if self.path.startswith("/api/"):
            self._proxy()
            return
        self.send_error(404, "Not found")

    def do_PATCH(self) -> None:  # noqa: N802
        if self.path.startswith("/api/"):
            self._proxy()
            return
        self.send_error(404, "Not found")

    def do_DELETE(self) -> None:  # noqa: N802
        if self.path.startswith("/api/"):
            self._proxy()
            return
        self.send_error(404, "Not found")

    def _serve_spa(self) -> None:
        request_path = urlsplit(self.path).path
        candidate = (FRONTEND_DIST / request_path.lstrip("/")).resolve()
        if request_path == "/" or not candidate.is_file() or not str(candidate).startswith(str(FRONTEND_DIST.resolve())):
            candidate = FRONTEND_DIST / "index.html"

        if not candidate.is_file():
            self.send_error(404, "Frontend build not found")
            return

        data = candidate.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", _content_type_for(candidate))
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _proxy(self) -> None:
        body = b""
        length = int(self.headers.get("Content-Length") or "0")
        if length:
            body = self.rfile.read(length)

        conn = http.client.HTTPConnection(BACKEND_HOST, BACKEND_PORT, timeout=600)
        try:
            forwarded_headers = {
                key: value
                for key, value in self.headers.items()
                if key.lower() not in {"host", "connection", "content-length"}
            }
            conn.request(self.command, self.path, body=body or None, headers=forwarded_headers)
            response = conn.getresponse()
            payload = response.read()
            self.send_response(response.status, response.reason)
            for key, value in response.getheaders():
                if key.lower() in {"transfer-encoding", "connection", "content-length"}:
                    continue
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            if payload:
                self.wfile.write(payload)
        finally:
            conn.close()


def main() -> None:
    if not FRONTEND_DIST.exists():
        raise SystemExit(f"Frontend dist directory not found: {FRONTEND_DIST}")
    server = ThreadingHTTPServer(("127.0.0.1", 5173), FrontendProxyHandler)
    print(f"Serving frontend from {FRONTEND_DIST}")
    print("Proxying /api to http://127.0.0.1:8001")
    print("Listening on http://127.0.0.1:5173")
    server.serve_forever()


if __name__ == "__main__":
    main()
