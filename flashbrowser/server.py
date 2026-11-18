from __future__ import annotations

import mimetypes
import secrets
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

mimetypes.add_type("application/wasm", ".wasm")
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("application/x-shockwave-flash", ".swf")
mimetypes.add_type("application/x-shockwave-flash", ".flv")

_ALLOWED_PROXY_SUFFIXES = {".swf", ".flv"}
_MAX_PROXY_BYTES = 64 * 1024 * 1024
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/87.0.4280.141 Safari/537.36"
)


class AssetServer:
    def __init__(self, assets_dir: Path):
        self.assets_dir = Path(assets_dir)
        self.token = secrets.token_urlsafe(24)
        self.qwebchannel_script = ""
        self._ui_dir = (self.assets_dir / "ui").resolve()
        self._ruffle_files = {
            path.name: path
            for path in (self.assets_dir / "ruffle").glob("*")
            if path.is_file()
        }
        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), self._make_handler())
        self._httpd.daemon_threads = True
        self.port = self._httpd.server_address[1]
        self._thread = threading.Thread(
            target=self._httpd.serve_forever, name="flash-assets", daemon=True
        )

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> None:
        if not self._thread.is_alive():
            self._thread.start()

    def stop(self) -> None:
        try:
            self._httpd.shutdown()
        except Exception:
            pass
        try:
            self._httpd.server_close()
        except Exception:
            pass

    def proxy_url_for_remote(self, url: str) -> str:
        query = urllib.parse.urlencode({"t": self.token, "url": url})
        return f"{self.base}/proxy?{query}"

    def proxy_url_for_file(self, path: str) -> str:
        query = urllib.parse.urlencode({"t": self.token, "file": path})
        return f"{self.base}/proxy?{query}"

    def viewer_url(self, src: str, name: str) -> str:
        query = urllib.parse.urlencode({"src": src, "name": name})
        return f"{self.base}/viewer?{query}"

    def home_url(self, params: dict[str, str]) -> str:
        return f"{self.base}/home?{urllib.parse.urlencode(params)}"

    def _make_handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def do_GET(self):
                parts = urllib.parse.urlsplit(self.path)
                path = parts.path
                if path in ("/", "/home"):
                    return self._send_file(server.assets_dir / "home.html")
                if path == "/viewer":
                    return self._send_file(server.assets_dir / "viewer.html")
                if path in ("/chrome", "/chrome/"):
                    return self._send_file(server._ui_dir / "chrome.html")
                if path.startswith("/ui/"):
                    return self._serve_ui(path[len("/ui/"):])
                if path == "/qwebchannel.js":
                    payload = server.qwebchannel_script
                    if not payload:
                        return self._send_bytes(b"not found", "text/plain; charset=utf-8", 404)
                    return self._send_bytes(
                        payload.encode("utf-8"), "application/javascript; charset=utf-8"
                    )
                if path.startswith("/ruffle/"):
                    name = urllib.parse.unquote(path[len("/ruffle/"):])
                    target = server._ruffle_files.get(name)
                    if target is None:
                        return self._send_bytes(b"not found", "text/plain; charset=utf-8", 404)
                    return self._send_file(target)
                if path == "/proxy":
                    return self._serve_proxy(urllib.parse.parse_qs(parts.query))
                if path == "/favicon.ico":
                    return self._send_bytes(b"", "image/x-icon", 204)
                return self._send_bytes(b"not found", "text/plain; charset=utf-8", 404)

            def _serve_ui(self, raw_name: str):
                name = urllib.parse.unquote(raw_name)
                if not name or "/" in name or "\\" in name or ".." in name:
                    return self._send_bytes(b"not found", "text/plain; charset=utf-8", 404)
                return self._send_file(server._ui_dir / name)

            def _send_file(self, path: Path):
                try:
                    data = Path(path).read_bytes()
                except OSError:
                    return self._send_bytes(b"not found", "text/plain; charset=utf-8", 404)
                content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
                if content_type.startswith("text/") or content_type in (
                    "application/javascript",
                    "application/json",
                ):
                    content_type += "; charset=utf-8"
                self._send_bytes(data, content_type)

            def _send_bytes(self, data: bytes, content_type: str, status: int = 200):
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                if data:
                    self.wfile.write(data)

            def _serve_proxy(self, query: dict[str, list[str]]):
                if query.get("t", [""])[0] != server.token:
                    return self._send_bytes(b"forbidden", "text/plain; charset=utf-8", 403)
                if "file" in query:
                    raw = query["file"][0]
                    target = Path(raw)
                    if target.suffix.lower() not in _ALLOWED_PROXY_SUFFIXES or not target.is_file():
                        return self._send_bytes(b"not found", "text/plain; charset=utf-8", 404)
                    try:
                        data = target.read_bytes()
                    except OSError:
                        return self._send_bytes(b"read failed", "text/plain; charset=utf-8", 500)
                    return self._send_bytes(data, "application/x-shockwave-flash")

                url = query.get("url", [""])[0]
                parsed = urllib.parse.urlsplit(url)
                if parsed.scheme not in ("http", "https"):
                    return self._send_bytes(b"bad url", "text/plain; charset=utf-8", 400)
                if Path(parsed.path).suffix.lower() not in _ALLOWED_PROXY_SUFFIXES:
                    return self._send_bytes(b"unsupported", "text/plain; charset=utf-8", 415)
                request = urllib.request.Request(
                    url,
                    headers={
                        "User-Agent": _USER_AGENT,
                        "Accept": "*/*",
                        "Accept-Encoding": "identity",
                    },
                )
                try:
                    with urllib.request.urlopen(request, timeout=30) as response:
                        data = response.read(_MAX_PROXY_BYTES)
                except (urllib.error.URLError, OSError, ValueError) as exc:
                    message = f"proxy failed: {exc}".encode("utf-8", "replace")
                    return self._send_bytes(message, "text/plain; charset=utf-8", 502)
                return self._send_bytes(data, "application/x-shockwave-flash")

        return Handler
