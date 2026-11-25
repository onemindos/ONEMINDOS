# SPDX-License-Identifier: Apache-2.0
"""The box's firewall, read-only, in plain words (P-09 part 1: "Firewall: view").

The host service (`onemindd host serve`, internal/firewall) runs `nft -j list ruleset` and answers
`GET /v1/firewall` with a small structured form of the OneMind table. This module checks that answer
again item by item (H-06: a rule or name that fails a check is dropped and counted), works out who each
rule lets in (this machine, the mesh, the pod network, the home LAN, or any address) and writes one
plain sentence per rule. Nothing here changes the firewall.

Part 2 (allow rules with automatic revert, fwallow.py) adds the owner's own allow rules: the host reports them
in `allow`, this module checks them like every other field, and `editable` says whether the box can take new
ones. The rules themselves also appear in `rules`, in the lists `owner_lan` and `owner_mesh`, in the same words as
every other rule.
"""

from __future__ import annotations

import ipaddress
import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .hostnet import HostNetClient, Reason, _items
from .storage import StorageTimeout, StorageUnavailable

SCHEMA = "onemind.firewall/v1"
PATH = "/v1/firewall"

NAME_RE = re.compile(r"^[A-Za-z0-9_.@*:-]{1,40}$")
VERDICTS = ("accept", "drop", "reject", "jump", "goto", "return", "none")
PROTOS = ("tcp", "udp", "icmp", "ipv6-icmp")
CT_STATES = ("established", "related", "new", "invalid", "untracked")
PORT_RE = re.compile(r"^(\d{1,5})(-(\d{1,5}))?$")
MAX_CHAINS = 64
MAX_RULES = 400
MAX_TABLES = 32
MAX_VALUES = 64
MAX_ALLOW = 32
ALLOW_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")

Audience = Literal["this_machine", "mesh", "pod_network", "lan", "specific_address", "one_interface", "any_network"]
Kind = Literal["open_port", "basics", "state", "internal", "hand_off", "block", "other"]
Exposure = Literal["lan_and_mesh_only", "open_to_internet", "no_firewall", "not_fully_understood"]

_LAN_RANGES = tuple(ipaddress.ip_network(n) for n in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16", "100.64.0.0/10", "fc00::/7", "fe80::/10"))

# Wider is later: a chain reached from two audiences is as open as the wider one.
_WIDTH = ("this_machine", "pod_network", "mesh", "specific_address", "one_interface", "lan", "any_network")

AUDIENCE_WORDS: dict[str, str] = {
    "this_machine": "this box itself",
    "mesh": "other machines on your OneMind mesh",
    "pod_network": "the apps running on this box",
    "lan": "devices on your home network (LAN)",
    "specific_address": "one named address",
    "one_interface": "one network connection",
    "any_network": "any address (the internet too, if the box is reachable from it)",
}

# What a port is for, in the words a person uses. Only the ports the image itself opens are named.
PORT_NAMES: dict[tuple[str, int], str] = {
    ("tcp", 22): "remote login, SSH", ("tcp", 443): "the OneMind dashboard and gateway, HTTPS",
    ("tcp", 445): "file sharing, Samba", ("tcp", 6443): "the cluster API, k3s", ("tcp", 7422): "the OneMind message bus link, NATS",
    ("tcp", 7443): "the rescue console", ("tcp", 8080): "the first-time setup wizard", ("tcp", 8443): "the OneMind gateway, HTTPS",
    ("tcp", 8444): "joining the mesh, Headscale", ("tcp", 10250): "the cluster node agent, kubelet",
    ("udp", 3478): "mesh connection set-up, STUN", ("udp", 5353): "finding the box by name, mDNS",
    ("udp", 8472): "the cluster network, flannel", ("udp", 41641): "the mesh tunnel", ("udp", 51820): "the cluster network, flannel",
    ("udp", 51821): "the cluster network, flannel",
}


class FirewallRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chain: str
    position: int = Field(description="1-based place in its chain; rules are tried in order.")
    action: Literal["accept", "drop", "reject", "jump", "goto", "return", "none"]
    kind: Kind
    audience: Audience = Field(description="Who this rule applies to (where the packet comes from).")
    proto: Literal["tcp", "udp", "icmp", "ipv6-icmp"] | None = None
    ports: list[str] = Field(description="Destination ports or ranges the rule matches; empty when it names none.")
    summary: str = Field(description="One plain sentence: what the rule does and for whom.")
    understood: bool = Field(description="False when the rule uses something this screen cannot describe; the summary then says so.")


class FirewallChain(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    base: bool = Field(description="A base chain sees traffic first; the others are reached from a rule that jumps to them.")
    hook: str | None = None
    policy: Literal["accept", "drop"] | None = Field(default=None, description="What happens to traffic no rule matched (base chains).")
    audience: Audience | None = Field(default=None, description="For a chain reached by jump: who can get into it.")
    rules: int


class FirewallSet(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    elements: list[str]


class FirewallTable(BaseModel):
    model_config = ConfigDict(extra="forbid")
    family: str
    name: str
    chains: int
    rules: int


class AllowRule(BaseModel):
    """One port the owner opened. `pending` rules revert at `expires_at` unless confirmed."""

    model_config = ConfigDict(extra="forbid")
    id: str = Field(description="The id of the approved action that opened it.")
    proto: Literal["tcp", "udp"]
    port: int
    scope: Literal["lan", "mesh"]
    state: Literal["pending", "confirmed", "revert_failed"] = Field(description="revert_failed: its time ran out and the box could not take it away yet; it keeps trying, and the owner can remove it now.")
    created_at: datetime | None = None
    expires_at: datetime | None = Field(default=None, description="Pending only: when the box takes the rule away again if nobody confirmed it.")
    summary: str


class AllowView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    supported: bool = Field(description="False when this box's firewall has no owner rule lists yet (older image) or the host cannot take rules.")
    reason: str | None = None
    ttl_seconds: int = Field(description="How long a new rule waits for confirmation before it reverts.")
    rules: list[AllowRule] = []


class FirewallView(BaseModel):
    """The box's firewall, explained. `editable` is true when the box can take allow rules (`allow.supported`)."""

    model_config = ConfigDict(extra="forbid")
    available: bool
    reason: Reason | None = None
    message: str | None = None
    at: datetime | None = None
    exposure: Exposure | None = Field(default=None, description="lan_and_mesh_only: every rule was read and nothing is open to an unknown address. open_to_internet: at least one service is. no_firewall: the OneMind table is not loaded or does not drop by default. not_fully_understood: a rule that lets traffic in uses something this screen cannot read, or part of the ruleset was left out; the box is never called safe on a guess.")
    headline: str | None = Field(default=None, description="The answer in one sentence.")
    default_action: Literal["accept", "drop"] | None = Field(default=None, description="What the input chain does with traffic no rule allows.")
    open_to_anywhere: list[str] = Field(default=[], description="proto/port of every service open to any address, e.g. tcp/22. Empty on a normal box.")
    chains: list[FirewallChain] = []
    rules: list[FirewallRule] = []
    sets: list[FirewallSet] = []
    other_tables: list[FirewallTable] = Field(default=[], description="Tables other services keep (cluster, mesh guard), by name and size only.")
    editable: bool = Field(default=False, description="True when the owner can ask for allow rules (POST /v1/network/firewall/allow); false on an image or host that cannot take them.")
    allow: AllowView | None = Field(default=None, description="The ports the owner opened, with their state and deadline; null when the host service keeps none.")
    dropped: int = Field(default=0, description="Entries the gateway refused because a field failed its checks, or past its own size caps.")
    truncated: int = Field(default=0, description="Chains, rules, sets and set members the host service left out because of its size caps. Not zero means the view is partial.")


def unavailable(reason: Reason, message: str) -> FirewallView:
    return FirewallView(available=False, reason=reason, message=message)


# ---- checks -------------------------------------------------------------------------------------------


def _name(v: Any) -> str:
    if not isinstance(v, str) or not NAME_RE.match(v):
        raise ValueError("bad name")
    return v


def _port(v: Any) -> str:
    if not isinstance(v, str):
        raise ValueError("bad port")
    m = PORT_RE.match(v)
    if not m:
        raise ValueError("bad port")
    lo, hi = int(m.group(1)), int(m.group(3) or m.group(1))
    if not (1 <= lo <= 65535 and 1 <= hi <= 65535 and lo <= hi):
        raise ValueError("bad port")
    return v


def _ports(v: Any) -> list[str]:
    if v is None:
        return []
    if not isinstance(v, list) or len(v) > MAX_VALUES:
        raise ValueError("bad ports")
    return [_port(p) for p in v]


def _saddr(v: Any) -> str | None:
    """A set reference (@name) or an address/prefix. Anything else is refused."""
    if v in (None, ""):
        return None
    if not isinstance(v, str):
        raise ValueError("bad source")
    if "%" in v:  # an IPv6 scope id names a local interface; never shown
        raise ValueError("scope id")
    if v.startswith("@"):
        _name(v[1:])
        return v
    return str(ipaddress.ip_network(v, strict=False)) if "/" in v else str(ipaddress.ip_address(v))


def _element(v: Any) -> str:
    if not isinstance(v, str) or "%" in v:
        raise ValueError("bad element")
    return str(ipaddress.ip_network(v, strict=False)) if "/" in v else str(ipaddress.ip_address(v))


class _Raw(BaseModel):
    """A host-service rule after the checks, before it is explained."""

    chain: str
    verdict: str
    target: str | None
    iif: str | None
    proto: str | None
    sport: list[str]
    dport: list[str]
    saddr: str | None
    ct: list[str]
    understood: bool


def _raw_rule(chain: str, d: dict) -> _Raw:
    verdict = d.get("verdict")
    if verdict not in VERDICTS:
        raise ValueError("bad verdict")
    proto = d.get("proto") or None
    if proto is not None and proto not in PROTOS:
        raise ValueError("bad protocol")
    ct = d.get("ct") or []
    if not isinstance(ct, list) or any(c not in CT_STATES for c in ct):
        raise ValueError("bad connection state")
    target = d.get("target") or None
    if target is not None:
        _name(target)
    iif = d.get("iif") or None
    if iif is not None:
        _name(iif)
    if not isinstance(d.get("understood"), bool):
        raise ValueError("bad understood flag")
    return _Raw(chain=chain, verdict=verdict, target=target, iif=iif, proto=proto, sport=_ports(d.get("sport")),
                dport=_ports(d.get("dport")), saddr=_saddr(d.get("saddr")), ct=ct, understood=d["understood"])


# ---- who a rule lets in --------------------------------------------------------------------------------


def _is_lan_prefix(saddr: str) -> bool:
    """Wholly inside a home-network range: RFC 1918, link-local, unique-local, or the shared 100.64.0.0/10
    (carrier-grade NAT, also the mesh's range). Documentation and reserved ranges are not the LAN."""
    try:
        net = ipaddress.ip_network(saddr, strict=False)
    except ValueError:
        return False
    return any(net.version == r.version and net.subnet_of(r) for r in _LAN_RANGES)


def _is_everyone(saddr: str) -> bool:
    """A source condition that still matches (nearly) every address: 0.0.0.0/0, ::/0, or a prefix so short that it
    only trims a sliver (0.0.0.0/1 + 128.0.0.0/1 is the usual way to write "everyone" twice)."""
    try:
        net = ipaddress.ip_network(saddr, strict=False)
    except ValueError:
        return False
    return net.prefixlen <= (4 if net.version == 4 else 3)


def _own_audience(r: _Raw, set_audience: dict[str, str]) -> str | None:
    """Who a rule's own conditions limit it to; None when it names nobody (the chain decides)."""
    if r.iif is not None:
        if r.iif == "lo":
            return "this_machine"
        if r.iif.startswith("tailscale"):
            return "mesh"
        if r.iif.startswith("flannel") or r.iif in ("cni0", "cni1"):
            return "pod_network"
    by_source = None
    if r.saddr is not None:
        if r.saddr.startswith("@"):
            by_source = set_audience.get(r.saddr[1:], "specific_address")
        elif (":" in r.saddr or "." in r.saddr) and not _is_everyone(r.saddr):
            by_source = "lan" if _is_lan_prefix(r.saddr) else "specific_address"
    if by_source is not None:
        return by_source  # a source limit is a tighter statement than "arrives on connection X"
    if r.iif is not None:
        return "one_interface"
    return None


def _wider(a: str, b: str) -> str:
    return a if _WIDTH.index(a) >= _WIDTH.index(b) else b


def _port_phrase(proto: str | None, ports: list[str]) -> str:
    parts = []
    for p in ports:
        label = f"{(proto or 'tcp').upper()} {p}"
        if proto and p.isdigit() and (proto, int(p)) in PORT_NAMES:
            label += f" ({PORT_NAMES[(proto, int(p))]})"
        parts.append(label)
    return ", ".join(parts)


def _is_replies_only(r: _Raw) -> bool:
    """`ct state established,related accept` and nothing else: the only connection-state rule that is safe to call
    "replies". Any other state (new, invalid, untracked), or a state rule that also names a port, protocol, source or
    connection, lets new traffic in and is classified by what it opens."""
    return (bool(r.ct) and set(r.ct) <= {"established", "related"} and not r.dport and not r.sport and r.proto is None
            and r.saddr is None and r.iif is None)


def _classify(r: _Raw, audience: str) -> tuple[str, str]:
    """(kind, one plain sentence) for one rule whose audience is known."""
    who = AUDIENCE_WORDS[audience]
    cap = who[0].upper() + who[1:]
    if not r.understood:
        return "other", "A rule this screen cannot describe in plain words yet. It is shown so nothing is hidden, not explained so nothing is guessed."
    if r.verdict in ("jump", "goto"):
        return "hand_off", f"Traffic from {AUDIENCE_WORDS[audience]} is checked against the '{r.target}' list next."
    if r.verdict == "return":
        return "other", "Stops checking this list and goes back to the one that called it."
    if r.verdict in ("drop", "reject"):
        if r.ct == ["invalid"]:
            return "block", "Packets that belong to no real connection are dropped."
        return "block", f"{cap}: traffic that matches is refused."
    if r.verdict == "none":
        return "other", "A rule without a verdict; it changes nothing about what is allowed."
    # accept
    if _is_replies_only(r):
        return "state", "Replies to connections this box started (and their related traffic) are always allowed in."
    if r.proto in ("icmp", "ipv6-icmp") and not r.dport:
        return "basics", f"Ping and the network's housekeeping messages (ICMP) are answered, from {who}."
    if r.proto == "udp" and r.sport and r.dport and any(p in ("67", "547") for p in r.sport):
        return "basics", "The router's answer to the box asking for a network address (DHCP) is allowed in."
    if r.dport:
        return "open_port", f"{cap} can reach {_port_phrase(r.proto, r.dport)}."
    if audience == "this_machine":
        return "internal", "The box can talk to itself."
    if audience in ("pod_network", "mesh"):
        return "internal", f"Everything from {who} is allowed in."
    if r.saddr is not None or r.iif is not None:
        return "internal", f"Everything from {who} is allowed in."
    if r.ct:
        return "other", "Every new connection is allowed in, from any address."
    return "other", "Everything is allowed in, from any address."


CHECKED = " This checks what arrives at the box; traffic passed on to apps on the box (for example cluster node ports) is not checked here."


def _headline(exposure: str, default: str | None, wan: list[str], why: list[str] | None = None) -> str:
    if exposure == "no_firewall":
        return "The OneMind firewall is not active, or it lets traffic in by default. Anything the box listens on may be reachable."
    if exposure == "open_to_internet":
        return f"Blocked by default. Open to any address, including the internet: {', '.join(wan)}. Everything else is closed." + CHECKED
    if exposure == "not_fully_understood":
        return ("Blocked by default, but this screen could not read everything, so it cannot say nothing is open to the internet: "
                + "; ".join(why or ["some rules were not read"]) + ". Treat the box as possibly reachable until that is cleared." + CHECKED)
    return ("Blocked by default. Only your home network (LAN), your mesh and this box itself can reach anything. "
            "Nothing is open to the internet." + CHECKED)


def _when(v: Any) -> datetime | None:
    if v in (None, ""):
        return None
    if not isinstance(v, str):
        raise ValueError("bad time")
    return datetime.fromisoformat(v.replace("Z", "+00:00"))


def _allow_rule(e: Any) -> AllowRule:
    if not isinstance(e, dict):
        raise ValueError("not an object")
    rid, proto, scope, state = e.get("id"), e.get("proto"), e.get("scope"), e.get("state")
    port = e.get("port")
    if not isinstance(rid, str) or not ALLOW_ID_RE.match(rid) or proto not in ("tcp", "udp") or scope not in ("lan", "mesh") \
            or state not in ("pending", "confirmed", "revert_failed") or not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
        raise ValueError("bad allow rule")
    expires = _when(e.get("expires")) if state == "pending" else None
    if state == "pending" and expires is None:
        raise ValueError("a pending rule has a deadline")
    who = AUDIENCE_WORDS["lan" if scope == "lan" else "mesh"]
    tail = {"pending": "Closes again by itself unless you confirm it.", "confirmed": "Confirmed: stays open until you remove it.",
            "revert_failed": "Its time ran out and the box could not close it yet. It keeps trying; you can remove it now."}[state]
    return AllowRule(id=rid, proto=proto, port=port, scope=scope, state=state, created_at=_when(e.get("created")), expires_at=expires,
                     summary=f"Lets {who} reach {proto.upper()} port {port}. {tail}")


def _allow_view(raw: Any) -> tuple[AllowView | None, int]:
    """The host's `allow` part, checked: (view, entries dropped). Anything malformed is dropped and counted, never shown."""
    if raw is None:
        return None, 0
    if not isinstance(raw, dict) or not isinstance(raw.get("supported"), bool):
        return None, 1
    ttl = raw.get("ttl_seconds")
    if not isinstance(ttl, int) or isinstance(ttl, bool) or not 1 <= ttl <= 86400:
        return None, 1
    reason = raw.get("reason")
    reason = reason[:200] if isinstance(reason, str) and reason and not CONTROL_RE.search(reason) else None
    rules, dropped = _items(raw.get("rules"), _allow_rule, MAX_ALLOW)
    seen: set[str] = set()
    unique = []
    for r in rules:
        if r.id in seen:
            dropped += 1
        else:
            seen.add(r.id)
            unique.append(r)
    return AllowView(supported=raw["supported"], reason=reason, ttl_seconds=ttl, rules=unique), dropped


def parse_view(body: Any) -> FirewallView:
    view = _parse_view(body)
    if view.available and isinstance(body, dict):
        allow, d = _allow_view(body.get("allow"))
        view.allow, view.dropped = allow, view.dropped + d
        view.editable = bool(allow and allow.supported and view.exposure != "no_firewall")
    return view


def _parse_view(body: Any) -> FirewallView:
    if not isinstance(body, dict) or body.get("schema") != SCHEMA:
        return unavailable("bad_response", "the host service sent something the gateway does not understand")
    dropped = 0
    host_dropped = 0  # entries of the OneMind table that failed a check: something there was not seen
    tables, d = _items(body.get("tables"), lambda e: FirewallTable(family=_name(e.get("family")), name=_name(e.get("name")),
                                                                  chains=_count(e.get("chains")), rules=_count(e.get("rules"))), MAX_TABLES)
    dropped += d
    try:
        truncated = _count(body.get("truncated", 0))
    except ValueError:
        return unavailable("bad_response", "the host service sent something the gateway does not understand")
    at = None
    try:
        at = datetime.fromisoformat(str(body.get("at")).replace("Z", "+00:00"))
    except ValueError:
        pass
    host = body.get("host")
    others = [t for t in tables if not (t.family == "inet" and t.name == "onemind_host")]
    if not isinstance(host, dict) or host.get("name") != "onemind_host" or host.get("family") != "inet":
        return FirewallView(available=True, at=at, exposure="no_firewall", headline=_headline("no_firewall", None, []),
                            other_tables=others, dropped=dropped + (0 if host is None else 1))

    raw_sets, d = _items(host.get("sets"), lambda e: (_name(e.get("name")), _elements(e.get("elements"))), 32)
    dropped += d
    host_dropped += d
    sets = [FirewallSet(name=n, elements=el) for n, el in raw_sets]
    def _set_aud(el: list[str]) -> str:
        if any(_is_everyone(e) for e in el):
            return "any_network"  # a set that holds "everyone" (0.0.0.0/0, or the 0/1 + 128/1 pair) is everyone
        return "lan" if el and all(_is_lan_prefix(e) for e in el) else "specific_address"

    set_audience = {n: _set_aud(el) for n, el in raw_sets}
    set_audience = {n: ("specific_address" if truncated and a == "lan" else a) for n, a in set_audience.items()}  # a cut set may hide a public member

    by_name: dict[str, dict] = {}
    chains_in: list[tuple[dict, list[_Raw]]] = []
    seen: set[str] = set()
    all_chains = host.get("chains") or []
    if not isinstance(all_chains, list):
        all_chains = []
        dropped += 1
        host_dropped += 1
    over = max(0, len(all_chains) - MAX_CHAINS)
    dropped += over
    host_dropped += over
    for c in all_chains[:MAX_CHAINS]:
        try:
            if not isinstance(c, dict):
                raise ValueError("not an object")
            head = _chain_head(c)
            if head["name"] in seen:
                raise ValueError("duplicate chain")
            rules, rd = _items(c.get("rules"), lambda e, n=head["name"]: _raw_rule(n, e), MAX_RULES)
            dropped += rd
            host_dropped += rd
            seen.add(head["name"])
            chains_in.append((head, rules))
            by_name[head["name"]] = head
        except (ValueError, TypeError):
            dropped += 1
            host_dropped += 1

    # Audience of each non-base chain: who can jump into it, widest wins; settled by repeating until stable.
    chain_aud: dict[str, str] = {}
    for _ in range(len(chains_in) + 1):
        changed = False
        for head, rules in chains_in:
            if head["hook"] not in (None, "input"):
                continue  # forward/output rules say nothing about who can reach the box
            if head["hook"] is None and head["name"] not in chain_aud:
                continue  # not reached from the input chain (yet)
            base_aud = chain_aud.get(head["name"])
            for r in rules:
                if r.verdict in ("jump", "goto") and r.target in by_name:
                    own = _own_audience(r, set_audience) or base_aud or "any_network"
                    new = own if r.target not in chain_aud else _wider(chain_aud[r.target], own)
                    if chain_aud.get(r.target) != new:
                        chain_aud[r.target], changed = new, True
        if not changed:
            break

    rules_out: list[FirewallRule] = []
    wan: list[str] = []
    unread = 0  # permitting rules from an open audience that this screen could not read
    for head, rules in chains_in:
        inherited = chain_aud.get(head["name"])
        reached = head["hook"] == "input" or (head["hook"] is None and head["name"] in chain_aud)
        for i, r in enumerate(rules, 1):
            aud = _own_audience(r, set_audience) or inherited or "any_network"
            kind, summary = _classify(r, aud)
            rules_out.append(FirewallRule(chain=head["name"], position=i, action=r.verdict, kind=kind, audience=aud, proto=r.proto,
                                          ports=r.dport, summary=summary, understood=r.understood))
            if not reached or aud not in ("any_network", "one_interface"):
                continue
            if r.verdict in ("accept", "jump", "goto") and not r.understood:
                unread += 1
            elif r.verdict == "accept" and kind in ("open_port", "other", "internal"):
                where = f" on {r.iif}" if aud == "one_interface" else ""
                if r.dport:
                    wan.extend(f"{r.proto or 'tcp'}/{p}{where}" for p in r.dport)
                else:
                    wan.append(f"everything{where}")
    wan = list(dict.fromkeys(wan))

    inp = next((h for h, _ in chains_in if h["hook"] == "input"), None)
    default = inp["policy"] if inp else None
    why: list[str] = []
    if unread:
        why.append(f"{unread} rule{'s' if unread != 1 else ''} that let traffic in use something it cannot describe")
    if truncated:
        why.append(f"{truncated} part{'s' if truncated != 1 else ''} of the rules {'were' if truncated != 1 else 'was'} left out for size")
    if host_dropped:
        why.append(f"{host_dropped} entr{'ies' if host_dropped != 1 else 'y'} failed its checks")
    exposure = ("no_firewall" if default != "drop" else "open_to_internet" if wan else "not_fully_understood" if why else "lan_and_mesh_only")
    chains_out = [FirewallChain(name=h["name"], base=h["hook"] is not None, hook=h["hook"], policy=h["policy"],
                                audience=None if h["hook"] else chain_aud.get(h["name"]), rules=len(rs)) for h, rs in chains_in]
    return FirewallView(available=True, at=at, exposure=exposure, headline=_headline(exposure, default, wan, why), default_action=default,
                        open_to_anywhere=wan, chains=chains_out, rules=rules_out, sets=sets, other_tables=others, dropped=dropped, truncated=truncated)


def _count(v: Any) -> int:
    if not isinstance(v, int) or isinstance(v, bool) or not 0 <= v <= 1_000_000:
        raise ValueError("bad count")
    return v


def _elements(v: Any) -> list[str]:
    if not isinstance(v, list) or len(v) > 64:
        raise ValueError("bad elements")
    return [_element(e) for e in v]


def _chain_head(c: dict) -> dict:
    hook = c.get("hook") or None
    if hook is not None and hook not in ("input", "forward", "output", "prerouting", "postrouting", "ingress"):
        raise ValueError("bad hook")
    policy = c.get("policy") or None
    if policy is not None and policy not in ("accept", "drop"):
        raise ValueError("bad policy")
    return {"name": _name(c.get("name")), "hook": hook, "policy": policy}


def read_view(client: HostNetClient) -> FirewallView:
    try:
        status, body = client.fetch(PATH)
    except (StorageUnavailable, StorageTimeout):
        return unavailable("host_service_unreachable",
                           "the host service is not reachable from the gateway, so this box's firewall cannot be read yet")
    if status == 404:
        return unavailable("host_service_error", "this box's host service is too old to report the firewall; update the OS")
    if status != 200:
        return unavailable("host_service_error", f"the host service answered {status}")
    return parse_view(body)
