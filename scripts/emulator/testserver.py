"""Local web server for the emulator walk, reached from the emulator as http://10.0.2.2:<port>.

/page      a long page that loads at once
/slow      sends the start of a page, then stalls, so the page-load line stays visible
/refresh   loads at once the first time and stalls on every later request (pull-to-refresh)
/small.bin a 1 MB download that finishes at once
/big.bin   a large download streamed slowly, so it is still running when the Downloads screen is photographed;
           honours Range requests, so a paused download can resume
"""
from __future__ import annotations

import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

STALL_SECONDS = 25.0
SMALL_FILE_BYTES = 1_000_000
BIG_FILE_BYTES = 400 * 1024 * 1024
STREAM_CHUNK_BYTES = 64 * 1024
STREAM_DELAY_SECONDS = 0.05  # about 1.2 MB/s, so the big file needs more than five minutes
_RANGE = re.compile(r"bytes=(\d+)-")

_PARAGRAPH = (
    "<p>Embermine test page. This text only exists to make the page tall enough to scroll and to give the "
    "screenshots something to show. Material shapes, wavy progress lines and the loading indicator are "
    "drawn over pages like this one.</p>"
)


def page_html(title: str, paragraphs: int = 40) -> bytes:
    body = "".join(_PARAGRAPH for _ in range(paragraphs))
    return (
        "<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
        f"<title>{title}</title><style>body{{font:20px sans-serif;margin:0;padding:24px;background:#fff7e6;color:#222}}"
        f"h1{{color:#b45309}}</style></head><body><h1>{title}</h1>{body}</body></html>"
    ).encode()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"  # close-delimited bodies, so a stalled response needs no Content-Length
    server: "WalkServer"

    def log_message(self, fmt: str, *args: object) -> None:
        self.server.requests.append(f"{self.command} {self.path}")

    def _send_head(self, length: int | None) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        if length is not None:
            self.send_header("Content-Length", str(length))
        self.end_headers()

    def _stalled(self, title: str) -> None:
        self._send_head(None)
        self.wfile.write(f"<!doctype html><title>{title}</title><h1>{title}</h1><p>This page is still loading".encode())
        self.wfile.flush()
        self.server.stop.wait(self.server.stall)
        try:
            self.wfile.write(b"</p>")
        except OSError:
            pass

    def _download(self, name: str, size: int, *, head: bool) -> None:
        start = 0
        status = 200
        match = _RANGE.fullmatch(self.headers.get("Range", "").strip())
        if match is not None:
            start = int(match[1])
            status = 206
        if start >= size and match is not None:
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(status)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Disposition", f'attachment; filename="{name}"')
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("ETag", f'"{name}"')
        self.send_header("Content-Length", str(size - start))
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{size - 1}/{size}")
        self.end_headers()
        if head:
            return
        sent = start
        try:
            while sent < size and not self.server.stop.is_set():
                piece = min(self.server.chunk, size - sent)
                self.wfile.write(b"\0" * piece)
                self.wfile.flush()
                sent += piece
                if self.server.delay:
                    self.server.stop.wait(self.server.delay)
        except OSError:
            pass  # the client paused or cancelled the download

    def do_HEAD(self) -> None:  # noqa: N802 - http.server API
        self._route(head=True)

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        self._route(head=False)

    def _route(self, *, head: bool) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/small.bin":
            self._download("embermine-small-test-file.bin", self.server.small_size, head=head)
        elif path == "/big.bin":
            self._download("embermine-large-test-file.bin", self.server.big_size, head=head)
        elif path == "/page":
            body = page_html("Embermine test page")
            self._send_head(len(body))
            self.wfile.write(body)
        elif path == "/slow":
            self._stalled("Embermine slow page")
        elif path == "/refresh":
            with self.server.lock:
                self.server.refresh_hits += 1
                first = self.server.refresh_hits == 1
            if first:
                body = page_html("Embermine refresh page")
                self._send_head(len(body))
                self.wfile.write(body)
            else:
                self._stalled("Embermine refresh page")
        elif path == "/reset":
            with self.server.lock:
                self.server.refresh_hits = 0
            self._send_head(2)
            self.wfile.write(b"ok")
        else:
            self.send_error(404)


class WalkServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port: int, host: str = "127.0.0.1", stall: float = STALL_SECONDS) -> None:
        super().__init__((host, port), Handler)
        self.stall = stall
        self.small_size = SMALL_FILE_BYTES
        self.big_size = BIG_FILE_BYTES
        self.chunk = STREAM_CHUNK_BYTES
        self.delay = STREAM_DELAY_SECONDS
        self.lock = threading.Lock()
        self.refresh_hits = 0
        self.requests: list[str] = []
        self.stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self.serve_forever, daemon=True)
        self._thread.start()

    def close(self) -> None:
        self.stop.set()
        self.shutdown()
        self.server_close()

