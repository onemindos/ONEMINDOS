# SPDX-License-Identifier: Apache-2.0
"""Device capability card validator (issue #727), the Python twin of the Go validator in sdk/schema.

A card (sdk/schema/onemind.device-card.schema.json) says what a device can do and how risky each
property and action is. Besides the schema, both validators refuse, with the same rule names:
  credential-field     a key that names a credential (password, secret, token, API key ...) anywhere,
                       a URL with a user part (scheme://user:pass@host, //user@host, and the forms a
                       WHATWG parser also reads as one: https:user@host, https:/user@host, any
                       scheme:user@host), or a URL whose query or fragment has such a key or a short
                       one (?access_token=, ?pwd=, ?pass=, ?auth=, ?key=, ?sig=, ?Authorization= ...):
                       a card never carries a secret
  unitless-number      a number or integer value, a limit or a safe quantity without a unit
  physical-limits      a physical action without limits
  physical-safe-state  a physical action without a safe state
  physical-owner-only  a physical action an automation may ask for, or anyone but an owner approves
  hold-required        a class whose risk asks for hold-to-approve (physical, irreversible) without needsHold
  agent-approver       an agent listed as approver: AI never approves
  observe-read-only    class observe (risk read, nothing to approve) on anything that can change the
                       device: allowed only on a readOnly property, an event or a safe:true action, and
                       never with a form whose op writes (writeproperty, writemultipleproperties,
                       writeallproperties); an event never has a write form either
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
    "observe-read-only": "observe is only for a read-only property, an event or a safe action, never with a form that writes",
    "schema": "the card does not match onemind.device-card.schema.json",
}
CREDENTIAL_KEY = re.compile(r"password|passwd|passphrase|secret|token|apikey|privatekey|credential|accesskey")
# In a URL query or fragment a key is also a credential when it names one in short (exact match, so
# ?monkey= or ?author= stay harmless) or carries authorization or signature (?X-Amz-Signature=).
URL_SHORT_KEYS = frozenset({"pwd", "pass", "auth", "authorization", "key", "sig", "signature"})
URL_CREDENTIAL_KEY = re.compile(r"authorization|signature")
# A URL with a user part, read the way a WHATWG URL parser reads it (after it drops tab and newline
# and trims C0 controls and spaces; a backslash counts as a slash):
#   scheme://user@host or //user@host       (two slashes, any user part)
#   scheme:user@host, scheme:/user@host ... (any scheme, any number of slashes, a user part without space)
#   https: user@host                        (a special scheme reads everything up to @ as the user part)
# Case is ASCII only, spelled out, so the Go twin (sdk/schema/devicecard.go) matches character for character.
URL_USERINFO = re.compile(
    r"^(?:(?:[A-Za-z][A-Za-z0-9+.-]*:)?[/\\]{2}[^/\\?#]*@"
    r"|[A-Za-z][A-Za-z0-9+.-]*:[/\\]*[^/\\?#\x00-\x20]*@"
    r"|(?:[Hh][Tt][Tt][Pp][Ss]?|[Ww][Ss][Ss]?|[Ff][Tt][Pp]|[Ff][Ii][Ll][Ee]):[/\\]*[^/\\?#]*@)")
URL_TAB_NEWLINE = re.compile(r"[\t\n\r]")
URL_TRIM = "".join(chr(c) for c in range(0x21))   # C0 controls and space
# A form op that writes: writeproperty, writemultipleproperties, writeallproperties (any ASCII case).
WRITE_OP = re.compile(r"[Ww][Rr][Ii][Tt][Ee]")
WHITESPACE = re.compile(r"[ \t\n\r\f\v]")
# Characters a word in prose may open with before a URL starts: "(https://...", '"https://...'.
WORD_OPENERS = "([{<\"'`"
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


def _url_credential_key(key: str) -> bool:
    norm = re.sub(r"[-_. ]", "", key.lower())
    return norm in URL_SHORT_KEYS or CREDENTIAL_KEY.search(norm) is not None or URL_CREDENTIAL_KEY.search(norm) is not None


def _url_credential_parts(text: str) -> bool:
    """The user-part and query-key checks on one piece of text read as a URL."""
    if URL_USERINFO.search(text):
        return True
    for part in re.split(r"[?#]", text)[1:]:
        for pair in re.split(r"[&;]", part):
            if _url_credential_key(unquote_plus(pair.split("=", 1)[0])):
                return True
    return False


def _url_credential(text: str) -> bool:
    """A user part, or a query or fragment parameter whose (percent-decoded) key names a credential.

    Tab and newline are dropped first, as a URL parser drops them. Text with whitespace inside is
    prose, not a URL, so a description may say "token" or ask a question, unless it starts like a
    URL (scheme://, /, ?, #). Prose is still searched for URLs: each whitespace-separated word gets
    the same user-part and query-key checks, so "Open https://relay.example/x?access_token=abc now"
    is refused while "Is it on? It keeps no token." is not."""
    text = URL_TAB_NEWLINE.sub("", text).strip(URL_TRIM)
    if URL_USERINFO.search(text):
        return True
    if not WHITESPACE.search(text):
        return _url_credential_parts(text)
    if URL_START.search(text) and _url_credential_parts(text):
        return True
    return any(_url_credential_parts(word.lstrip(WORD_OPENERS)) for word in WHITESPACE.split(text) if word)


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


def _write_forms(aff: dict, path: str, out: list) -> None:
    """Every form whose op (a string or a list) writes."""
    forms = aff.get("forms")
    if not isinstance(forms, list):
        return
    for i, form in enumerate(forms):
        op = form.get("op") if isinstance(form, dict) else None
        ops = [op] if isinstance(op, str) else op if isinstance(op, list) else []
        if any(isinstance(o, str) and WRITE_OP.search(o) for o in ops):
            out.append((f"{path}/forms/{i}/op", "observe-read-only"))


def _observe(kind: str, aff: dict, path: str, out: list) -> None:
    """Observe maps to risk read, which skips approval: it may label only what cannot change the device,
    and nothing labelled so may carry a form that writes. An event is always observe."""
    s = aff.get("om:safety")
    if kind == "events":
        _write_forms(aff, path, out)
        return
    if not isinstance(s, dict) or s.get("class") != "observe":
        return
    if kind == "properties":
        writable = aff.get("readOnly") is not True or aff.get("writeOnly") is True
    else:
        writable = aff.get("safe") is not True
    if writable:
        out.append((f"{path}/om:safety/class", "observe-read-only"))
    _write_forms(aff, path, out)


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
