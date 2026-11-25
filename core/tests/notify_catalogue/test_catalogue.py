# SPDX-License-Identifier: Apache-2.0
"""The alert catalogue is wired to the published event names and the CI lint command."""

import subprocess
import sys
from pathlib import Path

import pytest

from conftest import ADULT, OWNER

ROOT = Path(__file__).resolve().parents[3]
CATALOGUE = ROOT / "core/onemind_core/notify/catalogue.py"


def test_disk_warnings_escalate_and_resolve_per_disk(client):
    events = client.app.state.events
    data = {"node_id": "node1", "disk_key": "disk1", "disk": "/dev/vdb", "verdict": "warning"}
    events.publish_event("storage", "disk.warning", data)
    events.publish_event("storage", "disk.warning", {**data, "disk_key": "disk2", "disk": "/dev/vdc"})
    events.publish_event("storage", "disk.failing", {**data, "verdict": "critical"})
    alerts = client.get("/v1/alerts", headers=OWNER, params={"state": "open"}).json()
    by_key = {a["dedupe_key"]: a for a in alerts}
    first = by_key["storage:node1:disk:disk1"]
    assert (first["severity"], first["occurrences"], first["link"]) == ("critical", 2, "/storage")
    assert "/dev/vdb" in first["body"]
    assert first["learn_more_url"] and first["fix"] is None
    assert by_key["storage:node1:disk:disk2"]["severity"] == "warning"
    events.publish_event("storage", "disk.ok", {**data, "verdict": "ok"})
    remaining = client.get("/v1/alerts", headers=OWNER, params={"state": "open"}).json()
    assert [a["dedupe_key"] for a in remaining] == ["storage:node1:disk:disk2"]


def test_breaker_security_join_and_override_reach_only_owners(client):
    publish = client.app.state.events.publish_event
    publish("automation", "breaker.opened", {"rule_id": "rule1", "name": "Hall lights", "failures": 3})
    publish("security", "owner_override.enabled", {"setting": "ONEMIND_ALLOW_OWNER_OVERRIDE"})
    publish("node", "joined", {"node_id": "node2", "role": "worker", "mesh": True})
    publish("app", "owner_override", {"app_id": "example", "reason": "private audit reason", "tone": "red"})
    alerts = client.get("/v1/alerts", headers=OWNER, params={"state": "open"}).json()
    breaker = next(a for a in alerts if a["type"] == "automation.breaker.opened")
    assert breaker["subject"]["rule_id"] == "rule1" and breaker["link"] == "/automation"
    assert breaker["fix"] is None and breaker["learn_more_url"]
    items = client.get("/v1/notifications", headers=OWNER).json()
    assert {(n["topic"], n["severity"], n["link"]) for n in items} == {
        ("automation", "warning", "/automation"), ("security", "warning", "/activity"),
        ("nodes", "info", "/nodes"), ("security", "critical", "/activity"),
    }
    assert "private audit reason" not in str(items)
    assert client.get("/v1/notifications", headers=ADULT).json() == []
    client.app.state.audit.append("automation.rule.enabled", None, None, {"rule_id": "rule1"})
    active = client.get("/v1/alerts", headers=OWNER, params={"state": "open"}).json()
    assert all(a["type"] != "automation.breaker.opened" for a in active)


@pytest.mark.parametrize("help_link", [None, "", "not a link"])
def test_release_lint_fails_for_alert_without_fix_or_help(tmp_path, help_link):
    # Run the same standalone catalogue check as scripts/lint.sh, with a future broken entry.
    cmd = [sys.executable, "-I"]
    assert subprocess.run([*cmd, str(CATALOGUE)], check=False).returncode == 0
    broken = tmp_path / "catalogue.py"
    entry = f'Spec("test.no_remedy", "open", "nodes", link="/nodes", learn_more={help_link!r})'
    broken.write_text(CATALOGUE.read_text().replace("_SPECS = [", f"_SPECS = [{entry},", 1))
    result = subprocess.run([*cmd, str(broken)], capture_output=True, text=True, check=False)
    assert result.returncode != 0
    assert "test.no_remedy" in result.stdout + result.stderr
