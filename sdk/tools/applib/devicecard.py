# SPDX-License-Identifier: Apache-2.0
"""Device capability card validator (issue #727), the Python twin of the Go validator in sdk/schema.

A card (sdk/schema/onemind.device-card.schema.json) says what a device can do and how risky each
property and action is. Besides the schema, both validators refuse, with the same rule names:
  credential-field     a key that names a credential (password, secret, token, API key ...) anywhere,
                       a URL with a user part (user:pass@host, also scheme-relative //user@host), or
                       a URL whose query or fragment has such a key (?access_token=...): a card never
                       carries a secret
  unitless-number      a number or integer value, a limit or a safe quantity without a unit
  physical-limits      a physical action without limits
  physical-safe-state  a physical action without a safe state
  physical-owner-only  a physical action an automation may ask for, or anyone but an owner approves
  hold-required        a class whose risk asks for hold-to-approve (physical, irreversible) without needsHold
  agent-approver       an agent listed as approver: AI never approves
  observe-read-only    class observe (risk read, nothing to approve) on anything that can change the
                       device: allowed only on a readOnly property, an event or a safe:true action
  schema               anything else the JSON Schema refuses
Problems name the rule and the path, never a value, so no secret reaches a log.

Run: python3 -I sdk/tools/applib/devicecard.py [CARD.json ...]  (no files: the shipped examples)
Exit codes: 0 every card valid, 1 a card failed, 2 a file could not be read.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import NamedTuple
from urllib.parse import unquote_plus

from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schema"
SCHEMA = json.loads((SCHEMA_DIR / "onemind.device-card.schema.json").read_text())
MAX_CARD_BYTES = 64 * 1024
CLASS_RISK = {k: (v["risk"], v["physical"]) for k, v in SCHEMA["x-om-class-risk"].items() if not k.startswith("$")}
RULES = {
    "credential-field": "a card never carries a credential",
    "unitless-number": "a number needs a unit",
    "physical-limits": "a physical action needs limits",
    "physical-safe-state": "a physical action needs a safe state",
    "physical-owner-only": "a physical action is asked for by a person or agent and approved only by an owner",
    "hold-required": "this class is approved with a hold: needsHold must be true",
    "agent-approver": "an agent never approves",
    "observe-read-only": "observe is only for a read-only property, an event or a safe action",
    "schema": "the card does not match onemind.device-card.schema.json",
}
CREDENTIAL_KEY = re.compile(r"password|passwd|passphrase|secret|token|apikey|privatekey|credential|accesskey")
# A URL with a user part: scheme://user@host, or scheme-relative //user@host (a backslash counts as a
# slash, as browsers read it). The same patterns are in the Go twin (sdk/schema/devicecard.go).
URL_USERINFO = re.compile(r"^[ \t\n\r\f\v]*(?:[A-Za-z][A-Za-z0-9+.-]*:)?[/\\]{2}[^/\\?#]*@")
WHITESPACE = re.compile(r"[ \t\n\r\f\v]")
URL_START = re.compile(r"^(?:[A-Za-z][A-Za-z0-9+.-]*:[/\\]{2}|[/\\?#])")
_VALIDATOR = Draft202012Validator(SCHEMA)


class Problem(NamedTuple):
    rule: str
    path: str
    message: str


def hold_required(risk: str, physical: bool) -> bool:
    """The same rule as core/onemind_core/approvalcard.hold_required."""
    return physical or risk == "destructive"


def _has_unit(node: dict) -> bool:
    unit = node.get("unit")
    return isinstance(unit, str) and unit.strip() != ""


def _credential_key(key: str) -> bool:
    return CREDENTIAL_KEY.search(re.sub(r"[-_. ]", "", key.lower())) is not None


def _url_credential(text: str) -> bool:
    """A user part, or a query or fragment parameter whose (percent-decoded) key names a credential.

    Text with whitespace inside is prose, not a URL, so a description may say "token" or ask a
    question, unless it starts like a URL (scheme://, /, ?, #)."""
    if URL_USERINFO.search(text):
        return True
    text = text.strip(" \t\n\r\f\v")
    if WHITESPACE.search(text) and not URL_START.search(text):
        return False
    for part in re.split(r"[?#]", text)[1:]:
        for pair in re.split(r"[&;]", part):
            if _credential_key(unquote_plus(pair.split("=", 1)[0])):
                return True
    return False


def _credentials(node, path: str, out: list) -> None:
    if isinstance(node, dict):
        for key in sorted(node):
            if _credential_key(key):
                out.append((f"{path}/{key}", "credential-field"))
            _credentials(node[key], f"{path}/{key}", out)
    elif isinstance(node, list):
        for i, item in enumerate(node):
            _credentials(item, f"{path}/{i}", out)
    elif isinstance(node, str) and _url_credential(node):
        out.append((path, "credential-field"))


def _units(ds, path: str, out: list) -> None:
    if not isinstance(ds, dict):
        return
    if ds.get("type") in ("number", "integer") and not _has_unit(ds):
        out.append((path, "unitless-number"))
    props = ds.get("properties")
    if isinstance(props, dict):
        for key in sorted(props):
            _units(props[key], f"{path}/properties/{key}", out)
    _units(ds.get("items"), f"{path}/items", out)


def _safety(s, path: str, out: list) -> None:
    if not isinstance(s, dict):
        return
    limits = s.get("limits") if isinstance(s.get("limits"), list) else []
    askers = s.get("askers") if isinstance(s.get("askers"), list) else []
    approvers = s.get("approvers") if isinstance(s.get("approvers"), list) else []
    for i, lim in enumerate(limits):
        if isinstance(lim, dict) and not _has_unit(lim):
            out.append((f"{path}/limits/{i}", "unitless-number"))
    state = s.get("safeState")
    if isinstance(state, dict) and isinstance(state.get("quantity"), dict) and not _has_unit(state["quantity"]):
        out.append((f"{path}/safeState/quantity", "unitless-number"))
    if "agent" in approvers:
        out.append((f"{path}/approvers", "agent-approver"))
    if not isinstance(s.get("class"), str) or s["class"] not in CLASS_RISK:
        return
    risk, physical = CLASS_RISK[s["class"]]
    if hold_required(risk, physical) and s.get("needsHold") is not True:
        out.append((f"{path}/needsHold", "hold-required"))
    if physical:
        if not limits:
            out.append((f"{path}/limits", "physical-limits"))
        if not isinstance(state, dict):
            out.append((f"{path}/safeState", "physical-safe-state"))
        if "automation" in askers or approvers != ["owner"]:
            out.append((path, "physical-owner-only"))


def _observe(kind: str, aff: dict, path: str, out: list) -> None:
    """Observe maps to risk read, which skips approval: it may label only what cannot change the device."""
    s = aff.get("om:safety")
    if not isinstance(s, dict) or s.get("class") != "observe":
        return
    if kind == "properties":
        writable = aff.get("readOnly") is not True or aff.get("writeOnly") is True
    else:
        writable = kind == "actions" and aff.get("safe") is not True
    if writable:
        out.append((f"{path}/om:safety/class", "observe-read-only"))


def problems(card: dict) -> list[Problem]:
    """The rule problems of a decoded card, in a stable order (sorted keys, the same walk in Go)."""
    found: list = []
    _credentials(card, "", found)
    for kind, inner in (("properties", ()), ("actions", ("input", "output")), ("events", ("data",))):
        group = card.get(kind)
        if not isinstance(group, dict):
            continue
        for name in sorted(group):
            aff, path = group[name], f"/{kind}/{name}"
            if not isinstance(aff, dict):
                continue
            if kind == "properties":
                _units(aff, path, found)
            for key in inner:
                _units(aff.get(key), f"{path}/{key}", found)
            _safety(aff.get("om:safety"), f"{path}/om:safety", found)
            _observe(kind, aff, path, found)
    return [Problem(rule, path or "/", RULES[rule]) for path, rule in found]


def _no_constant(name: str):
    raise ValueError(f"{name} is not JSON")


def validate(data: bytes) -> list[Problem]:
    """Every problem of one card; an empty list means it is valid."""
    if len(data) > MAX_CARD_BYTES:
        return [Problem("size", "/", f"a card is at most {MAX_CARD_BYTES} bytes")]
    try:
        card = json.loads(data, parse_constant=_no_constant)
    except (ValueError, RecursionError):
        return [Problem("json", "/", "not one JSON document")]
    if not isinstance(card, dict):
        return [Problem("schema", "/", RULES["schema"])]
    found = problems(card)
    if found:
        return found
    err = best_match(_VALIDATOR.iter_errors(card))
    if err is not None:
        path = "/" + "/".join(str(p) for p in err.absolute_path)
        return [Problem("schema", path, f"{RULES['schema']} (keyword {err.validator})")]
    return []


def main(argv: list[str]) -> int:
    files = [Path(a) for a in argv] or sorted((SCHEMA_DIR / "examples" / "device-card").glob("*.json"))
    status = 0
    for f in files:
        try:
            data = f.read_bytes()
        except OSError as exc:
            print(f"{f}: cannot read ({exc.strerror})", file=sys.stderr)
            return 2
        found = validate(data)
        for p in found:
            print(f"{f}: {p.rule} at {p.path}: {p.message}")
        if found:
            status = 1
        else:
            print(f"{f}: ok")
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
