# SPDX-License-Identifier: Apache-2.0
"""Desktop apps: one shared base image (apps/_bases/desktop) and one streaming runtime for every desktop app.

A desktop app (Obsidian, a browser, an office suite) runs on the box with its own screen, and the viewer sees it in a
browser tab through a streaming runtime. OneMind picks exactly one runtime, measured by test/gui/bakeoff.py, in this
order: Neko (Apache-2.0), then Selkies (MPL-2.0) only if Neko fails, then Xpra (GPL-2.0-or-later) only if both fail.
This module checks the base's recipe and Dockerfile, and the rules every app that streams a desktop must follow:
not root, not privileged, one runtime, and the runtime's own login switched off only behind a NetworkPolicy that
admits the gateway's proxy alone. Offline and deterministic; sdk/tools/app-factory does the docker calls.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from applib import common

BASES_DIR = common.APPS_DIR / "_bases"
BASE_NAME = "base.yaml"
API_VERSION = "onemind.factory/v1alpha1"
BASE_REGISTRY_PREFIX = "ghcr.io/onemindos/bases/"
DESKTOP_UID = 1000
OS = "debian-13"                                   # D-007: Debian 13 is the shipping base
# Kinds an app could ship to open its own ingress. The box refuses both (K-01: the gateway owns NetworkPolicy), so a
# login-free desktop may never rely on one.
INGRESS_KINDS = ("NetworkPolicy", "Ingress")

# The bake-off order. A runtime is reached only when every one before it failed the bake-off.
RUNTIME_ORDER = ("neko", "selkies", "xpra")
RUNTIMES = {
    "neko": {"licence": "Apache-2.0", "env_prefix": "NEKO_", "image_hint": "/neko/"},
    "selkies": {"licence": "MPL-2.0", "env_prefix": "SELKIES_", "image_hint": "selkies"},
    "xpra": {"licence": "GPL-2.0-or-later", "env_prefix": "XPRA_", "image_hint": "xpra"},
}
# How each runtime is told to skip its own login. Neko: the noauth member provider (server/internal/member/noauth,
# v3.2.0). Selkies and Xpra values are UNVERIFIED (not used while Neko passes).
LOGIN_OFF_ENV = {"NEKO_MEMBER_PROVIDER": {"noauth"}, "SELKIES_ENABLE_BASIC_AUTH": {"false", "0"}}
LOGIN_OFF_ARG = re.compile(r"(^|[-\s])(tcp-|ws-|bind-)?auth=(none|allow)\b")

PINNED_RE = re.compile(r"^[a-z0-9.\-]+(:[0-9]+)?(/[a-z0-9._\-]+)+:[A-Za-z0-9._\-]+@sha256:[0-9a-f]{64}$")


def load_base(base_dir: Path) -> dict | None:
    path = base_dir / BASE_NAME
    return yaml.safe_load(path.read_text(encoding="utf-8")) if path.is_file() else None


def validate_base(doc: object, base_dir: Path) -> list[str]:
    """Every problem with apps/_bases/<name>/base.yaml and its Dockerfile; [] when the base can be built."""
    if not isinstance(doc, dict):
        return ["base.yaml is not a mapping"]
    errs: list[str] = []
    name = base_dir.name
    if doc.get("apiVersion") != API_VERSION or doc.get("kind") != "Base":
        errs.append(f"apiVersion must be {API_VERSION} and kind Base")
    if doc.get("base") != name:
        errs.append(f"base must be '{name}'")
    if not PINNED_RE.match(str(doc.get("from", ""))):
        errs.append("from must be a registry image pinned as name:tag@sha256:<64 hex>")
    if doc.get("os") != OS:
        errs.append(f"os must be {OS} (D-007)")
    user = doc.get("user") if isinstance(doc.get("user"), dict) else {}
    if user.get("uid") != DESKTOP_UID or user.get("gid") != DESKTOP_UID:
        errs.append(f"user.uid and user.gid must be {DESKTOP_UID}: desktop images never run as root")
    rt = doc.get("runtime")
    if isinstance(rt, list) or "runtimes" in doc:
        errs.append("one streaming runtime only: runtime is a single mapping, not a list")
    elif not isinstance(rt, dict) or rt.get("name") not in RUNTIMES:
        errs.append(f"runtime.name must be one of {', '.join(RUNTIME_ORDER)}")
    else:
        if rt.get("licence") != RUNTIMES[rt["name"]]["licence"]:
            errs.append(f"runtime.licence for {rt['name']} is {RUNTIMES[rt['name']]['licence']}")
        if not re.fullmatch(r"\d+\.\d+\.\d+", str(rt.get("version", ""))):
            errs.append("runtime.version must be the pinned release, e.g. 3.2.0")
    archs = doc.get("archs")
    if not isinstance(archs, list) or not archs or set(archs) - {"amd64", "arm64"}:
        errs.append("archs must list amd64 and/or arm64")
    target = doc.get("target") if isinstance(doc.get("target"), dict) else {}
    if target.get("image") != f"{BASE_REGISTRY_PREFIX}{name}":
        errs.append(f"target.image must be {BASE_REGISTRY_PREFIX}{name}")
    build = doc.get("build") if isinstance(doc.get("build"), dict) else {}
    if build.get("sbom") is not True or build.get("scan") is not True:
        errs.append("build.sbom and build.scan must both be true")
    notices = str(build.get("notices", ""))
    if not notices or "/" in notices or not (base_dir / notices).is_file():
        errs.append("build.notices must name a licence notices file in the base directory")
    df = base_dir / "Dockerfile"
    if not df.is_file():
        errs.append("Dockerfile is missing")
    else:
        errs += dockerfile_problems(df.read_text(encoding="utf-8"), doc)
    return errs


def _instructions(text: str) -> list[tuple[str, str]]:
    """(INSTRUCTION, arguments) per Dockerfile instruction, continuation lines joined, comments dropped."""
    joined = re.sub(r"\\\n", " ", "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#")))
    out = []
    for line in joined.splitlines():
        parts = line.strip().split(None, 1)
        if parts:
            out.append((parts[0].upper(), parts[1] if len(parts) > 1 else ""))
    return out


def dockerfile_problems(text: str, doc: dict | None = None) -> list[str]:
    """Refuse a desktop image that ends as root, builds privileged, keeps sudo or setuid, or adds a second runtime.

    With doc (a base.yaml), also: the one FROM is doc['from'] and the licence notices are copied in.
    """
    ins = _instructions(text)
    errs: list[str] = []
    froms = [a for i, a in ins if i == "FROM"]
    if doc is not None and froms != [doc.get("from")]:
        errs.append("the Dockerfile must have exactly one FROM, the pinned base.yaml from")
    users = [a.strip() for i, a in ins if i == "USER"]
    if not users or not re.fullmatch(rf"{DESKTOP_UID}(:{DESKTOP_UID})?", users[-1]):
        errs.append(f"the last USER must be {DESKTOP_UID}:{DESKTOP_UID}: the image must not end as root")
    rt = (doc or {}).get("runtime") if isinstance((doc or {}).get("runtime"), dict) else {}
    others = [n for n in RUNTIMES if n != rt.get("name")] if rt.get("name") else []
    for i, a in ins:
        low = a.lower()
        if i == "RUN" and re.search(r"--security=insecure|--privileged|--device", low):
            errs.append("RUN may not ask for privileged or insecure build steps")
        if i == "RUN" and re.search(r"\b(apt-get|apt|apk)\b[^;&|]*\binstall\b[^;&|]*\bsudo\b", low):
            errs.append("the image may not install sudo")
        if i == "RUN" and re.search(r"chmod\s+([ug]\+s|[0-7]?[4-7][0-7]{3})\b", low):
            errs.append("the image may not set setuid or setgid bits")
        for other in others:
            if i in ("RUN", "COPY", "ADD") and re.search(rf"\b{other}\b", low):
                errs.append(f"a second streaming runtime ({other}) is not allowed: the base uses {rt['name']}")
    if doc is not None:
        notices = str(((doc.get("build") or {}) if isinstance(doc.get("build"), dict) else {}).get("notices", ""))
        if notices and not any(i == "COPY" and notices in a.split() for i, a in ins):
            errs.append(f"the Dockerfile must COPY {notices} into the image (licence notices)")
    return errs


def _env(c: dict) -> dict[str, str]:
    return {str(e.get("name")): str(e.get("value", "")) for e in c.get("env") or [] if isinstance(e, dict)}


def _runtime_of(c: dict) -> str | None:
    env = _env(c)
    img = str(c.get("image", ""))
    for name, r in RUNTIMES.items():
        if any(k.startswith(r["env_prefix"]) for k in env) or r["image_hint"] in img:
            return name
    return None


def _login_off(c: dict) -> bool:
    env = _env(c)
    if any(env.get(k, "").lower() in vals for k, vals in LOGIN_OFF_ENV.items()):
        return True
    return any(LOGIN_OFF_ARG.search(str(a)) for a in (c.get("command") or []) + (c.get("args") or []))


def _peer_problem(peer: dict, rule: dict, proxy: dict, web: set[int], alone: bool) -> str | None:
    """Why one ingress peer is more than the gateway, or None when it is the gateway (or the pod itself)."""
    if peer == {"namespaceSelector": {"matchLabels": proxy}} and proxy:
        return None                                                  # the gateway's app proxy namespace
    cidr = str((peer.get("ipBlock") or {}).get("cidr", "")) if set(peer) == {"ipBlock"} else ""
    ports = {p.get("port") for p in rule.get("ports") or []}
    if cidr.endswith(("/32", "/128")) and not peer["ipBlock"].get("except") and ports and ports <= web:
        return None                                                  # the gateway host, web port only
    if peer == {"podSelector": {}} and alone:
        return None                                                  # its own namespace, where it is the only pod
    return f"ingress from {peer} reaches it"


def gateway_only_problems(app_id: str, manifest: dict, objects: list[dict], rules, dependents: set[str]) -> list[str]:
    """Every way something other than the gateway could reach a desktop whose runtime login is off.

    The gateway writes the app's NetworkPolicies itself; an app cannot ship one (K-01). So this reads the policies the
    gateway would write for this app and refuses the login switch unless their ingress admits only the gateway's proxy
    namespace and the gateway host on the web port, plus the app's own namespace when the desktop is its only pod.
    It also refuses what would add a path later: another app depending on this one (the gateway then opens that app's
    namespace to it, contract 12.22), host ports, and NetworkPolicy or Ingress objects in the app.
    """
    errs: list[str] = []
    work = list(common.workloads(objects))
    alone = len(work) == 1 and work[0][0].get("kind") in ("Deployment", "StatefulSet") \
        and (common.dig(work[0][0], ("spec", "replicas")) or 1) == 1
    for o in objects:
        if o.get("kind") in INGRESS_KINDS:
            errs.append(f"{o['kind']}/{common.dig(o, ('metadata', 'name')) or '?'}: an app may not ship its own "
                        "ingress rules; the gateway writes them")
    spec = manifest.get("spec") or {}
    if spec.get("hostPorts"):
        errs.append("spec.hostPorts opens the desktop to the network")
    if dependents:
        errs.append(f"apps depending on it ({', '.join(sorted(dependents))}) would be let in by the gateway")
    from onemind_core import policy as gw  # the gateway's own code, so CI and the box cannot disagree

    egress, _ = gw.egress_entries(app_id, manifest, rules)
    web = set(gw.web_ports(manifest, objects))
    # The gateway runs on the hub host; 192.0.2.1 (TEST-NET-1, RFC 5737) stands in for its address here.
    for pol in gw.network_policies(app_id, egress, rules, gateway_sources=["192.0.2.1"], gateway_ports=sorted(web)):
        ps = pol.get("spec") or {}
        if "Ingress" not in (ps.get("policyTypes") or []):
            continue
        for rule in ps.get("ingress") or []:
            for peer in rule.get("from") or [{}]:
                why = _peer_problem(peer, rule, dict(rules.proxy_label), web, alone)
                if why:
                    errs.append(f"gateway policy {pol['metadata']['name']}: {why}")
    return errs


def stream_problems(objects: list[dict], app_id: str = "", manifest: dict | None = None, rules=None,
                    dependents: set[str] | None = None) -> list[str]:
    """Rules for every app whose pods run a streaming runtime (rendered Kubernetes objects of one app).

    Not root, not privileged, no added capabilities, one runtime, and the runtime's own login off only when
    gateway_only_problems finds nothing. rules: the gateway's sandbox rules (onemind_core.policy.load_rules).
    """
    errs: list[str] = []
    seen: set[str] = set()
    login_off_at: list[str] = []
    for obj, pod in common.workloads(objects):
        where = f"{obj.get('kind')}/{common.dig(obj, ('metadata', 'name')) or '?'}"
        streaming = [c for c in common.containers(pod) if _runtime_of(c)]
        if not streaming:
            continue
        seen.update(_runtime_of(c) for c in streaming)
        psc = pod.get("securityContext") or {}
        if psc.get("runAsUser") == 0 or psc.get("runAsNonRoot") is not True:
            errs.append(f"{where}: a desktop pod must set runAsNonRoot: true and a non-zero runAsUser")
        for c in common.containers(pod):
            sc = c.get("securityContext") or {}
            if sc.get("runAsUser") == 0 or sc.get("privileged") is True or sc.get("allowPrivilegeEscalation") is not False:
                errs.append(f"{where} container '{c.get('name')}': root, privileged or privilege escalation is refused")
            if (sc.get("capabilities") or {}).get("add"):
                errs.append(f"{where} container '{c.get('name')}': adding capabilities is refused")
        if any(_login_off(c) for c in streaming):
            login_off_at.append(where)
    if len(seen) > 1:
        errs.append(f"one streaming runtime per app: found {', '.join(sorted(seen))}")
    if login_off_at:
        if rules is None or manifest is None:
            errs.append(f"{', '.join(login_off_at)}: the runtime's own login is off and the gateway's policy is unknown")
        else:
            errs += [f"{', '.join(login_off_at)}: the runtime's own login is off, but {e}"
                     for e in gateway_only_problems(app_id, manifest, objects, rules, dependents or set())]
    return errs


def build_command(doc: dict, base_dir: Path, out: Path, push: bool, tag: str) -> list[str]:
    """The docker command the factory runs for a base: every arch, SBOM and max provenance when pushed."""
    ref = f"{doc['target']['image']}:{tag}"
    if push:
        return ["docker", "buildx", "build", "--platform", ",".join(f"linux/{a}" for a in doc["archs"]), "--push",
                "--provenance=mode=max", "--sbom=true", "--metadata-file", str(out / "buildx.json"),
                "-t", ref, "-f", str(base_dir / "Dockerfile"), str(base_dir)]
    return ["docker", "build", "--platform", "linux/amd64", "-t", ref, "-f", str(base_dir / "Dockerfile"), str(base_dir)]


def check_identity(os_release: str, uid: str) -> list[str]:
    """What the built image says about itself: Debian 13 and uid 1000 (read with docker run, see app-factory)."""
    kv = dict(re.findall(r'(?m)^([A-Z_]+)="?([^"\n]*)"?$', os_release))
    errs = []
    if (kv.get("ID"), kv.get("VERSION_ID")) != ("debian", "13"):
        errs.append(f"built image is {kv.get('ID')} {kv.get('VERSION_ID')}, not Debian 13")
    if uid.strip() != str(DESKTOP_UID):
        errs.append(f"built image runs as uid {uid.strip() or '?'}, not {DESKTOP_UID}")
    return errs
