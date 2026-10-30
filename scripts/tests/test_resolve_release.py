import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "resolve_release", Path(__file__).resolve().parents[1] / "resolve-release.py"
)
assert _SPEC is not None and _SPEC.loader is not None
rr = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(rr)

SHA = "9a2dc53c369c7ae5172018b35988e1d2ffeff402"
PEELED = "1111111111111111111111111111111111111111"


class FakeHttp:
    """Maps URL -> JSON payload (dict), HTTP status int, or an exception to raise."""

    def __init__(self, responses: dict) -> None:
        self.responses = responses
        self.calls: list = []

    def get_json(self, url: str) -> dict:
        self.calls.append(("GET", url))
        r = self.responses.get(url)
        if r is None:
            raise rr.ResolveError(f"HTTP 404 for {url}")
        if isinstance(r, Exception):
            raise r
        return r

    def head_ok(self, url: str) -> bool:
        self.calls.append(("HEAD", url))
        return self.responses.get(url) == 200


def tc_urls(sha: str, task_id: str = "TASK1") -> tuple:
    index = rr.TASKCLUSTER_INDEX.format(sha=sha)
    task = rr.TASKCLUSTER_TASK.format(task_id=task_id)
    buildhub = rr.TASKCLUSTER_BUILDHUB.format(task_id=task_id)
    return index, task, buildhub


class TagTests(unittest.TestCase):
    def test_candidates_prefer_android_tag(self) -> None:
        self.assertEqual(
            rr.tag_candidates("159.0"), ["FIREFOX-ANDROID_159_0_RELEASE", "FIREFOX_159_0_RELEASE"]
        )
        self.assertEqual(
            rr.tag_candidates("158.0.2"),
            ["FIREFOX-ANDROID_158_0_2_RELEASE", "FIREFOX_158_0_2_RELEASE"],
        )

    def test_android_tag_wins_when_both_exist(self) -> None:
        remote = {"FIREFOX-ANDROID_159_0_RELEASE": "a" * 40, "FIREFOX_159_0_RELEASE": "b" * 40}
        tag, sha = rr.find_tag("159.0", remote.get)
        self.assertEqual((tag, sha), ("FIREFOX-ANDROID_159_0_RELEASE", "a" * 40))

    def test_falls_back_to_desktop_tag(self) -> None:
        remote = {"FIREFOX_159_0_RELEASE": SHA}
        tag, sha = rr.find_tag("159.0", remote.get)
        self.assertEqual((tag, sha), ("FIREFOX_159_0_RELEASE", SHA))

    def test_no_tag_is_an_error(self) -> None:
        with self.assertRaisesRegex(rr.ResolveError, "159.0"):
            rr.find_tag("159.0", lambda tag: None)

    def test_parse_ls_remote_prefers_peeled_sha(self) -> None:
        out = f"{SHA}\trefs/tags/FIREFOX_159_0_RELEASE\n{PEELED}\trefs/tags/FIREFOX_159_0_RELEASE^{{}}\n"
        self.assertEqual(rr.parse_ls_remote(out, "FIREFOX_159_0_RELEASE"), PEELED)

    def test_parse_ls_remote_lightweight_tag(self) -> None:
        out = f"{SHA}\trefs/tags/FIREFOX_159_0_RELEASE\n"
        self.assertEqual(rr.parse_ls_remote(out, "FIREFOX_159_0_RELEASE"), SHA)

    def test_parse_ls_remote_empty(self) -> None:
        self.assertIsNone(rr.parse_ls_remote("", "FIREFOX_159_0_RELEASE"))


class BuildIdTests(unittest.TestCase):
    def setUp(self) -> None:
        self.index, self.task, self.buildhub = tc_urls(SHA)

    def test_reads_moz_build_date(self) -> None:
        http = FakeHttp(
            {
                self.index: {"taskId": "TASK1"},
                self.task: {"payload": {"env": {"MOZ_BUILD_DATE": "20261022150525"}}},
            }
        )
        self.assertEqual(rr.geckoview_buildid(SHA, http), "20261022150525")
        self.assertFalse(any(url == self.buildhub for _, url in http.calls))

    def test_falls_back_to_buildhub(self) -> None:
        http = FakeHttp(
            {
                self.index: {"taskId": "TASK1"},
                self.task: {"payload": {"env": {}}},
                self.buildhub: {"build": {"id": "20261022150525"}},
            }
        )
        self.assertEqual(rr.geckoview_buildid(SHA, http), "20261022150525")

    def test_falls_back_when_value_malformed(self) -> None:
        http = FakeHttp(
            {
                self.index: {"taskId": "TASK1"},
                self.task: {"payload": {"env": {"MOZ_BUILD_DATE": "not-a-date"}}},
                self.buildhub: {"build": {"id": "20261022150525"}},
            }
        )
        self.assertEqual(rr.geckoview_buildid(SHA, http), "20261022150525")

    def test_mismatch_between_sources_is_an_error(self) -> None:
        http = FakeHttp(
            {
                self.index: {"taskId": "TASK1"},
                self.task: {"payload": {"env": {"MOZ_BUILD_DATE": "20261022150525"}}},
                self.buildhub: {"build": {"id": "20261022150526"}},
            }
        )
        self.assertEqual(rr.geckoview_buildid(SHA, http, cross_check=False), "20261022150525")
        with self.assertRaisesRegex(rr.ResolveError, "mismatch"):
            rr.geckoview_buildid(SHA, http, cross_check=True)

    def test_neither_source_available(self) -> None:
        http = FakeHttp({self.index: {"taskId": "TASK1"}, self.task: {"payload": {"env": {}}}})
        with self.assertRaises(rr.ResolveError):
            rr.geckoview_buildid(SHA, http)

    def test_missing_index_entry(self) -> None:
        with self.assertRaises(rr.ResolveError):
            rr.geckoview_buildid(SHA, FakeHttp({}))

    def test_valid_buildid_shape(self) -> None:
        self.assertTrue(rr.is_buildid("20261022150525"))
        for bad in ("2026102215052", "202610221505250", "abcdefghijklmn", "", None):
            self.assertFalse(rr.is_buildid(bad))


class MavenTests(unittest.TestCase):
    def test_pom_url(self) -> None:
        self.assertEqual(
            rr.maven_pom_url("159.0", "20261022150525"),
            "https://maven.mozilla.org/maven2/org/mozilla/geckoview/geckoview-omni/"
            "159.0.20261022150525/geckoview-omni-159.0.20261022150525.pom",
        )

    def test_missing_pom_is_an_error(self) -> None:
        with self.assertRaisesRegex(rr.ResolveError, "Maven"):
            rr.check_maven("159.0", "20261022150525", FakeHttp({}))

    def test_present_pom(self) -> None:
        url = rr.maven_pom_url("159.0", "20261022150525")
        self.assertEqual(rr.check_maven("159.0", "20261022150525", FakeHttp({url: 200})), url)


class ResolveTests(unittest.TestCase):
    def _http(self, version: str, buildid: str = "20261022150525") -> FakeHttp:
        index, task, _ = tc_urls(SHA)
        return FakeHttp(
            {
                index: {"taskId": "TASK1"},
                task: {"payload": {"env": {"MOZ_BUILD_DATE": buildid}}},
                rr.maven_pom_url(version, buildid): 200,
            }
        )

    def test_full_resolution(self) -> None:
        result = rr.resolve(
            "159.0", lambda tag: SHA if tag == "FIREFOX_159_0_RELEASE" else None, self._http("159.0")
        )
        self.assertEqual(
            result,
            {
                "version": "159.0",
                "tag": "FIREFOX_159_0_RELEASE",
                "sha": SHA,
                "buildid": "20261022150525",
                "geckoview_version": "159.0.20261022150525",
            },
        )

    def test_invalid_version(self) -> None:
        with self.assertRaises(rr.ResolveError):
            rr.resolve("159", lambda tag: SHA, self._http("159.0"))

    def test_reads_default_version_file(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "firefox-version.txt"
            p.write_text("159.0\n")
            self.assertEqual(rr.read_version_file(p), "159.0")


class OutputTests(unittest.TestCase):
    RESULT = {
        "version": "159.0",
        "tag": "FIREFOX_159_0_RELEASE",
        "sha": SHA,
        "buildid": "20261022150525",
        "geckoview_version": "159.0.20261022150525",
    }

    def test_github_output_lines(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "out"
            out.write_text("existing=1\n")
            rr.write_github_output(self.RESULT, str(out))
            lines = out.read_text().splitlines()
        self.assertEqual(lines[0], "existing=1")
        self.assertIn("tag=FIREFOX_159_0_RELEASE", lines)
        self.assertIn("buildid=20261022150525", lines)
        self.assertIn(f"sha={SHA}", lines)
        self.assertIn("version=159.0", lines)

    def test_cli_json_roundtrip_is_serialisable(self) -> None:
        self.assertEqual(json.loads(json.dumps(self.RESULT)), self.RESULT)

    def test_main_requires_github_output_env(self) -> None:
        old = os.environ.pop("GITHUB_OUTPUT", None)
        try:
            with self.assertRaises(rr.ResolveError):
                rr.write_github_output(self.RESULT, None)
        finally:
            if old is not None:
                os.environ["GITHUB_OUTPUT"] = old


if __name__ == "__main__":
    unittest.main()
