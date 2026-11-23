# SPDX-License-Identifier: Apache-2.0
"""Quality tiers (#174): the catalog shows the tier and the checks behind it, derived from the gate's evidence."""

import json
from datetime import timedelta

from conftest import GUEST, write_scan
from onemind_core.scan import QUALITY_CHECKS, read_scan


def evidence(**falsify):
    ev = {lvl: {n: True for n in names} for lvl, names in QUALITY_CHECKS.items()}
    for key in falsify:
        for lvl, names in QUALITY_CHECKS.items():
            if key in names:
                ev[lvl][key] = False
    return ev


def put(app_dir, now, quality, result="pass"):
    write_scan(app_dir, now)
    doc = json.loads((app_dir / "scan.json").read_text())
    doc["result"] = result
    if quality is not None:
        doc["quality"] = quality
    (app_dir / "scan.json").write_text(json.dumps(doc))


def catalog(client):
    return {a["id"]: a for a in client.get("/v1/apps", headers=GUEST).json()}


def test_scan_without_quality_is_not_rated(client, settings):
    assert catalog(client)["whoami"]["scan"]["quality"] is None


def test_gold_when_every_check_holds(client, clock, settings):
    put(settings.apps_dir / "whoami", clock.now - timedelta(hours=1), {"tier": "gold", "evidence": evidence()})
    q = catalog(client)["whoami"]["scan"]["quality"]
    assert q["tier"] == "gold"
    assert q["evidence"]["bronze"]["gate_pass"] is True
    assert set(q["evidence"]["gold"]) == set(QUALITY_CHECKS["gold"])


def test_tier_is_derived_from_evidence_not_from_the_written_tier(client, clock, settings):
    # The record says gold, but a Gold check is false: the gateway shows silver.
    put(settings.apps_dir / "whoami", clock.now - timedelta(hours=1),
        {"tier": "gold", "evidence": evidence(images_signed=True)})
    assert catalog(client)["whoami"]["scan"]["quality"]["tier"] == "silver"
    # A failed Bronze check gives none, whatever higher checks say.
    put(settings.apps_dir / "whoami", clock.now - timedelta(hours=1),
        {"tier": "gold", "evidence": evidence(upstream_alive=True)})
    assert catalog(client)["whoami"]["scan"]["quality"]["tier"] == "none"


def test_failed_scan_has_no_tier(client, clock, settings):
    put(settings.apps_dir / "whoami", clock.now - timedelta(hours=1), {"tier": "gold", "evidence": evidence()},
        result="fail")
    assert catalog(client)["whoami"]["scan"]["quality"]["tier"] == "none"


def test_malformed_quality_is_not_rated_or_none(client, clock, settings):
    app_dir = settings.apps_dir / "whoami"
    for bad in ("gold", {"tier": "gold"}, {"tier": "gold", "evidence": "yes"}, [1]):
        put(app_dir, clock.now - timedelta(hours=1), bad)
        assert read_scan(app_dir).quality is None
    # Truthy non-booleans do not count as checks that hold.
    put(app_dir, clock.now - timedelta(hours=1),
        {"tier": "gold", "evidence": {lvl: {n: 1 for n in names} for lvl, names in QUALITY_CHECKS.items()}})
    assert read_scan(app_dir).quality["tier"] == "none"
