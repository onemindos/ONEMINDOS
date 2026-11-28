#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check the Kanidm provisioning plan and render it (BD-03, D-015, D-030).

Kanidm is not installed in the image yet (CORE-SEC-10). This tool only reads provision.yaml and prints:
  check                       validate the plan (exit 1 on errors)
  server-toml                 the kanidmd server.toml for the plan's domain and origin
  plan                        the kanidm CLI steps that create the groups and the account policies
  invite NAME DISPLAY ROLE    the kanidm CLI steps that invite one new person (D-030 (2): passkeys only)
It never runs kanidm itself; CORE-SEC-10 runs these steps as idm_admin on the box.
"""
import argparse
import json
import os
import re
import shlex
import sys
from urllib.parse import urlsplit

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PLAN = os.path.join(HERE, "provision.yaml")
SCHEMA = "onemind.io/kanidm-provision/v1"
ROLES = ("owner", "adult", "child", "guest")
# Kanidm 1.12 AccountPolicyCredentialType, weakest to strongest (tools/cli/src/opt/kanidm.rs).
CRED_TYPES = ("any", "mfa", "passkey", "attested_passkey")
# Ports the gateway already holds on the hub (onemind-gateway.service, onemind_starting.py).
GATEWAY_PORTS = (443, 8443)
# Kanidm clamps a reset token's TTL to 300..86400 s (server/lib/src/idm/credupdatesession.rs).
RESET_TTL = (300, 86400)
NAME = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
HOST = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$")


def load(path=DEFAULT_PLAN):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _origin_port(u):
    try:
        return u.port or 443
    except ValueError:
        return None


def validate(cfg):
    """Return a list of problems; empty means the plan is usable."""
    if not isinstance(cfg, dict):
        return ["plan is not a mapping"]
    errs = []
    if cfg.get("schema") != SCHEMA:
        errs.append(f"schema must be {SCHEMA}")
    if not re.fullmatch(r"\d+\.\d+\.\d+", str(cfg.get("kanidm_version", ""))):
        errs.append("kanidm_version must be an exact x.y.z version")

    srv = cfg.get("server") or {}
    domain = str(srv.get("domain", ""))
    if not HOST.match(domain):
        errs.append(f"server.domain {domain!r} is not a lowercase host name")
    u = urlsplit(str(srv.get("origin", "")))
    port = _origin_port(u)
    if u.scheme != "https" or not u.hostname or u.path not in ("", "/") or u.query or u.fragment:
        errs.append("server.origin must be https://<host>[:port] with no path")
    elif u.hostname != domain and not u.hostname.endswith("." + domain):
        # Same rule kanidmd enforces at start; it is also the passkey RP ID rule (lab PK-5, PK-6).
        errs.append(f"server.origin host {u.hostname!r} is not {domain!r} or a sub-name of it")
    if port is None:
        errs.append("server.origin has an invalid port")
    elif port in GATEWAY_PORTS:
        errs.append(f"server.origin port {port} is held by the gateway")
    bind = re.fullmatch(r"(\[[0-9a-f:]+\]|[0-9.]+):(\d+)", str(srv.get("bindaddress", "")))
    if not bind:
        errs.append("server.bindaddress must be <address>:<port>")
    elif port is not None and int(bind.group(2)) != port:
        errs.append("server.bindaddress port differs from the origin port (no proxy in front of kanidmd yet)")
    for key in ("db_path", "tls_chain", "tls_key"):
        if not str(srv.get(key, "")).startswith("/"):
            errs.append(f"server.{key} must be an absolute path")

    roles = cfg.get("role_groups") or {}
    if sorted(roles) != sorted(ROLES):
        errs.append(f"role_groups must name exactly {', '.join(ROLES)}")
    policies = cfg.get("policy_groups") or {}
    groups = list(roles.values()) + list(policies)
    for g in groups:
        if not NAME.match(str(g)):
            errs.append(f"group name {g!r} is not valid")
    if len(set(groups)) != len(groups):
        errs.append("a group is listed twice")
    for g, pol in policies.items():
        if (pol or {}).get("credential_type_minimum") not in CRED_TYPES:
            errs.append(f"policy_groups.{g}.credential_type_minimum must be one of {', '.join(CRED_TYPES)}")

    inv = cfg.get("invite") or {}
    extra = inv.get("add_to_groups") or []
    for g in extra:
        if g not in policies:
            errs.append(f"invite.add_to_groups {g!r} is not a policy group")
    ttl = inv.get("reset_token_ttl_seconds")
    if not isinstance(ttl, int) or not RESET_TTL[0] <= ttl <= RESET_TTL[1]:
        errs.append(f"invite.reset_token_ttl_seconds must be {RESET_TTL[0]}..{RESET_TTL[1]}")
    return errs


def invite_minimum(cfg):
    """The strongest credential-type-minimum a newly invited person gets (Kanidm takes the largest)."""
    pols = cfg.get("policy_groups") or {}
    got = [pols[g]["credential_type_minimum"] for g in cfg["invite"].get("add_to_groups") or [] if g in pols]
    return max(got, key=CRED_TYPES.index) if got else "any"


def _toml(v):
    return json.dumps(v)  # a JSON string is a valid TOML basic string


def server_toml(cfg):
    s = cfg["server"]
    return "\n".join([
        "# Rendered by os/identity/kanidm/kanidm-provision.py from provision.yaml. Do not edit by hand.",
        'version = "2"',
        f"bindaddress = {_toml(s['bindaddress'])}",
        f"db_path = {_toml(s['db_path'])}",
        f"tls_chain = {_toml(s['tls_chain'])}",
        f"tls_key = {_toml(s['tls_key'])}",
        f"domain = {_toml(s['domain'])}",
        f"origin = {_toml(s['origin'])}",
        "",
    ])


def plan(cfg):
    """kanidm CLI argv lists (run as idm_admin) that create the groups and set the policies."""
    steps = [["kanidm", "group", "create", g] for g in list(cfg["role_groups"].values()) + list(cfg["policy_groups"])]
    for g, pol in cfg["policy_groups"].items():
        steps.append(["kanidm", "group", "account-policy", "enable", g])
        steps.append(["kanidm", "group", "account-policy", "credential-type-minimum", g, pol["credential_type_minimum"]])
    return steps


def invite(cfg, name, display, role):
    """kanidm CLI argv lists that invite one new person: role group, the invite policy groups, a reset link."""
    if not NAME.match(name):
        raise ValueError(f"person name {name!r} is not valid")
    if role not in cfg["role_groups"]:
        raise ValueError(f"role {role!r} is not one of {', '.join(cfg['role_groups'])}")
    steps = [["kanidm", "person", "create", name, display],
             ["kanidm", "group", "add-members", cfg["role_groups"][role], name]]
    steps += [["kanidm", "group", "add-members", g, name] for g in cfg["invite"].get("add_to_groups") or []]
    steps.append(["kanidm", "person", "credential", "create-reset-token", name,
                  "--ttl", str(cfg["invite"]["reset_token_ttl_seconds"])])
    return steps


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--plan", default=DEFAULT_PLAN)
    ap.add_argument("--json", action="store_true", help="print steps as JSON")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    sub.add_parser("server-toml")
    sub.add_parser("plan")
    p = sub.add_parser("invite")
    p.add_argument("name")
    p.add_argument("display")
    p.add_argument("role")
    a = ap.parse_args(argv)
    cfg = load(a.plan)
    errs = validate(cfg)
    if errs:
        print("\n".join(errs), file=sys.stderr)
        return 1
    if a.cmd == "check":
        print(f"ok: domain {cfg['server']['domain']}, origin {cfg['server']['origin']}, "
              f"new invitees need {invite_minimum(cfg)}")
        return 0
    if a.cmd == "server-toml":
        sys.stdout.write(server_toml(cfg))
        return 0
    try:
        steps = plan(cfg) if a.cmd == "plan" else invite(cfg, a.name, a.display, a.role)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 2
    print(json.dumps(steps, indent=2) if a.json else "\n".join(shlex.join(s) for s in steps))
    return 0


if __name__ == "__main__":
    sys.exit(main())
