# SPDX-License-Identifier: Apache-2.0
"""The hub's persistent node history, from real heartbeat ingestion through the gateway."""

import json
from dataclasses import replace
from datetime import timedelta
from time import perf_counter

from fastapi.testclient import TestClient

from conftest import OWNER
from onemind_core.app import create_app
from onemind_core.ledger import iso

RETENTION_S = 30 * 86400


def test_gateway_restart_and_retention(settings, clock, executor):
    params = {"node_id": "node-1", "metric": "cpu_pct"}
    at = clock()
    with TestClient(create_app(settings, clock=clock, executor=executor)) as c:
        def heartbeat(cpu):
            hb = {"schema": "onemind.node.status/v1", "node_id": "node-1", "metrics": {"cpu_pct": cpu}}
            assert c.app.state.registry.ingest("onemind.node.node-1.status", json.dumps(hb).encode())
            c.app.state.monitoring.tick()

        heartbeat(19.5)
        clock.advance(60)
        heartbeat(22.5)
        clock.advance(300)
        heartbeat(37.5)

        prom = c.get("/v1/metrics", headers=OWNER).text
        assert 'onemind_node_cpu_percent{node="node-1"} 37.5' in prom
        assert c.get("/v1/series", params=params).status_code == 401
        assert c.get("/v1/series", params={**params, "metric": "hostname"}, headers=OWNER).status_code == 422
        assert c.get("/v1/series", params={**params, "points": 0}, headers=OWNER).status_code == 422
        assert c.get("/v1/series", params={**params, "window_s": RETENTION_S + 1}, headers=OWNER).status_code == 422
        # A different producer's number with the same source id is outside this reader's scope.
        c.app.state.monitoring.series.record("connector", clock(), [(clock(), "node-1", "cpu_pct", 99.75)])

    with TestClient(create_app(settings, clock=clock, executor=executor)) as c:
        def query(**changes):
            r = c.get("/v1/series", params={**params, "window_s": 3600, "points": 60, **changes}, headers=OWNER)
            assert r.status_code == 200, r.text
            return r.json()

        assert query() == [{"at": iso(at), "value": 19.5},
                           {"at": iso(at + timedelta(seconds=60)), "value": 22.5},
                           {"at": iso(clock()), "value": 37.5}]
        assert query(points=1) == [{"at": iso(at), "value": 26.5}]
        assert query(metric="temp_c") == []  # no reading was reported
        assert query(node_id="another-node") == []
        clock.advance(RETENTION_S)
        assert query(window_s=RETENTION_S) == [{"at": iso(at + timedelta(seconds=360)), "value": 37.5}]
        clock.advance(1)
        c.app.state.monitoring.tick()  # expire disk rows even while the restarted registry is empty
        assert query(window_s=RETENTION_S) == []
        with c.app.state.gateway.db.engine.connect() as conn:
            assert conn.exec_driver_sql("SELECT COUNT(*) FROM series_hours").scalar_one() == 0


def test_ten_nodes_thirty_days_fits_and_queries_fast(tmp_path, settings, clock, executor):
    db_path = tmp_path / "capacity.db"
    settings = replace(settings, db_url=f"sqlite:///{db_path}")
    nodes = [f"node-{i:059}" for i in range(10)]  # the longest permitted node identifier
    with TestClient(create_app(settings, clock=clock, executor=executor)) as c:
        store = c.app.state.monitoring.series

        def readings(hour, minutes):
            for minute in minutes:
                at = hour + timedelta(minutes=minute)
                for j, node in enumerate(nodes):
                    gauges = {"cpu_pct": 17.123 + minute, "load1": 0.31 + j, "temp_c": 50.23,
                              "mem_used_mb": 2048.5 + minute, "mem_total_mb": 8192.0,
                              "disk_free_gb": 32.345, "disk_total_gb": 256.123}
                    for metric, value in gauges.items():
                        yield at, node, metric, value

        for _ in range(30 * 24):
            hour = clock()
            clock.advance(3600)
            # Grow each row after insertion, as successive monitoring ticks do on the hub.
            store.record("node", clock(), readings(hour, range(1)))
            store.record("node", clock(), readings(hour, range(1, 60)))
        with c.app.state.gateway.db.engine.connect() as conn:
            assert conn.exec_driver_sql("SELECT COUNT(*) FROM series_hours").scalar_one() == 30 * 24 * 10 * 7
        size = sum(f.stat().st_size for f in tmp_path.glob("capacity.db*"))  # include the live WAL
        started = perf_counter()
        r = c.get("/v1/series", headers=OWNER, params={
            "node_id": nodes[-1], "metric": "cpu_pct", "window_s": RETENTION_S, "points": 60})
        elapsed = perf_counter() - started
        assert r.status_code == 200 and len(r.json()) == 60
        assert all(17.123 < point["value"] < 76.123 for point in r.json())
        assert size < 50_000_000, size
        assert elapsed < 0.2, elapsed
        print(f"Ten nodes × 30 days: {size:,} bytes, 60-point gateway query {elapsed * 1000:.1f} ms")
