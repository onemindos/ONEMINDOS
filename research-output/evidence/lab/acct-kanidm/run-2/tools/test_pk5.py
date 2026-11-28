# SPDX-License-Identifier: Apache-2.0
"""Exercise the PK-5 verdict against the recorded browser errors and lab faults."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, mock_open, patch

TOOLS = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("wa", TOOLS / "wa.py")
wa = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(wa)
ROWS = (TOOLS.parent / "PK-5.txt").read_text().splitlines()
EVIDENCE = {row["step"]: row for row in map(json.loads, (line for line in ROWS if line.startswith("{")))}
ORIGIN = EVIDENCE["signin"]["origin"]


class BrowserVerdictTest(unittest.TestCase):
    def test_signin_requires_browser_rp_id_error(self):
        for messages, body, expected in (
            (EVIDENCE["signin"]["browser_console"], "Use Passkey", True),
            ([], "Use Passkey", False),
            (["NotAllowedError: operation timed out"], "Use Passkey", False),
            (["SecurityError: unrelated browser error"], "Use Passkey", False),
            ([], "login failed", False),
        ):
            with self.subTest(messages=messages, body=body):
                browser = Mock(current_url=ORIGIN + "/ui/login/begin")
                browser.find_element.return_value.text = body
                browser.get_log.return_value = [{"message": m} for m in messages]
                with (
                    patch.multiple(wa, driver=Mock(return_value=browser),
                                   wait_for=Mock(), click_text=Mock(return_value=True),
                                   add_authenticator=Mock(), read_secret=Mock(return_value="[]"),
                                   write_secret=Mock(), creds_to_json=Mock(return_value=[]),
                                   page=Mock(return_value={"url": browser.current_url, "text": body}),
                                   shot=Mock(), out=Mock()),
                    patch.object(wa, "time", Mock(time=Mock(side_effect=[0, 0, 26]))),
                ):
                    self.assertEqual(wa.signin(ORIGIN, "owner", "test.cred", "refused"), expected)

    def test_enrol_requires_403_on_add_passkey_and_zero_credentials(self):
        recorded = EVIDENCE["passkey_created"]["browser_console"]
        for messages, credentials, expected in (
            (recorded, [], True),
            ([], [], False),
            ([recorded[0].replace("/ui/reset/add_passkey", "/ui/reset")], [], False),
            ([recorded[0].replace("403 (Forbidden)", "500 (Internal Server Error)")], [], False),
            (recorded, [object()], False),
        ):
            with self.subTest(messages=messages, credentials=len(credentials)):
                browser = Mock()
                browser.get_log.return_value = [{"message": m} for m in messages]
                browser.get_credentials.return_value = credentials
                with (
                    patch.multiple(wa, driver=Mock(return_value=browser),
                                   wait_for=Mock(side_effect=[True, RuntimeError("no label")]),
                                   add_authenticator=Mock(), shot=Mock(), out=Mock(),
                                   page=Mock(return_value={"text": "Updating Credentials"})),
                    patch("builtins.open", mock_open(read_data="test-reset-token")),
                ):
                    self.assertEqual(wa.enrol(ORIGIN, "owner", "test.cred", "refused"), expected)


class ShellVerdictTest(unittest.TestCase):
    def test_unexpected_driver_outcomes_fail_pk5_and_keep_the_log(self):
        for command in ("signin", "enrol"):
            with self.subTest(command=command), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                for name in ("lib.sh", "pk3.sh"):
                    (root / name).write_text((TOOLS / name).read_text().replace("/root/aklab", tmp))
                (root / "netns.sh").write_text("exit 0\n")
                result = subprocess.run(
                    ["bash", "-c", """
fail_step=$2
ip() {
    case "$*" in
        *"$fail_step"*refused) echo 'unexpected browser outcome' >&2; return 17 ;;
    esac
}
kanidm() { echo 'use-reset-token test-reset-token'; echo 'expire at: test'; }
python3() { return 0; }
source "$1/pk3.sh"
""", "test-pk5", tmp, command],
                    capture_output=True, text=True, check=False,
                )
                log = (root / "run-2" / "PK-5.txt").read_text()
                self.assertIn("unexpected browser outcome", log)
                self.assertIn("(exit 17)", log)
                self.assertEqual(result.returncode, 17)
                self.assertFalse((root / "run-2" / "PK-6.txt").exists())


if __name__ == "__main__":
    unittest.main()
