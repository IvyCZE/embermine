import http.client
import unittest

from scripts.emulator.testserver import WalkServer


class WalkServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.server = WalkServer(0, stall=0.2)
        self.server.start()
        self.addCleanup(self.server.close)
        self.port = self.server.server_address[1]

    def get(self, path: str) -> tuple[int, bytes]:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", path)
        response = conn.getresponse()
        return response.status, response.read()

    def test_page_is_long_and_immediate(self) -> None:
        status, body = self.get("/page")
        self.assertEqual(status, 200)
        self.assertIn(b"Embermine test page", body)
        self.assertGreater(len(body), 5000)

    def test_slow_page_sends_its_start_then_finishes(self) -> None:
        status, body = self.get("/slow")
        self.assertEqual(status, 200)
        self.assertTrue(body.endswith(b"</p>"))

    def test_refresh_is_fast_once_then_stalls_until_reset(self) -> None:
        self.assertIn(b"Embermine refresh page", self.get("/refresh")[1])
        self.assertEqual(self.server.refresh_hits, 1)
        self.assertEqual(self.get("/refresh")[0], 200)
        self.assertEqual(self.server.refresh_hits, 2)
        self.get("/reset")
        self.assertEqual(self.server.refresh_hits, 0)

    def test_unknown_path_is_404(self) -> None:
        self.assertEqual(self.get("/nope")[0], 404)


class DownloadEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.server = WalkServer(0, stall=0.2)
        self.server.big_size = 5000
        self.server.small_size = 700
        self.server.chunk = 1024
        self.server.delay = 0.0
        self.server.start()
        self.addCleanup(self.server.close)
        self.port = self.server.server_address[1]

    def request(self, method: str, path: str, headers: dict[str, str] | None = None) -> tuple[http.client.HTTPResponse, bytes]:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request(method, path, headers=headers or {})
        response = conn.getresponse()
        return response, response.read()

    def test_small_file_is_an_attachment_with_the_announced_length(self) -> None:
        response, body = self.request("GET", "/small.bin")
        self.assertEqual(response.status, 200)
        self.assertEqual(len(body), 700)
        self.assertEqual(response.getheader("Content-Length"), "700")
        self.assertEqual(response.getheader("Content-Type"), "application/octet-stream")
        self.assertIn("attachment", response.getheader("Content-Disposition", ""))
        self.assertIn("embermine-small-test-file.bin", response.getheader("Content-Disposition", ""))
        self.assertEqual(response.getheader("Accept-Ranges"), "bytes")

    def test_big_file_streams_in_chunks_to_its_full_size(self) -> None:
        response, body = self.request("GET", "/big.bin")
        self.assertEqual(response.status, 200)
        self.assertEqual(len(body), 5000)
        self.assertIn("embermine-large-test-file.bin", response.getheader("Content-Disposition", ""))

    def test_range_request_resumes_with_a_partial_response(self) -> None:
        response, body = self.request("GET", "/big.bin", {"Range": "bytes=4000-"})
        self.assertEqual(response.status, 206)
        self.assertEqual(len(body), 1000)
        self.assertEqual(response.getheader("Content-Range"), "bytes 4000-4999/5000")

    def test_range_past_the_end_is_not_satisfiable(self) -> None:
        response, _ = self.request("GET", "/big.bin", {"Range": "bytes=9000-"})
        self.assertEqual(response.status, 416)

    def test_head_reports_the_length_without_a_body(self) -> None:
        response, body = self.request("HEAD", "/big.bin")
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Content-Length"), "5000")
        self.assertEqual(body, b"")
