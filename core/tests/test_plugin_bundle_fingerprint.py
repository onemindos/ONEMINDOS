# SPDX-License-Identifier: Apache-2.0
"""Owner-approved install plans include plugin settings and UI content."""
from pathlib import Path

import pytest
import yaml

from conftest import OWNER, ScriptedExecutor, make_client
from onemind_core.catalog import Catalog
from onemind_core.lifecycle import bundle_sha256
from test_plugin_workload import plugin_settings  # noqa: F401
from test_plugin_credentials import approve, request


def settings_schema(settings):
    root = Path(settings.apps_dir) / "uptime-kuma"
    path = root / "onemind.app.yaml"
    doc = yaml.safe_load(path.read_text())
    doc["spec"]["extensions"]["settings"] = {"schema": "settings.schema.json"}
    path.write_text(yaml.safe_dump(doc))
    schema = root / "settings.schema.json"
    schema.write_text('{"type":"object","additionalProperties":false}')
    return root, schema


def test_changed_settings_schema_invalidates_pending_approved_plan(plugin_settings, clock):
    _, schema = settings_schema(plugin_settings)
    executor = ScriptedExecutor()
    with make_client(plugin_settings, clock, executor) as client:
        action_id = request(client, clock, "app.install")
        before = client.get(f"/v1/actions/{action_id}", headers=OWNER).json()
        schema.write_text('{"type":"object","properties":{"new":{"type":"string"}}}')
        r = client.post(f"/v1/actions/{action_id}/approve", headers=OWNER,
                        json={"plan_sha256": before["plan_sha256"]})
        assert r.status_code == 409
        assert executor.calls == []


def test_ui_and_root_icon_changes_affect_bundle_digest(plugin_settings):
    root, _ = settings_schema(plugin_settings)
    app = Catalog(plugin_settings.apps_dir).load()["uptime-kuma"]
    original = bundle_sha256(app)
    assert original is not None
    (root / "ui").mkdir()
    js = root / "ui" / "main.js"
    js.write_text("console.log('hello')")
    with_ui = bundle_sha256(app)
    assert with_ui != original
    js.write_text("console.log('changed')")
    assert bundle_sha256(app) != with_ui
    before_icon = bundle_sha256(app)
    (root / app.manifest["metadata"]["icon"]).write_text("changed icon")
    assert bundle_sha256(app) != before_icon


@pytest.mark.parametrize("kind", ["missing", "symlink", "escape", "too-large"])
def test_unsafe_settings_file_never_gets_valid_bundle_digest(plugin_settings, tmp_path, kind):
    root, schema = settings_schema(plugin_settings)
    if kind == "missing":
        schema.unlink()
    elif kind == "symlink":
        schema.unlink(); schema.symlink_to(root / "onemind.app.yaml")
    elif kind == "too-large":
        schema.write_bytes(b"x" * (4 * 1024**2 + 1))
    else:
        path = root / "onemind.app.yaml"
        doc = yaml.safe_load(path.read_text()); doc["spec"]["extensions"]["settings"]["schema"] = "../outside.json"
        path.write_text(yaml.safe_dump(doc))
    app = Catalog(plugin_settings.apps_dir).load()["uptime-kuma"]
    assert bundle_sha256(app) is None
