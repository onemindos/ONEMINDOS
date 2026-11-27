#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CHECK = Path(__file__).with_name("check-android-sdk-deps.py")
CLASSPATH = "releaseRuntimeClasspath - Runtime classpath of '/release'.\n"
MANIFEST = '<manifest xmlns:android="http://schemas.android.com/apk/res/android"><application>{}</application></manifest>'


class AndroidReleaseSdkCheck(unittest.TestCase):
    def check(self, dependency: str, manifest_entry: str = "") -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as directory:
            dependencies = Path(directory, "dependencies.txt")
            dependencies.write_text(CLASSPATH + dependency)
            manifest = Path(directory, "manifest.xml")
            manifest.write_text(MANIFEST.format(manifest_entry))
            return subprocess.run(
                [sys.executable, "-I", str(CHECK), str(dependencies), str(manifest)],
                capture_output=True, text=True, check=False,
            )

    def test_accepts_open_source_zxing(self):
        self.assertEqual(self.check("+--- com.google.zxing:core:3.5.4").returncode, 0)

    def test_rejects_each_google_sdk_group_and_the_credentials_bridge(self):
        for dependency in (
            "com.google.android.gms:play-services-base:18.5.0",
            "com.google.firebase:firebase-messaging:25.0.1",
            "com.google.mlkit:barcode-scanning:17.3.0",
            "androidx.credentials:credentials-play-services-auth:1.5.0",
        ):
            with self.subTest(dependency=dependency):
                result = self.check("+--- " + dependency)
                self.assertEqual(result.returncode, 1)
                self.assertIn(dependency, result.stdout)

    def test_rejects_fcm_components_even_with_a_clean_classpath(self):
        service = '<service android:name="expo.modules.notifications.service.ExpoFirebaseMessagingService" />'
        result = self.check("", service)
        self.assertEqual(result.returncode, 1)
        self.assertIn("ExpoFirebaseMessagingService", result.stdout)


if __name__ == "__main__":
    unittest.main()
