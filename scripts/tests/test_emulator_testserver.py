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
