import unittest

from scripts.emulator import netreport


class NetreportTests(unittest.TestCase):
    def test_render_counts_hosts_and_states_the_session(self) -> None:
        text = netreport.render(
            {
                "DNS queries": ["example.com", "example.com", "a.example.net"],
                "TLS SNI": ["example.com"],
                "QUIC SNI": [],
            },
            session="light walk, default settings",
            visited=["https://example.com/"],
            pcap_bytes=1234,
        )
        self.assertIn("# Session captured: light walk, default settings", text)
        self.assertIn("#   https://example.com/", text)
        self.assertIn("     2 example.com", text)
        self.assertIn("## QUIC SNI (count, name)\n(none)", text)
        union = text.split("## All host names")[1]
        self.assertIn("     3 example.com", union)

    def test_empty_capture_is_visible(self) -> None:
        text = netreport.render({"DNS queries": []}, "s", [], 0)
        self.assertIn("(none)", text)

    def test_sni_lists_keep_only_the_first_name(self) -> None:
        text = netreport.render({"TLS SNI": ["a.example,b.example"]}, "s", [], 1)
        self.assertIn("     1 a.example", text)
        self.assertNotIn("b.example", text)
