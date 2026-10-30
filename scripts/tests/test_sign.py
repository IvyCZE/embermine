import base64
import subprocess

from scripts.tests.helpers import SCRIPTS, TempDirTestCase, clean_env, make_stub_tools

OWNER_PASSWORD = "owner-store-pass-1234"
OWNER_KEY_PASSWORD = "owner-key-pass-5678"
OWNER_KEYSTORE = base64.b64encode(b"\x00fake-pkcs12-bytes\xff" * 8).decode()


class SignTests(TempDirTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.tools = make_stub_tools(self.tmp / "tools")
        self.log = self.tmp / "stub.log"
        self.log.write_text("")
        self.runner_temp = self.tmp / "runner-temp"
        self.runner_temp.mkdir()
        self.in_dir = self.tmp / "in"
        self.in_dir.mkdir()
        for abi in ("arm64-v8a", "x86_64"):
            (self.in_dir / f"app-{abi}-release-unsigned.apk").write_text(abi)
        self.out_dir = self.tmp / "out"

    def sign(self, *extra: str, **env: str) -> subprocess.CompletedProcess[str]:
        merged = clean_env(
            HOME=str(self.home),
            PATH=f"{self.tools}:/usr/bin:/bin",
            BUILD_TOOLS=str(self.tools),
            STUB_LOG=str(self.log),
            RUNNER_TEMP=str(self.runner_temp),
        )
        merged.update(env)
        return subprocess.run(
            [
                "bash", str(SCRIPTS / "sign.sh"),
                "--in-dir", str(self.in_dir), "--out-dir", str(self.out_dir), "--version", "159.0-dev.7",
                *extra,
            ],
            capture_output=True,
            text=True,
            env=merged,
            check=False,
        )

    def decide(self, *extra: str, **env: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(SCRIPTS / "sign.sh"), "--decide", *extra],
            capture_output=True,
            text=True,
            env=clean_env(HOME=str(self.home), **env),
            check=False,
        )

    def owner_env(self) -> dict[str, str]:
        return {
            "KEYSTORE_BASE64": OWNER_KEYSTORE,
            "KEYSTORE_PASSWORD": OWNER_PASSWORD,
            "KEY_PASSWORD": OWNER_KEY_PASSWORD,
        }

    def logged(self) -> str:
        return self.log.read_text()

    def test_decide_without_secrets_is_throwaway(self) -> None:
        for env in ({}, {"KEYSTORE_BASE64": ""}):
            with self.subTest(env=env):
                proc = self.decide(**env)
                self.assertEqual((proc.returncode, proc.stdout.strip()), (0, "throwaway"))

    def test_decide_with_secrets_is_owner(self) -> None:
        proc = self.decide(**self.owner_env())
        self.assertEqual((proc.returncode, proc.stdout.strip()), (0, "owner"))

    def test_decide_release_path_never_falls_back(self) -> None:
        proc = self.decide("--require-owner-key")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("throwaway", proc.stderr)
        proc = self.decide("--require-owner-key", KEYSTORE_BASE64="")
        self.assertNotEqual(proc.returncode, 0)
        proc = self.decide("--require-owner-key", **self.owner_env())
        self.assertEqual(proc.stdout.strip(), "owner")

    def test_decide_partial_secrets_fail(self) -> None:
        for missing in ("KEYSTORE_PASSWORD", "KEY_PASSWORD"):
            with self.subTest(missing=missing):
                env = self.owner_env()
                del env[missing]
                proc = self.decide(**env)
                self.assertNotEqual(proc.returncode, 0)
                self.assertIn(missing, proc.stderr)

    def test_without_secrets_generates_throwaway_key_and_signs(self) -> None:
        proc = self.sign()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("throwaway test key", proc.stdout)
        self.assertIn("keytool -genkeypair", self.logged())
        for abi in ("arm64-v8a", "x86_64"):
            self.assertTrue((self.out_dir / f"embermine-159.0-dev.7-{abi}.apk").is_file())
        self.assertFalse(any(self.out_dir.glob("*.idsig")))
        self.assertIn("--v4-signing-enabled false", self.logged())

    def test_throwaway_key_lives_in_runner_temp_and_is_removed(self) -> None:
        self.assertEqual(self.sign().returncode, 0)
        dirs = [line.split()[1] for line in self.logged().splitlines() if line.startswith("keystore-dir")]
        self.assertTrue(dirs)
        for d in dirs:
            self.assertTrue(d.startswith(str(self.runner_temp)), d)
        self.assertEqual(list(self.runner_temp.iterdir()), [])

    def test_with_secrets_uses_owner_key_and_never_generates_one(self) -> None:
        proc = self.sign(**self.owner_env())
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("owner key", proc.stdout)
        self.assertNotIn("keytool -genkeypair", self.logged())
        self.assertIn("--ks-key-alias owner-alias", self.logged())
        self.assertIn("-storepass:env EMBERMINE_KS_PASS", self.logged())
        self.assertEqual(list(self.runner_temp.iterdir()), [], "decoded keystore must be removed")

    def test_alias_comes_from_the_keystore_without_a_key_alias_variable(self) -> None:
        proc = self.sign(STUB_KEY_ENTRIES="embermine", **self.owner_env())
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("key alias: embermine", proc.stdout)
        self.assertIn("--ks-key-alias embermine", self.logged())

    def test_key_alias_variable_overrides_the_keystore(self) -> None:
        proc = self.sign(KEY_ALIAS="explicit", **self.owner_env())
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("--ks-key-alias explicit", self.logged())
        self.assertNotIn("keytool -list", self.logged())

    def test_keystore_without_exactly_one_private_key_fails(self) -> None:
        for entries in ("", "one two"):
            with self.subTest(entries=entries):
                proc = self.sign(STUB_KEY_ENTRIES=entries, **self.owner_env())
                self.assertNotEqual(proc.returncode, 0)
                self.assertIn("exactly one private key entry", proc.stderr)
                self.assertNotIn("apksigner sign", self.logged())

    def test_secret_values_never_reach_output_or_arguments(self) -> None:
        proc = self.sign(**self.owner_env())
        self.assertEqual(proc.returncode, 0, proc.stderr)
        for secret in (OWNER_PASSWORD, OWNER_KEY_PASSWORD, OWNER_KEYSTORE):
            for text in (proc.stdout, proc.stderr, self.logged()):
                self.assertNotIn(secret, text)
        self.assertIn("--ks-pass env:EMBERMINE_KS_PASS", self.logged())

    def test_passwords_are_masked_on_github_actions(self) -> None:
        proc = self.sign(GITHUB_ACTIONS="true", **self.owner_env())
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn(f"::add-mask::{OWNER_PASSWORD}", proc.stdout)
        self.assertIn(f"::add-mask::{OWNER_KEY_PASSWORD}", proc.stdout)

    def test_undecodable_keystore_fails_instead_of_falling_back(self) -> None:
        env = self.owner_env()
        env["KEYSTORE_BASE64"] = "%%% not base64 %%%"
        proc = self.sign(**env)
        self.assertNotEqual(proc.returncode, 0)
        self.assertNotIn("keytool", self.logged())
        self.assertFalse(self.out_dir.exists() and any(self.out_dir.iterdir()))

    def test_release_path_without_secrets_signs_nothing(self) -> None:
        proc = self.sign("--require-owner-key")
        self.assertNotEqual(proc.returncode, 0)
        self.assertNotIn("keytool", self.logged())
        self.assertNotIn("apksigner sign", self.logged())

    def test_unexpected_apk_fails(self) -> None:
        (self.in_dir / "app-universal-release-unsigned.apk").write_text("universal")
        proc = self.sign()
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("unexpected APK", proc.stderr)

    def test_missing_abi_fails(self) -> None:
        (self.in_dir / "app-x86_64-release-unsigned.apk").unlink()
        proc = self.sign()
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("missing", proc.stderr)

    def test_writes_signing_mode_to_github_output(self) -> None:
        out = self.tmp / "gh-output"
        self.assertEqual(self.sign(GITHUB_OUTPUT=str(out)).returncode, 0)
        self.assertEqual(out.read_text().strip(), "signing=throwaway")
