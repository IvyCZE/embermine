import subprocess

from scripts.tests.helpers import SCRIPTS, TempDirTestCase, clean_env, make_stub_tools

BADGING = """package: name='yt.ivy.embermine' versionCode='159000001' versionName='159.0-dev.7' compileSdkVersion='36'
sdkVersion:'26'
targetSdkVersion:'36'
application-label:'Embermine'
application: label='Embermine' icon='res/mipmap-anydpi-v26/ic_launcher.xml'
launchable-activity: name='org.mozilla.fenix.App'  label='' icon=''
native-code: 'arm64-v8a'
"""

MANIFEST_WITH_SHARED_ID = (
    '      A: http://schemas.android.com/apk/res/android:sharedUserId(0x0101000b)='
    '"org.mozilla.firefox.sharedID" (Raw: "org.mozilla.firefox.sharedID")\n'
)
MANIFEST_WITHOUT = '      A: http://schemas.android.com/apk/res/android:versionCode(0x0101021b)=159000001\n'


class ApkInfoTests(TempDirTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.tools = make_stub_tools(self.tmp / "tools")
        self.apks = self.tmp / "apks"
        self.apks.mkdir()
        (self.apks / "embermine-159.0-dev.7-arm64-v8a.apk").write_bytes(b"x" * 10)
        self.badging = self.tmp / "badging.txt"
        self.manifest = self.tmp / "manifest.txt"
        self.badging.write_text(BADGING)
        self.manifest.write_text(MANIFEST_WITHOUT)

    def run_info(self, **env: str) -> tuple[subprocess.CompletedProcess[str], str]:
        out = self.tmp / "apk-info.txt"
        proc = subprocess.run(
            ["bash", str(SCRIPTS / "apk-info.sh"), "--dir", str(self.apks), "--out", str(out)],
            capture_output=True,
            text=True,
            check=False,
            env=clean_env(
                HOME=str(self.home),
                BUILD_TOOLS=str(self.tools),
                STUB_LOG=str(self.tmp / "log"),
                STUB_BADGING=str(self.badging),
                STUB_MANIFEST=str(self.manifest),
                **env,
            ),
        )
        return proc, out.read_text() if out.exists() else ""

    def test_reports_every_required_field(self) -> None:
        proc, text = self.run_info()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        for expected in (
            "=== embermine-159.0-dev.7-arm64-v8a.apk (10 bytes)",
            "package: name='yt.ivy.embermine'",
            "versionCode: 159000001",
            "versionName: 159.0-dev.7",
            "application-label:'Embermine'",
            "native-code: 'arm64-v8a'",
            "signature-verified: yes",
            "signer-sha256: F7:6F:69:93:74:D5:0B:B5:CF:6A:C6:75:4E:C5:9F:AA:3E:B1:77:74:AD:FF:BE:C9:73:B9:DD:D2:64:BD:C2:A0",
            "signer-sha256-hex: f76f699374d50bb5cf6ac6754ec59faa3eb17774adffbec973b9ddd264bdc2a0",
            "sharedUserId: absent",
            "launcher-icon: res/mipmap-anydpi-v26/ic_launcher.xml",
        ):
            self.assertIn(expected, text)

    def test_reports_shared_user_id_when_present(self) -> None:
        self.manifest.write_text(MANIFEST_WITH_SHARED_ID)
        _, text = self.run_info()
        self.assertIn("sharedUserId: present (org.mozilla.firefox.sharedID)", text)

    def test_no_apks_is_an_error(self) -> None:
        for apk in self.apks.glob("*.apk"):
            apk.unlink()
        proc, _ = self.run_info()
        self.assertNotEqual(proc.returncode, 0)

    def test_legacy_signer_wording_is_understood(self) -> None:
        proc, text = self.run_info(STUB_VERIFY_STYLE="legacy")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("signer-sha256-hex: f76f699374d50bb5cf6ac6754ec59faa3eb17774adffbec973b9ddd264bdc2a0", text)

    def test_different_certificates_across_schemes_fail(self) -> None:
        proc, _ = self.run_info(STUB_SECOND_DIGEST="ab" * 32)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("exactly one signer", proc.stderr)
