# SPDX-License-Identifier: Apache-2.0
"""One app identifier domain for every client: com.onemindos.* (founder decision, 2026-11-21).

Store identifiers cannot change after the first upload, so this fails if a client leaves the
domain the founder owns (onemindos.com)."""
import json, os, re, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load = lambda *p: json.load(open(os.path.join(ROOT, *p)))
DOMAIN = re.compile(r"^com\.onemindos\.[a-z]+$")


class AppIdentifiers(unittest.TestCase):
    def test_mobile(self):
        expo = load("mobile", "app.json")["expo"]
        self.assertEqual(expo["ios"]["bundleIdentifier"], "com.onemindos.mobile")
        self.assertEqual(expo["android"]["package"], "com.onemindos.mobile")

    def test_desktop(self):
        ident = load("desktop", "src-tauri", "tauri.conf.json")["identifier"]
        self.assertEqual(ident, "com.onemindos.desktop")
        self.assertRegex(ident, DOMAIN)

    def test_keychain_service_follows_identifier(self):
        src = open(os.path.join(ROOT, "desktop", "src-tauri", "src", "store.rs")).read()
        self.assertIn('KEYCHAIN_SERVICE: &str = "com.onemindos.desktop"', src)

    def test_push_docs_use_the_mobile_id(self):
        doc = open(os.path.join(ROOT, "mobile", "docs", "push.md")).read()
        self.assertNotIn("os.onemind.mobile", doc)
        self.assertIn("apns-topic: com.onemindos.mobile", doc)
