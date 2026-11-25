# SPDX-License-Identifier: Apache-2.0
"""Firewall view (P-09 part 1): a real gateway reads a real host service over a real Unix socket, in the
shape internal/firewall emits for the shipped host.nft. The rules are explained in plain words and the
audience of every rule (this box, mesh, pods, LAN, any address) is worked out, never guessed."""

from __future__ import annotations

import copy
import json
import os
import socketserver
import tempfile
import threading
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import ADULT, AGENT, OWNER
from onemind_core.app import create_app
from onemind_core.hostfw import parse_view
from onemind_core.netconf import NetSettings


def R(verdict="accept", **kw):
    return {"verdict": verdict, "understood": True, **kw}


HOST = {
    "family": "inet", "name": "onemind_host",
    "sets": [{"name": "lan4", "elements": ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16", "100.64.0.0/10"]},
             {"name": "lan6", "elements": ["fc00::/7", "fe80::/10"]}],
    "chains": [
        {"name": "input", "hook": "input", "policy": "drop", "rules": [
            R(ct=["established", "related"]),
            R("drop", ct=["invalid"]),
            R(iif="lo"),
            R(iif="tailscale0", proto="tcp", dport=["6443", "10250"]),
            R(iif="flannel*", proto="udp", dport=["8472", "51820", "51821"]),
            R(iif="cni0", proto="tcp", dport=["6443"]),
            R(iif="tailscale0", proto="tcp", dport=["443", "8443", "7422"]),
            R(proto="icmp"),
            R(proto="ipv6-icmp"),
            R(proto="udp", sport=["67"], dport=["68"]),
            R("jump", target="lan", saddr="@lan4"),
            R("jump", target="lan", saddr="@lan6"),
        ]},
        {"name": "lan", "rules": [R("jump", target="setup"), R("jump", target="samba"),
                                  R(proto="tcp", dport=["443", "8443", "8444", "7443"]), R(proto="udp", dport=["5353", "3478", "41641"])]},
        {"name": "setup", "rules": []},
        {"name": "samba", "rules": [R(proto="tcp", dport=["445"])]},
    ],
}
GOOD = {"schema": "onemind.firewall/v1", "at": "2026-11-25T12:00:00Z",
        "tables": [{"family": "inet", "name": "onemind_host", "chains": 4, "rules": 17},
                   {"family": "ip", "name": "kube-proxy", "chains": 9, "rules": 40}],
        "host": HOST}


def good(**over):
    d = copy.deepcopy(GOOD)
    d.update(over)
    return d


class _Handler(socketserver.StreamRequestHandler):
    def handle(self):
        line = self.rfile.readline().decode()
        while self.rfile.readline().strip():
            pass
        status, body = self.server.answer if line.startswith("GET /v1/firewall ") else (404, {})
        raw = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.wfile.write(f"HTTP/1.1 {status} X\r\nContent-Type: application/json\r\nContent-Length: {len(raw)}\r\nConnection: close\r\n\r\n".encode() + raw)


class _Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    answer: tuple[int, object] = (200, GOOD)


@pytest.fixture
def host():
    d = tempfile.mkdtemp(prefix="fw")  # short: AF_UNIX paths are limited to about 100 bytes
    sock = os.path.join(d, "h.sock")
    srv = _Server(sock, _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    srv.path = sock
    yield srv
    srv.shutdown()
    srv.server_close()


def box(settings, clock, executor, sock: str):
    s = replace(settings, sections={"net": NetSettings(host_socket=Path(sock))})
    return TestClient(create_app(s, clock=clock, executor=executor))


def rules(v, chain=None):
    return [r for r in v.rules if chain in (None, r.chain)]


def test_owner_reads_the_firewall_through_the_gateway(settings, clock, executor, host):
    with box(settings, clock, executor, host.path) as c:
        r = c.get("/v1/network/firewall", headers=OWNER)
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["available"] and b["exposure"] == "lan_and_mesh_only" and b["default_action"] == "drop"
        assert b["open_to_anywhere"] == [] and b["editable"] is False and b["dropped"] == 0
        assert "Nothing is open to the internet" in b["headline"]
        assert [t["name"] for t in b["other_tables"]] == ["kube-proxy"]
        assert [ch["name"] for ch in b["chains"]] == ["input", "lan", "setup", "samba"]


def test_the_shipped_rules_are_each_explained_for_the_right_audience():
    v = parse_view(GOOD)
    inp = {r.position: r for r in rules(v, "input")}
    assert (inp[1].kind, inp[1].audience) == ("state", "any_network") and "Replies" in inp[1].summary
    assert inp[2].kind == "block" and "belong to no real connection" in inp[2].summary
    assert (inp[3].kind, inp[3].audience) == ("internal", "this_machine") and inp[3].summary == "The box can talk to itself."
    assert (inp[4].kind, inp[4].audience) == ("open_port", "mesh") and "TCP 6443 (the cluster API, k3s)" in inp[4].summary
    assert inp[5].audience == "pod_network" and inp[6].audience == "pod_network"
    assert inp[7].audience == "mesh" and "other machines on your onemind mesh" in inp[7].summary.lower()
    assert inp[8].kind == inp[9].kind == "basics" and inp[10].kind == "basics" and "DHCP" in inp[10].summary
    assert inp[11].kind == "hand_off" and inp[11].audience == "lan" and "'lan'" in inp[11].summary
    lan = {r.position: r for r in rules(v, "lan")}
    assert lan[3].audience == "lan" and lan[3].kind == "open_port" and "devices on your home network (lan) can reach" in lan[3].summary.lower()
    assert lan[3].ports == ["443", "8443", "8444", "7443"] and "the rescue console" in lan[3].summary
    assert lan[4].audience == "lan" and "mDNS" in lan[4].summary
    assert rules(v, "samba")[0].audience == "lan" and "file sharing, Samba" in rules(v, "samba")[0].summary
    chain = {c.name: c for c in v.chains}
    assert chain["lan"].audience == "lan" and chain["samba"].audience == "lan" and chain["setup"].audience == "lan"
    assert chain["input"].base and chain["input"].policy == "drop" and chain["input"].audience is None
    assert v.sets[0].name == "lan4" and "10.0.0.0/8" in v.sets[0].elements


def test_a_service_open_to_any_address_is_named_and_changes_the_headline():
    # The cloud images ship this in host.d: SSH and HTTPS from any address.
    body = good()
    body["host"]["chains"][0]["rules"].append(R(proto="tcp", dport=["22", "443"]))
    v = parse_view(body)
    assert v.exposure == "open_to_internet" and v.open_to_anywhere == ["tcp/22", "tcp/443"]
    assert "any address (the internet too" in rules(v, "input")[-1].summary.lower()
    assert "tcp/22" in v.headline and "the internet" in v.headline and "Nothing is open" not in v.headline
    # ...but a LAN-only service never counts.
    assert parse_view(GOOD).open_to_anywhere == []


def test_accept_everything_from_anywhere_is_flagged_not_hidden():
    body = good()
    body["host"]["chains"][0]["rules"].append(R())
    v = parse_view(body)
    assert v.exposure == "open_to_internet" and v.open_to_anywhere == ["everything"]
    assert rules(v, "input")[-1].summary == "Everything is allowed in, from any address."


def test_a_chain_reached_from_two_audiences_is_as_open_as_the_wider():
    body = good()
    body["host"]["chains"][0]["rules"].append(R("jump", target="lan"))  # no source condition: anyone
    v = parse_view(body)
    assert {c.name: c.audience for c in v.chains}["lan"] == "any_network"
    assert v.exposure == "open_to_internet" and "tcp/443" in v.open_to_anywhere


def test_no_firewall_table_or_a_permissive_default_is_said_plainly():
    v = parse_view(good(host=None))
    assert v.available and v.exposure == "no_firewall" and v.rules == [] and "not active" in v.headline
    body = good()
    body["host"]["chains"][0]["policy"] = "accept"
    v = parse_view(body)
    assert v.exposure == "no_firewall" and v.default_action == "accept"


def test_a_rule_the_screen_cannot_describe_says_so_and_is_never_called_safe():
    body = good()
    body["host"]["chains"][0]["rules"].append(R(understood=False))  # e.g. `tcp dport 82 limit rate 10/second accept`, from anyone
    v = parse_view(body)
    last = rules(v, "input")[-1]
    assert not last.understood and last.kind == "other" and "cannot describe" in last.summary
    assert v.open_to_anywhere == []  # it is not claimed to be open either: it is not known
    assert v.exposure == "not_fully_understood" and "Nothing is open to the internet" not in v.headline
    assert "1 rule that let traffic in use something it cannot describe" in v.headline
    # A permit the screen cannot read is only a doubt when it could be reached from outside the LAN.
    body = good()
    body["host"]["chains"][0]["rules"].append(R(iif="lo", understood=False))
    body["host"]["chains"][1]["rules"].append(R(proto="tcp", dport=["1"], understood=False))  # in the lan chain: LAN only
    body["host"]["chains"][0]["rules"].append(R("drop", understood=False))  # a block it cannot read opens nothing
    assert parse_view(body).exposure == "lan_and_mesh_only"
    # An unreadable jump from anyone into a list is never called LAN-only (the list's ports count as open to anyone).
    body = good()
    body["host"]["chains"][0]["rules"].append(R("jump", target="lan", understood=False))
    assert parse_view(body).exposure == "open_to_internet"
    body = good()
    body["host"]["chains"][0]["rules"].append(R("jump", target="nowhere", understood=False))
    assert parse_view(body).exposure == "not_fully_understood"


def test_only_replies_are_called_replies_and_a_new_connection_rule_is_an_open_port():
    # nft prints `tcp dport 22 ct state new accept` with ct state "new": it lets a stranger start a connection.
    body = good()
    body["host"]["chains"][0]["rules"].append(R(proto="tcp", dport=["22"], ct=["new"]))
    v = parse_view(body)
    last = rules(v, "input")[-1]
    assert last.kind == "open_port" and last.audience == "any_network" and "TCP 22 (remote login, SSH)" in last.summary
    assert v.exposure == "open_to_internet" and v.open_to_anywhere == ["tcp/22"] and "Nothing is open" not in v.headline
    # ct state new with no port opens everything; established,new is no better.
    for states in (["new"], ["established", "new"], ["untracked"], ["invalid"]):
        body = good()
        body["host"]["chains"][0]["rules"].append(R(ct=states))
        v = parse_view(body)
        assert rules(v, "input")[-1].kind == "other" and v.open_to_anywhere == ["everything"], states
        assert v.exposure == "open_to_internet", states
    # Replies with extra conditions are not the plain replies rule either.
    for extra in ({"proto": "tcp", "dport": ["22"]}, {"saddr": "203.0.113.0/24"}, {"iif": "eth0"}):
        body = good()
        body["host"]["chains"][0]["rules"].append(R(ct=["established", "related"], **extra))
        assert rules(parse_view(body), "input")[-1].kind != "state", extra
    # The shipped rule, in either order, is still the replies rule.
    for states in (["related", "established"], ["established"]):
        body = good()
        body["host"]["chains"][0]["rules"][0] = R(ct=states)
        assert rules(parse_view(body), "input")[0].kind == "state"


def test_everyone_written_as_a_prefix_or_an_interface_name_is_still_the_internet():
    for extra, label in (({"saddr": "0.0.0.0/0"}, "tcp/80"), ({"saddr": "::/0"}, "tcp/80"), ({"saddr": "0.0.0.0/1"}, "tcp/80"),
                         ({"iif": "eth0"}, "tcp/80 on eth0")):
        body = good()
        body["host"]["chains"][0]["rules"].append(R(proto="tcp", dport=["80"], **extra))
        v = parse_view(body)
        assert v.exposure == "open_to_internet" and v.open_to_anywhere == [label], extra
    # A source limit beats an interface name: eth0 from the LAN only is the LAN.
    body = good()
    body["host"]["chains"][0]["rules"].append(R(proto="tcp", dport=["80"], iif="eth0", saddr="@lan4"))
    v = parse_view(body)
    assert rules(v, "input")[-1].audience == "lan" and v.exposure == "lan_and_mesh_only"
    # One named public address is not "anyone".
    body = good()
    body["host"]["chains"][0]["rules"].append(R(proto="tcp", dport=["22"], saddr="203.0.113.7"))
    assert parse_view(body).exposure == "lan_and_mesh_only"
    # Everything from one connection, with no port, is named too.
    body = good()
    body["host"]["chains"][0]["rules"].append(R(iif="eth0"))
    assert parse_view(body).open_to_anywhere == ["everything on eth0"]


def test_rules_in_a_list_nothing_reaches_or_in_a_forward_chain_do_not_count_as_open():
    body = good()
    body["host"]["chains"].append({"name": "orphan", "rules": [R(proto="tcp", dport=["9999"])]})
    body["host"]["chains"].append({"name": "fwd", "hook": "forward", "policy": "accept", "rules": [R(proto="tcp", dport=["8888"])]})
    v = parse_view(body)
    assert v.exposure == "lan_and_mesh_only" and v.open_to_anywhere == []
    assert any(r.chain == "orphan" for r in v.rules)  # still shown, nothing hidden


def test_a_partial_ruleset_is_never_called_closed():
    v = parse_view(good(truncated=3))
    assert v.truncated == 3 and v.exposure == "not_fully_understood"
    assert "3 parts of the rules were left out for size" in v.headline and "Nothing is open to the internet" not in v.headline
    # A cut set may hide a public member, so a rule that names it is no longer called LAN.
    body = good(truncated=1)
    body["host"]["chains"][0]["rules"].append(R(proto="tcp", dport=["22"], saddr="@lan4"))
    assert rules(parse_view(body), "input")[-1].audience == "specific_address"
    # A host service that predates the field says nothing: zero. Garbage is refused.
    assert parse_view(GOOD).truncated == 0
    assert parse_view(good(truncated=-1)).reason == "bad_response"
    assert parse_view(good(truncated="x")).reason == "bad_response"
    # Entries the gateway itself refuses in the OneMind table also stop it saying "nothing is open".
    body = good()
    body["host"]["chains"][0]["rules"].append(R(iif="<bad>"))
    v = parse_view(body)
    assert v.dropped == 1 and v.exposure == "not_fully_understood" and "failed its checks" in v.headline
    # ...and so do chains past the gateway's own cap.
    body = good()
    body["host"]["chains"] += [{"name": f"x{i}", "rules": []} for i in range(70)]
    assert parse_view(body).exposure == "not_fully_understood"


def test_the_ping_sentence_names_the_audience_the_rule_really_has():
    v = parse_view(GOOD)
    assert "from any address" in rules(v, "input")[7].summary  # the shipped rule has no source limit
    body = good()
    body["host"]["chains"][1]["rules"].append(R(proto="icmp"))
    assert "from devices on your home network (LAN)" in rules(parse_view(body), "lan")[-1].summary
    body = good()
    body["host"]["chains"][0]["rules"].append(R(proto="icmp", saddr="@lan4"))
    assert "from any address" not in rules(parse_view(body), "input")[-1].summary


def test_the_headline_says_what_it_checked():
    assert "not checked here" in parse_view(GOOD).headline


GOLDEN = Path(__file__).resolve().parents[2] / "internal" / "firewall" / "testdata" / "host-view.golden.json"


def test_the_real_nft_output_of_the_shipped_host_nft_reads_as_closed():
    """internal/firewall's golden view is what the Go side emits for the unedited `nft -j list ruleset` of host.nft
    (nftables 1.1.3). It goes through the same checks as a live answer: every shipped rule is understood, nothing is
    open to the internet, and nothing is dropped or truncated."""
    v = parse_view(json.loads(GOLDEN.read_text()))
    assert v.available and v.dropped == 0 and v.truncated == 0
    assert all(r.understood for r in v.rules), [r.summary for r in v.rules if not r.understood]
    assert v.exposure == "lan_and_mesh_only" and v.open_to_anywhere == [] and v.default_action == "drop"
    inp = rules(v, "input")
    assert inp[0].kind == "state" and inp[1].kind == "block" and inp[2].audience == "this_machine"
    assert [r.audience for r in inp if r.kind == "hand_off"] == ["lan", "lan"]
    assert {r.audience for r in rules(v, "lan")} == {"lan"} and rules(v, "samba")[0].ports == ["445"]


@pytest.mark.parametrize("who", [ADULT, AGENT])
def test_only_the_owner_sees_the_firewall(settings, clock, executor, host, who):
    with box(settings, clock, executor, host.path) as c:
        assert c.get("/v1/network/firewall", headers=who).status_code == 403
        assert c.get("/v1/network/firewall").status_code == 401


def test_it_reads_only(settings, clock, executor, host):
    with box(settings, clock, executor, host.path) as c:
        for method in ("post", "put", "patch", "delete"):
            assert getattr(c, method)("/v1/network/firewall", headers=OWNER).status_code in (404, 405)


def test_unreachable_host_service_is_said_not_hidden(settings, clock, executor):
    with box(settings, clock, executor, "/nonexistent/host.sock") as c:
        b = c.get("/v1/network/firewall", headers=OWNER).json()
        assert b["available"] is False and b["reason"] == "host_service_unreachable" and b["rules"] == []
        assert b["exposure"] is None  # an unknown firewall is never reported as safe


def test_host_service_error_old_host_and_garbage(settings, clock, executor, host):
    with box(settings, clock, executor, host.path) as c:
        host.answer = (500, {"error": "internal"})
        assert c.get("/v1/network/firewall", headers=OWNER).json()["reason"] == "host_service_error"
        host.answer = (404, {})
        b = c.get("/v1/network/firewall", headers=OWNER).json()
        assert b["reason"] == "host_service_error" and "update the OS" in b["message"]
        host.answer = (200, b"<html>not json</html>")
        assert c.get("/v1/network/firewall", headers=OWNER).json()["reason"] == "bad_response"
        host.answer = (200, {"schema": "onemind.netview/v1"})
        assert c.get("/v1/network/firewall", headers=OWNER).json()["reason"] == "bad_response"


def test_every_field_is_rechecked_and_bad_entries_dropped():
    """H-06: nothing the host service sends reaches a screen unchecked, and one bad entry hides no other."""
    body = good()
    body["host"]["chains"][0]["rules"] = [
        R(iif="lo"),
        R(iif="<script>alert(1)</script>"),
        R(proto="tcp", dport=["70000"]),
        R(proto="tcp", dport=["9-3"]),
        R(proto="sctp"),
        R("allow-everything"),
        R(ct=["bogus"]),
        R(saddr="999.1.1.1"),
        R("jump", target="x; rm -rf /"),
        {"verdict": "accept"},  # no understood flag
        "not an object",
    ]
    v = parse_view(body)
    assert [r.position for r in rules(v, "input")] == [1] and rules(v, "input")[0].audience == "this_machine"
    assert v.dropped == 10
    body = good()
    body["host"]["sets"] = [{"name": "lan4", "elements": ["10.0.0.0/8"]}, {"name": "bad", "elements": ["not-an-ip"]}]
    body["host"]["chains"].append({"name": "evil name!", "rules": []})
    body["tables"].append({"family": "inet", "name": "<b>x</b>", "chains": 1, "rules": 1})
    v = parse_view(body)
    assert [s.name for s in v.sets] == ["lan4"] and "evil name!" not in [c.name for c in v.chains]
    assert [t.name for t in v.other_tables] == ["kube-proxy"] and v.dropped == 3


def test_ports_and_ranges_are_validated_and_scope_ids_refused():
    body = good()
    body["host"]["chains"] = body["host"]["chains"][:1]
    body["host"]["chains"][0]["rules"] = [R(proto="tcp", dport=["8000-8100"]), R(saddr="fe80::1%eth0"), R(saddr="192.0.2.0/24", proto="tcp", dport=["22"])]
    v = parse_view(body)
    assert [r.ports for r in rules(v, "input")] == [["8000-8100"], ["22"]]
    last = rules(v, "input")[-1]
    assert last.audience == "specific_address" and v.dropped == 1 and v.open_to_anywhere == ["tcp/8000-8100"]


def test_openapi_describes_the_route(client):
    spec = client.get("/openapi.json").json()
    op = spec["paths"]["/v1/network/firewall"]["get"]
    assert op["operationId"] == "network.firewall"
    assert set(spec["paths"]["/v1/network/firewall"]) == {"get"}


def test_a_named_set_that_holds_everyone_is_the_internet_not_one_address():
    for members in (["0.0.0.0/0"], ["0.0.0.0/1", "128.0.0.0/1"], ["192.168.0.0/16", "0.0.0.0/0"]):
        body = good()
        body["host"]["sets"].append({"name": "all", "elements": members})
        body["host"]["chains"][0]["rules"].append(R(proto="tcp", dport=["80"], saddr="@all"))
        v = parse_view(body)
        assert v.exposure == "open_to_internet" and v.open_to_anywhere == ["tcp/80"], members
    body = good()
    body["host"]["sets"].append({"name": "one", "elements": ["203.0.113.7"]})
    body["host"]["chains"][0]["rules"].append(R(proto="tcp", dport=["80"], saddr="@one"))
    assert parse_view(body).exposure == "lan_and_mesh_only"
