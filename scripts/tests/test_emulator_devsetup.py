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

FINISHED = "I ActivityManager: Finished processing BOOT_COMPLETED for u0"
GREEN_DUMP = "color/system_accent1_500 (0x0106003f) = 0xff4d8254\n"
BLUE_DUMP = "0x0106003f system_accent1_500: 0xff3c68ff"
# Android's un-overlaid default for system_primary_light (what Compose dynamicLightColorScheme reads on API 34).
BLUE_PRIMARY_DUMP = GREEN_DUMP + "color/system_primary_light (0x01060042) = 0xff445e91\n"
GREEN_PRIMARY_DUMP = GREEN_DUMP + "color/system_primary_light (0x01060042) = 0xff2e6b38\n"
ENABLED = (
    "android\n[x] com.android.systemui:accent\n[x] com.android.systemui:neutral\n[x] com.android.systemui:dynamic\n"
)
ACCENT_DISABLED = (
    "android\n[ ] com.android.systemui:accent\n[x] com.android.systemui:neutral\n[x] com.android.systemui:dynamic\n"
)
DYNAMIC_DISABLED = (
    "android\n[x] com.android.systemui:accent\n[x] com.android.systemui:neutral\n[ ] com.android.systemui:dynamic\n"
)


class FakeAdb:
    """Answers by substring of the command; an answer may be a callable of the number of earlier uses."""

    def __init__(self, answers: dict[str, object]) -> None:
        self.answers = answers
        self.commands: list[str] = []

    def shell(self, command: str, timeout: float = 60) -> str:
        self.commands.append(command)
        for needle, answer in self.answers.items():
            if needle in command:
                if callable(answer):
                    return answer(len([c for c in self.commands if needle in c]))
                return str(answer)
        return ""

    def puts(self) -> list[str]:
        return [c for c in self.commands if "settings put secure" in c]


def palette_adb(listing: object, dump: object = GREEN_DUMP, idmap: object = "stopped") -> FakeAdb:
    return FakeAdb(
        {
            "settings get secure": devsetup.palette_json(),
            "cmd overlay list android": listing,
            "cmd overlay dump": dump,
            "getprop init.svc.idmap2d": idmap,
        }
    )


class PaletteTests(unittest.TestCase):
    def test_palette_json_has_the_three_keys_of_a_preset_palette(self) -> None:
        data = json.loads(devsetup.palette_json("2E9E4F"))
        self.assertEqual(data["android.theme.customization.system_palette"], "2E9E4F")
        self.assertEqual(data["android.theme.customization.accent_color"], "2E9E4F")
        self.assertEqual(data["android.theme.customization.color_source"], "preset")

    def test_overlay_states_reads_the_enabled_marker(self) -> None:
        self.assertEqual(
            devsetup.overlay_states(ACCENT_DISABLED + "--- some.other.overlay\n"),
            {
                "com.android.systemui:accent": False,
                "com.android.systemui:neutral": True,
                "com.android.systemui:dynamic": True,
            },
        )

    def test_force_palette_quotes_the_json_and_records_the_state(self) -> None:
        value = devsetup.palette_json("2E9E4F")
        adb = palette_adb(ENABLED)
        logged: list[str] = []
        evidence = devsetup.force_palette(adb, logged.append, lambda _: None)  # type: ignore[arg-type]
        self.assertIn(f"settings put secure theme_customization_overlay_packages '{value}'", adb.commands[0])
        self.assertIn("palette applied: yes", evidence)
        self.assertIn(
            "overlays from cmd overlay list android: [x] com.android.systemui:accent; [x] com.android.systemui:neutral; [x] com.android.systemui:dynamic",
            evidence,
        )
        self.assertTrue(any("0xff4d8254 (green)" in line for line in evidence))
        self.assertEqual(logged[: len(evidence)], evidence)
        self.assertEqual(len(adb.puts()), 1)

    def test_green_dump_value_with_a_disabled_accent_overlay_is_not_applied(self) -> None:
        adb = palette_adb(ACCENT_DISABLED)
        state = devsetup.read_palette_state(adb)  # type: ignore[arg-type]
        self.assertTrue(state.green)
        self.assertTrue(state.readback_ok)
        self.assertFalse(state.applied)
        with self.assertRaises(devsetup.PaletteError) as ctx:
            devsetup.force_palette(adb, lambda _: None, lambda _: None)  # type: ignore[arg-type]
        self.assertEqual(len(adb.puts()), devsetup.PALETTE_ATTEMPTS)
        self.assertIn("palette applied: NO (com.android.systemui:accent is disabled)", ctx.exception.evidence)
        self.assertIn("[ ] com.android.systemui:accent", "\n".join(ctx.exception.evidence))

    def test_enabled_overlays_with_a_wallpaper_blue_accent_are_not_applied(self) -> None:
        state = devsetup.read_palette_state(palette_adb(ENABLED, BLUE_DUMP))  # type: ignore[arg-type]
        self.assertFalse(state.applied)
        self.assertIn("accent tone 0xff3c68ff is not green", state.problems())

    def test_a_missing_palette_overlay_is_not_applied(self) -> None:
        state = devsetup.read_palette_state(palette_adb("android\n[x] com.android.systemui:accent\n"))  # type: ignore[arg-type]
        self.assertFalse(state.applied)
        self.assertEqual(
            state.problems(),
            ["com.android.systemui:neutral is not listed", "com.android.systemui:dynamic is not listed"],
        )

    def test_force_palette_rewrites_the_setting_until_the_overlays_are_enabled(self) -> None:
        adb = palette_adb(lambda n: ACCENT_DISABLED if n <= devsetup.PALETTE_POLLS + 2 else ENABLED)
        evidence = devsetup.force_palette(adb, lambda _: None, lambda _: None)  # type: ignore[arg-type]
        self.assertEqual(len(adb.puts()), 2)
        self.assertTrue(any(c.startswith("settings delete secure") for c in adb.commands))
        self.assertIn("palette applied: yes", evidence)

    def test_late_attempts_enable_the_disabled_overlay_directly(self) -> None:
        adb = palette_adb(lambda n: ENABLED if n > 3 * devsetup.PALETTE_POLLS else ACCENT_DISABLED)
        devsetup.force_palette(adb, lambda _: None, lambda _: None)  # type: ignore[arg-type]
        enables = [c for c in adb.commands if c.startswith("cmd overlay enable")]
        self.assertEqual(enables, ["cmd overlay enable --user current com.android.systemui:accent"])

    def test_force_palette_fails_when_the_accent_never_turns_green(self) -> None:
        adb = palette_adb(ENABLED, BLUE_DUMP)
        with self.assertRaises(devsetup.PaletteError) as ctx:
            devsetup.force_palette(adb, lambda _: None, lambda _: None)  # type: ignore[arg-type]
        self.assertEqual(len(adb.puts()), devsetup.PALETTE_ATTEMPTS)
        self.assertTrue(any("0xff3c68ff (NOT green)" in line for line in ctx.exception.evidence))

    def test_is_greenish(self) -> None:
        self.assertTrue(devsetup.is_greenish("ff2e9e4f"))
        self.assertFalse(devsetup.is_greenish("ff3c68ff"))

    def test_force_palette_fails_on_a_failed_read_back(self) -> None:
        adb = FakeAdb(
            {
                "settings get secure": "null",
                "cmd overlay list android": ENABLED,
                "cmd overlay dump": GREEN_DUMP,
                "getprop init.svc.idmap2d": "stopped",
            }
        )
        with self.assertRaises(devsetup.PaletteError) as ctx:
            devsetup.force_palette(adb, lambda _: None, lambda _: None)  # type: ignore[arg-type]
        self.assertTrue(any("NO (setting read-back differs)" in line for line in ctx.exception.evidence))

    def test_confirm_palette_leaves_an_active_palette_alone(self) -> None:
        adb = palette_adb(ENABLED)
        evidence = devsetup.confirm_palette(adb, lambda _: None, lambda _: None)  # type: ignore[arg-type]
        self.assertIn("palette applied: yes", evidence)
        self.assertEqual(adb.puts(), [])

    def test_confirm_palette_forces_a_lost_palette_again(self) -> None:
        adb = palette_adb(lambda n: ACCENT_DISABLED if n == 1 else ENABLED)
        evidence = devsetup.confirm_palette(adb, lambda _: None, lambda _: None)  # type: ignore[arg-type]
        self.assertEqual(len(adb.puts()), 1)
        self.assertIn("palette applied: yes", evidence)


class DynamicOverlayTests(unittest.TestCase):
    """com.android.systemui:dynamic supplies system_primary_light, which Compose reads on API 34."""

    def test_the_dynamic_overlay_is_a_required_palette_overlay(self) -> None:
        self.assertIn("com.android.systemui:dynamic", devsetup.REQUIRED_OVERLAYS)

    def test_accent_and_neutral_without_dynamic_are_not_applied(self) -> None:
        state = devsetup.read_palette_state(palette_adb(DYNAMIC_DISABLED))  # type: ignore[arg-type]
        self.assertTrue(state.green)
        self.assertTrue(state.readback_ok)
        self.assertFalse(state.applied)
        self.assertEqual(state.problems(), ["com.android.systemui:dynamic is disabled"])

    def test_disabled_dynamic_overlay_is_enabled_from_attempt_three(self) -> None:
        adb = palette_adb(DYNAMIC_DISABLED)
        with self.assertRaises(devsetup.PaletteError):
            devsetup.force_palette(adb, lambda _: None, lambda _: None)  # type: ignore[arg-type]
        first_enable = next(i for i, c in enumerate(adb.commands) if c.startswith("cmd overlay enable"))
        puts_before = [c for c in adb.commands[:first_enable] if "settings put secure" in c]
        self.assertEqual(len(puts_before), devsetup.ENABLE_FROM_ATTEMPT)
        enables = [c for c in adb.commands if c.startswith("cmd overlay enable")]
        self.assertEqual(
            enables,
            ["cmd overlay enable --user current com.android.systemui:dynamic"]
            * (devsetup.PALETTE_ATTEMPTS - devsetup.ENABLE_FROM_ATTEMPT),
        )

    def test_primary_light_is_read_from_the_same_dump_as_the_accent(self) -> None:
        adb = palette_adb(ENABLED, BLUE_PRIMARY_DUMP)
        state = devsetup.read_palette_state(adb)  # type: ignore[arg-type]
        self.assertEqual(state.accent, "ff4d8254")
        self.assertEqual(state.primary_light, "ff445e91")
        self.assertEqual(adb.commands.count("cmd overlay dump"), 1)
        self.assertFalse(state.applied)
        self.assertIn("system_primary_light tone 0xff445e91 is not green", state.problems())

    def test_green_primary_light_and_accent_are_applied(self) -> None:
        state = devsetup.read_palette_state(palette_adb(ENABLED, GREEN_PRIMARY_DUMP))  # type: ignore[arg-type]
        self.assertTrue(state.applied)

    def test_primary_light_missing_from_the_dump_does_not_block(self) -> None:
        state = devsetup.read_palette_state(palette_adb(ENABLED, GREEN_DUMP))  # type: ignore[arg-type]
        self.assertEqual(state.primary_light, "")
        self.assertTrue(state.applied)

    def test_force_palette_refuses_a_blue_primary_light_even_with_a_green_accent(self) -> None:
        adb = palette_adb(ENABLED, BLUE_PRIMARY_DUMP)
        with self.assertRaises(devsetup.PaletteError) as ctx:
            devsetup.force_palette(adb, lambda _: None, lambda _: None)  # type: ignore[arg-type]
        self.assertEqual(len(adb.puts()), devsetup.PALETTE_ATTEMPTS)
        self.assertTrue(
            any(line.startswith("system_primary_light") and "(NOT green)" in line for line in ctx.exception.evidence)
        )

    def test_an_idmap2d_transaction_in_flight_is_not_applied(self) -> None:
        state = devsetup.read_palette_state(palette_adb(ENABLED, GREEN_DUMP, idmap="running"))  # type: ignore[arg-type]
        self.assertEqual(state.idmap2d, "running")
        self.assertFalse(state.applied)
        self.assertIn("idmap2d is running (overlay transaction in flight)", state.problems())

    def test_an_idle_or_unset_idmap2d_does_not_block(self) -> None:
        for status in ("stopped", ""):
            with self.subTest(status=status):
                state = devsetup.read_palette_state(palette_adb(ENABLED, GREEN_DUMP, idmap=status))  # type: ignore[arg-type]
                self.assertTrue(state.applied)

    def test_force_palette_waits_for_idmap2d_to_go_idle_without_rewriting_the_setting(self) -> None:
        adb = palette_adb(ENABLED, GREEN_DUMP, idmap=lambda n: "running" if n <= 2 else "stopped")
        evidence = devsetup.force_palette(adb, lambda _: None, lambda _: None)  # type: ignore[arg-type]
        self.assertEqual(len(adb.puts()), 1)
        self.assertIn("palette applied: yes", evidence)

    def test_evidence_lists_all_three_overlays_and_the_idmap2d_state(self) -> None:
        evidence = devsetup.force_palette(palette_adb(ENABLED, GREEN_PRIMARY_DUMP), lambda _: None, lambda _: None)  # type: ignore[arg-type]
        self.assertIn(
            "overlays from cmd overlay list android: [x] com.android.systemui:accent; [x] com.android.systemui:neutral; [x] com.android.systemui:dynamic",
            evidence,
        )
        self.assertIn("system_primary_light reported by cmd overlay dump: 0xff2e6b38 (green)", evidence)
        self.assertIn("idmap2d service: stopped (idle)", evidence)


class BootSettleTests(unittest.TestCase):
    def test_returns_once_user_zero_is_unlocked_and_boot_completed_has_finished(self) -> None:
        adb = FakeAdb(
            {
                "am get-started-user-state 0": lambda n: "User 0 is RUNNING_UNLOCKING"
                if n <= 2
                else "User 0 is RUNNING_UNLOCKED",
                "logcat -d -b system -s ActivityManager:I": lambda n: "" if n <= 3 else FINISHED,
            }
        )
        logged: list[str] = []
        sleeps: list[float] = []
        note = devsetup.wait_for_boot_settled(adb, logged.append, sleeps.append)  # type: ignore[arg-type]
        self.assertEqual(len(sleeps), 3)
        self.assertIn("RUNNING_UNLOCKED", note)
        self.assertIn("BOOT_COMPLETED finished", note)
        self.assertEqual(logged, [note])

    def test_user_unlock_can_also_be_read_from_dumpsys_user(self) -> None:
        adb = FakeAdb(
            {
                "am get-started-user-state 0": "",
                "dumpsys user": "mIsUserUnlocked=true",
                "logcat -d -b system -s ActivityManager:I": FINISHED,
            }
        )
        sleeps: list[float] = []
        devsetup.wait_for_boot_settled(adb, lambda _: None, sleeps.append)  # type: ignore[arg-type]
        self.assertEqual(sleeps, [])

    def test_timeout_logs_a_warning_and_does_not_raise(self) -> None:
        adb = FakeAdb(
            {
                "am get-started-user-state 0": "User 0 is RUNNING_UNLOCKED",
                "logcat -d -b system -s ActivityManager:I": "",
            }
        )
        logged: list[str] = []
        sleeps: list[float] = []
        note = devsetup.wait_for_boot_settled(adb, logged.append, sleeps.append, timeout=10)  # type: ignore[arg-type]
        self.assertLessEqual(sum(sleeps), 10)
        self.assertIn("did not settle", note)
        self.assertTrue(any(line.startswith("WARNING") for line in logged))

    def test_boot_completed_alone_does_not_settle_while_user_zero_is_locked(self) -> None:
        adb = FakeAdb(
            {
                "am get-started-user-state 0": "User 0 is RUNNING_UNLOCKING",
                "dumpsys user": "mIsUserUnlocked=false",
                "logcat -d -b system -s ActivityManager:I": FINISHED,
            }
        )
        note = devsetup.wait_for_boot_settled(adb, lambda _: None, lambda _: None, timeout=4)  # type: ignore[arg-type]
        self.assertIn("did not settle", note)
        self.assertIn("user 0 unlocked: False", note)


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

    def test_a_fresh_install_check_finds_no_earlier_install_and_clears_nothing(self) -> None:
        adb = FakeAdb({})
        note = devsetup.prepare_fresh_install(adb, "yt.ivy.embermine", lambda _: None)  # type: ignore[arg-type]
        self.assertIn("not installed before this run", note)
        self.assertEqual(adb.commands, ["pm path yt.ivy.embermine"])

    def test_an_earlier_install_has_its_app_data_cleared_before_the_install(self) -> None:
        adb = FakeAdb({"pm path": "package:/data/app/yt.ivy.embermine/base.apk", "pm clear": "Success"})
        note = devsetup.prepare_fresh_install(adb, "yt.ivy.embermine", lambda _: None)  # type: ignore[arg-type]
        self.assertIn("app data was cleared (Success)", note)
        self.assertEqual(adb.commands, ["pm path yt.ivy.embermine", "pm clear yt.ivy.embermine"])
