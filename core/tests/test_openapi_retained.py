# SPDX-License-Identifier: Apache-2.0
"""Export can retain isolated state when cleanup is not authorized."""
import json
from onemind_core.openapi import main


def test_retained_export_contains_real_settings_schema(tmp_path):
    out = tmp_path / "api.json"
    state = tmp_path / "export-state"
    assert main(["--out", str(out), "--state-dir", str(state)]) == 0
    assert (state / "export.db").is_file()
    spec = json.loads(out.read_text())
    assert "put" in spec["paths"]["/v1/onboarding/settings"]
    assert main(["--check", str(out), "--state-dir", str(state)]) == 0
    assert (state / "export.db").is_file()
