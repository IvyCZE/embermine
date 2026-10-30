import json
import tempfile
import unittest
from pathlib import Path

from scripts.emulator import devsetup
from scripts.emulator.session import LaunchError

APK_INFO = """\
=== embermine-159.0-dev.5-arm64-v8a.apk (1 bytes)
package: name='org.mozilla.firefox' versionCode='159000001'
application-label:'Firefox'

=== embermine-159.0-dev.5-x86_64.apk (2 bytes)
package: name='yt.ivy.embermine' versionCode='159000002'
application-label:'Embermine'
"""


class FakeAdb:
    def __init__(self, answers: dict[str, str]) -> None:
        self.answers = answers
        self.commands: list[str] = []

    def shell(self, command: str, timeout: float = 60) -> str:
        self.commands.append(command)
        for needle, answer in self.answers.items():
            if needle in command:
                return answer
        return ""


class PaletteTests(unittest.TestCase):
    def test_palette_json_has_the_three_keys_of_a_preset_palette(self) -> None:
        data = json.loads(devsetup.palette_json("2E9E4F"))
        self.assertEqual(data["android.theme.customization.system_palette"], "2E9E4F")
        self.assertEqual(data["android.theme.customization.accent_color"], "2E9E4F")
        self.assertEqual(data["android.theme.customization.color_source"], "preset")

    def test_force_palette_quotes_the_json_and_records_the_read_back(self) -> None:
        value = devsetup.palette_json("2E9E4F")
        adb = FakeAdb(
            {
                "settings get secure": value,
                "cmd overlay list android": "[x] android.theme.accent.green\n[ ] other",
                "cmd overlay dump": "color/system_accent1_500 (0x0106003f) = 0xff2e9e4f\n",
            }
        )
        logged: list[str] = []
        evidence = devsetup.force_palette(adb, logged.append, lambda _: None)  # type: ignore[arg-type]
        self.assertIn(f"settings put secure theme_customization_overlay_packages '{value}'", adb.commands[0])
        self.assertIn("palette applied: yes", evidence)
        self.assertTrue(any("android.theme.accent.green" in line for line in evidence))
        self.assertIn("resolved system_accent1_500: 0xff2e9e4f (green)", evidence)
        self.assertEqual(logged[: len(evidence)], evidence)
        self.assertEqual(len([c for c in adb.commands if "settings put secure" in c]), 1)

    def test_force_palette_writes_again_while_the_accent_is_not_green(self) -> None:
        adb = FakeAdb({"settings get secure": devsetup.palette_json(), "cmd overlay dump": "0x0106003f system_accent1_500: 0xff3c68ff"})
        evidence = devsetup.force_palette(adb, lambda _: None, lambda _: None)  # type: ignore[arg-type]
        self.assertEqual(len([c for c in adb.commands if "settings put secure" in c]), 4)
        self.assertIn("resolved system_accent1_500: 0xff3c68ff (NOT green)", evidence)

    def test_is_greenish(self) -> None:
        self.assertTrue(devsetup.is_greenish("ff2e9e4f"))
        self.assertFalse(devsetup.is_greenish("ff3c68ff"))

    def test_force_palette_reports_a_failed_read_back(self) -> None:
        adb = FakeAdb({"settings get secure": "null"})
        evidence = devsetup.force_palette(adb, lambda _: None, lambda _: None)  # type: ignore[arg-type]
        self.assertTrue(any("NO (read-back differs)" in line for line in evidence))


class ApkTests(unittest.TestCase):
    def test_package_and_label_of_the_named_apk(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            info = Path(tmp) / "apk-info.txt"
            info.write_text(APK_INFO)
            self.assertEqual(devsetup.apk_package_and_label(info, "embermine-159.0-dev.5-x86_64.apk"), ("yt.ivy.embermine", "Embermine"))
            self.assertEqual(devsetup.apk_package_and_label(info, "embermine-159.0-dev.5-arm64-v8a.apk"), ("org.mozilla.firefox", "Firefox"))
            with self.assertRaises(LaunchError):
                devsetup.apk_package_and_label(info, "missing.apk")

    def test_find_apk_needs_exactly_one_x86_64_apk(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            with self.assertRaises(LaunchError):
                devsetup.find_apk(directory)
            (directory / "embermine-159.0-x86_64.apk").write_bytes(b"x")
            (directory / "embermine-159.0-arm64-v8a.apk").write_bytes(b"x")
            self.assertEqual(devsetup.find_apk(directory).name, "embermine-159.0-x86_64.apk")

    def test_missing_apk_fails_the_install_step(self) -> None:
        with self.assertRaises(LaunchError):
            devsetup.install_apk(FakeAdb({}), Path("/nonexistent.apk"), lambda _: None)  # type: ignore[arg-type]
