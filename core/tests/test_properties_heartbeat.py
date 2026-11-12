# SPDX-License-Identifier: Apache-2.0
"""Property tests: heartbeat ingest on the hub (contract §2, onemind_core/nodes.py).

Any NATS client that reaches the hub can publish on onemind.node.<id>.status, so ingest is where
untrusted heartbeats are parsed. For any sequence of (subject, payload) pairs Hypothesis builds:

- a heartbeat is kept only when the subject is exactly onemind.node.<id>.status with a valid id,
  the payload is at most 64 KiB of JSON, an object, schema onemind.node.status/v1, and its node_id
  equals the subject's <id>: a node cannot write another node's entry, and wildcard or extra
  subject tokens never match;
- the registry then holds, per node, the last heartbeat it kept, and nothing else;
- a kept heartbeat never carries the privacy-forbidden keys (serials, MACs, IPs, user names), and
  status and last_seen always come from the hub's clock, never from the sender;
- the node id rule is the same one onemindd validates (internal/heartbeat nodeIDRe), so a node the
  agent accepts is never silently dropped by the hub, and the reverse.

The Go side of the same subject has native fuzz targets: internal/heartbeat/fuzz_test.go.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from hypothesis import event, given
from hypothesis import strategies as st

from onemind_core.ledger import iso
from onemind_core.nodes import FORBIDDEN_KEYS, HEARTBEAT_SCHEMA, MAX_HEARTBEAT_BYTES, NodeRegistry
from props import budget, json_values

GO_HEARTBEAT = Path(__file__).resolve().parents[2] / "internal" / "heartbeat" / "heartbeat.go"
VALID_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")  # contract §2 / §12.9: one NATS token

valid_ids = st.from_regex(VALID_ID, fullmatch=True)
any_ids = valid_ids | st.text(max_size=70) | st.sampled_from(["*", ">", "a.b", "a b", "", "x" * 65, "node\t1", "nodé"])
# NATS subjects never carry whitespace (the protocol line is whitespace-separated), so the
# generated subjects do not either; the id strategies above still try whitespace inside a token.
tokens = st.text(alphabet=st.characters(codec="utf-8", exclude_characters=" \t\r\n."), min_size=1, max_size=12)


@st.composite
def subjects(draw, node_id: str):
    shape = draw(st.sampled_from(["exact"] * 6 + ["wildcard", "extra", "missing", "case", "other"]))
    if shape == "exact":
        return f"onemind.node.{node_id}.status"
    if shape == "wildcard":
        return draw(st.sampled_from(["onemind.node.*.status", "onemind.node.>", "onemind.>", ">", "onemind.node.*.*"]))
    if shape == "extra":
        return f"onemind.node.{node_id}.status.{draw(tokens)}"
    if shape == "missing":
        return f"onemind.node.{node_id}"
    if shape == "case":
        return f"OneMind.Node.{node_id}.Status"
    return ".".join(draw(st.lists(tokens, min_size=1, max_size=5)))


@st.composite
def payloads(draw, node_id: str):
    hb: dict = {}
    if draw(st.integers(0, 9)):
        hb["schema"] = HEARTBEAT_SCHEMA if draw(st.integers(0, 5)) else draw(st.text(max_size=20))
    if draw(st.integers(0, 9)):
        hb["node_id"] = node_id if draw(st.integers(0, 4)) else draw(any_ids)
    for key in draw(st.lists(st.sampled_from(sorted(FORBIDDEN_KEYS | {"status", "last_seen"})), max_size=3)):
        hb[key] = draw(json_values)
    hb.update(draw(st.dictionaries(st.sampled_from(["hostname", "role", "board", "cpus", "k3s", "rauc"]), json_values, max_size=3)))
    form = draw(st.sampled_from(["object"] * 7 + ["not-object", "not-json", "huge"]))
    if form == "not-object":
        return json.dumps(draw(st.lists(json_values, max_size=2) | json_values)).encode()
    if form == "not-json":
        return draw(st.binary(max_size=40))
    if form == "huge":
        hb["padding"] = "x" * MAX_HEARTBEAT_BYTES
    return json.dumps(hb, ensure_ascii=draw(st.booleans())).encode()


@st.composite
def messages(draw):
    node_id = draw(st.sampled_from(["node-a", "node-b", "node-c"]) if draw(st.integers(0, 2)) else any_ids)
    return draw(subjects(node_id)), draw(payloads(node_id))


def expected(subject: str, data: bytes) -> dict | None:
    """The reference: what ingest must keep for this message, or None."""
    parts = subject.split(".")
    if len(parts) != 4 or parts[:2] != ["onemind", "node"] or parts[3] != "status":
        return None
    if not VALID_ID.fullmatch(parts[2]) or len(data) > MAX_HEARTBEAT_BYTES:
        return None
    try:
        hb = json.loads(data)
    except ValueError:
        return None
    if not isinstance(hb, dict) or hb.get("schema") != HEARTBEAT_SCHEMA or hb.get("node_id") != parts[2]:
        return None
    return {k: v for k, v in hb.items() if k not in FORBIDDEN_KEYS | {"status", "last_seen"}}


@budget(100)
@given(msgs=st.lists(messages(), min_size=1, max_size=12))
def test_ingest_keeps_exactly_the_valid_heartbeats(msgs):
    now = [datetime(2026, 11, 12, 9, 0, tzinfo=UTC)]
    reg = NodeRegistry(lambda: now[0])
    model: dict[str, tuple[dict, datetime]] = {}
    for subject, data in msgs:
        now[0] += timedelta(seconds=7)
        want = expected(subject, data)
        assert reg.ingest(subject, data) is (want is not None), (subject, data[:200])
        if want is not None:
            model[want["node_id"]] = (want, now[0])
    event(f"nodes kept: {min(len(model), 3)}{'+' if len(model) > 3 else ''}")
    now[0] += timedelta(seconds=40)
    listed = reg.list()
    assert [n["node_id"] for n in listed] == sorted(model)
    for node in listed:
        hb, seen = model[node["node_id"]]
        assert not FORBIDDEN_KEYS & node.keys()
        assert node["last_seen"] == iso(seen)
        assert node["status"] == ("online" if (now[0] - seen).total_seconds() <= 30 else
                                  "stale" if (now[0] - seen).total_seconds() <= 120 else "offline")
        assert {k: v for k, v in node.items() if k not in ("status", "last_seen")} == hb


def go_node_id_pattern() -> re.Pattern[str]:
    m = re.search(r"nodeIDRe\s*=\s*regexp\.MustCompile\(`\^(.+)\$`\)", GO_HEARTBEAT.read_text())
    assert m, "internal/heartbeat/heartbeat.go no longer defines nodeIDRe as ^...$; update this test"
    return re.compile(m.group(1))


GO_ID = go_node_id_pattern()


@budget(200)
@given(node_id=any_ids)
def test_hub_and_agent_accept_the_same_node_ids(node_id):
    """Go's RE2 and Python's re agree on this character class; fullmatch = RE2's ^...$ (no
    trailing-newline match)."""
    hub = NodeRegistry(lambda: datetime(2026, 11, 12, tzinfo=UTC)).ingest(
        f"onemind.node.{node_id}.status",
        json.dumps({"schema": HEARTBEAT_SCHEMA, "node_id": node_id}).encode(),
    )
    assert hub == (GO_ID.fullmatch(node_id) is not None), node_id
