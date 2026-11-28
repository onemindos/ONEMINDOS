# SPDX-License-Identifier: Apache-2.0
"""BAK-02 (#163): the app the backup and restore drills install must load in the gateway's own catalog.

test/backup-wire/backup-probe is a test fixture, not a Market app, so validate-apps never reads it. When the
app schema gained required fields (age_rating in #918, licenceClass in #867) the fixture fell behind: the
gateway skipped it, POST /v1/actions answered 404 "unknown app", and both VM drills stopped before any backup
ran (restore-drill run 45729613454). This test loads the fixture the way the box does, with the image's schema,
so a schema change that breaks it fails here (ci-apps runs on every sdk/schema change) instead of in a
three-hour VM run.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "core"))
from onemind_core.catalog import Catalog  # noqa: E402

SCHEMA = REPO / "sdk" / "schema" / "onemind.app.schema.json"
# Every app a VM drill copies into /opt/onemind/apps and installs through app.install.
FIXTURES = [REPO / "test" / "backup-wire" / "backup-probe"]


class DrillFixtureAppTests(unittest.TestCase):
    def test_every_drill_fixture_loads_in_the_gateway_catalog(self):
        for fixture in FIXTURES:
            with self.subTest(app=fixture.name), tempfile.TemporaryDirectory() as tmp:
                # The drills copy the folder in under its own name, as the box's apps directory holds it.
                shutil.copytree(fixture, Path(tmp) / fixture.name)
                catalog = Catalog(Path(tmp), SCHEMA)
                apps = catalog.load()
                self.assertEqual(catalog.errors, {}, f"{fixture.name} is skipped by the gateway catalog")
                self.assertIn(fixture.name, apps)


if __name__ == "__main__":
    unittest.main()
