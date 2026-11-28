# SPDX-License-Identifier: Apache-2.0
"""App factory (first slice): rebuild an app's image on a patched, digest-pinned base and record where it came from.

A recipe (apps/<id>/factory.yaml) says which upstream release to watch, which image that release publishes and
which operating-system packages to upgrade on top of it ("overlay"). Everything here is deterministic and offline
(no network, no docker) so it can be tested; sdk/tools/app-factory does the network and docker calls.
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import yaml

from applib import common

RECIPE_NAME = "factory.yaml"
API_VERSION = "onemind.factory/v1alpha1"
BUILDER = "onemind-app-factory"
REGISTRY_PREFIX = "ghcr.io/onemindos/apps/"      # packages are written with the workflow's GITHUB_TOKEN
DEFAULT_REBUILD_DAYS = 7                          # re-patch the OS packages at least weekly (gateway: scan <= 7 days)
PKG_RE = re.compile(r"^[a-z0-9][a-z0-9+.\-]*$")  # apt and apk package names; nothing a shell could read as syntax
USER_RE = re.compile(r"^[a-z_][a-z0-9_-]*$|^[0-9]+$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
IMAGE_RE = re.compile(r"^[a-z0-9.\-]+(:[0-9]+)?(/[a-z0-9._\-]+)+$")


def load_recipe(app_dir: Path) -> dict | None:
    path = app_dir / RECIPE_NAME
    return yaml.safe_load(path.read_text(encoding="utf-8")) if path.is_file() else None


def validate_recipe(doc: object, app_dir: Path) -> list[str]:
    """Return every problem with a recipe; [] when it is usable."""
    if not isinstance(doc, dict):
        return ["recipe is not a mapping"]
    errs: list[str] = []
    app_id = app_dir.name
    if doc.get("apiVersion") != API_VERSION or doc.get("kind") != "Recipe":
        errs.append(f"apiVersion must be {API_VERSION} and kind Recipe")
    if doc.get("app") != app_id:
        errs.append(f"app must be '{app_id}'")
    up, build, target = (doc.get(k) if isinstance(doc.get(k), dict) else {} for k in ("upstream", "build", "target"))
    if not re.match(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", str(up.get("github", ""))):
        errs.append("upstream.github must be owner/repo")
    try:
        re.compile(str(up.get("tag_pattern", "")))
        if not up.get("tag_pattern"):
            errs.append("upstream.tag_pattern is required")
    except re.error:
        errs.append("upstream.tag_pattern is not a valid regular expression")
    if not IMAGE_RE.match(str(up.get("image", ""))):
        errs.append("upstream.image must be a registry/repo name without tag or digest")
    if build.get("strategy") != "overlay":
        errs.append("build.strategy must be overlay (the only strategy in this slice)")
    patch = build.get("patch") if isinstance(build.get("patch"), dict) else {}
    kinds = [k for k in ("apt", "apk") if patch.get(k)]
    if len(kinds) != 1 or set(patch) - {"apt", "apk"}:
        errs.append("build.patch needs exactly one of apt or apk: a list of packages to upgrade")
    for kind in kinds:
        pkgs = patch[kind]
        if not isinstance(pkgs, list) or not all(isinstance(p, str) and PKG_RE.match(p) for p in pkgs):
            errs.append(f"build.patch.{kind} must be a list of plain package names")
    if not USER_RE.match(str(build.get("restore_user", ""))):
        errs.append("build.restore_user is required (the user the upstream image runs as, put back after the patch)")
    if target.get("image") != f"{REGISTRY_PREFIX}{app_id}":
        errs.append(f"target.image must be {REGISTRY_PREFIX}{app_id}")
    if not re.fullmatch(r"[A-Za-z0-9._{}\-]+", str(up.get("image_tag", "{tag}"))):
        errs.append("upstream.image_tag may only use letters, digits, . _ - and the {tag} / {version} placeholders")
    days = doc.get("rebuild_after_days", DEFAULT_REBUILD_DAYS)
    if not isinstance(days, int) or not 1 <= days <= 30:
        errs.append("rebuild_after_days must be 1 to 30")
    used = {common.split_image(i)[0] for i in manifest_images(app_dir)}
    if not used & {up.get("image"), target.get("image")}:
        errs.append("no image in manifests/ is the upstream image or the target image: the recipe would change nothing")
    return errs


def upstream_ref(recipe: dict, tag: str) -> str:
    """The upstream image tag for a release tag, e.g. {tag}=v2.1.7 and image_tag '{version}' give :2.1.7."""
    up = recipe["upstream"]
    return f"{up['image']}:" + up.get("image_tag", "{tag}").format(tag=tag, version=tag.lstrip("v"))


def manifest_images(app_dir: Path) -> list[str]:
    """Every image ref written in the app's manifests folder (init containers included)."""
    refs: list[str] = []
    for f in sorted((app_dir / "manifests").glob("*.y*ml")):
        refs += re.findall(r"(?m)^\s*(?:-\s*)?image:\s*([^\s#]+)", f.read_text(encoding="utf-8"))
    return refs


def current_pin(manifest: dict) -> dict:
    """What the manifest says is deployed: upstream tag, base digest, build time, our revision (0 = never rebuilt)."""
    b = common.dig(manifest, ("metadata", "build")) or {}
    return {
        "tag": b.get("upstreamTag") or common.dig(manifest, ("metadata", "upstream", "release")),
        "base_digest": (b.get("base") or "").split("@")[-1] or None,
        "built_at": b.get("builtAt"),
        "revision": int(b.get("revision") or 0),
    }


def decide(recipe: dict, manifest: dict, latest_tag: str | None, base_digest: str | None,
           now: dt.datetime, force: bool = False) -> tuple[str, str]:
    """('rebuild'|'skip', reason). New upstream release, moved base, a week of drift, or forced."""
    pin = current_pin(manifest)
    if not latest_tag or not base_digest:
        return "skip", "no upstream release or image could be read (nothing is changed on a read failure)"
    if force:
        return "rebuild", "forced"
    if latest_tag != pin["tag"]:
        return "rebuild", f"new upstream release {latest_tag} (was {pin['tag']})"
    if pin["base_digest"] != base_digest:
        return "rebuild", "upstream re-published the same tag with a different image"
    days = recipe.get("rebuild_after_days", DEFAULT_REBUILD_DAYS)
    try:
        age = now - dt.datetime.fromisoformat(str(pin["built_at"]).replace("Z", "+00:00"))
    except ValueError:
        return "rebuild", "never built by the factory"
    if age >= dt.timedelta(days=days):
        return "rebuild", f"last build is {age.days} days old: pick up newer operating-system fixes"
    return "skip", "up to date"


def version_for(tag: str, revision: int) -> str:
    return f"{tag.lstrip('v')}+om.{revision}"


def image_tag_for(tag: str, revision: int) -> str:
    return f"{tag.lstrip('v')}-om{revision}"


def render_dockerfile(recipe: dict, base_ref: str) -> str:
    """The whole build: start from the upstream image by digest, upgrade the named packages, restore the user."""
    if "@sha256:" not in base_ref or not DIGEST_RE.match(base_ref.split("@", 1)[1]):
        raise ValueError("base_ref must be pinned by sha256 digest")
    build = recipe["build"]
    patch = build["patch"]
    if "apt" in patch:
        pkgs = " ".join(patch["apt"])
        run = ("apt-get -o Acquire::Retries=3 update && "
               f"apt-get -o Acquire::Retries=3 install -y --no-install-recommends --only-upgrade {pkgs} && "
               "rm -rf /var/lib/apt/lists/*")
    else:
        run = f"apk upgrade --no-cache {' '.join(patch['apk'])}"
    return (f"# Generated by sdk/tools/app-factory from apps/{recipe['app']}/{RECIPE_NAME}. Do not edit.\n"
            f"FROM {base_ref}\nUSER root\nRUN {run}\nUSER {build['restore_user']}\n")


def vuln_set(trivy: dict, only_fixable: bool = False) -> dict[str, dict]:
    """{CVE id + package: finding} for CRITICAL and HIGH findings in a `trivy image --format json` document."""
    out: dict[str, dict] = {}
    for res in trivy.get("Results") or []:
        for v in res.get("Vulnerabilities") or []:
            if v.get("Severity") not in ("CRITICAL", "HIGH") or (only_fixable and not v.get("FixedVersion")):
                continue
            out[f"{v['VulnerabilityID']} {v['PkgName']}"] = {
                "id": v["VulnerabilityID"], "pkg": v["PkgName"], "severity": v["Severity"],
                "fixed": v.get("FixedVersion"), "installed": v.get("InstalledVersion"),
            }
    return out


def changelog(app: str, old_tag: str, new_tag: str, old: dict, new: dict, reason: str,
              patched: list[str], base_ref: str, built_ref: str) -> str:
    """Plain-language PR text: what changed, which CVEs closed, what is still open."""
    a, b = vuln_set(old), vuln_set(new)
    closed = [a[k] for k in sorted(a) if k not in b]
    opened = [b[k] for k in sorted(b) if k not in a]
    left_fixable = [v for v in b.values() if v["fixed"] and v["severity"] == "CRITICAL"]
    line = lambda v: f"- {v['id']} ({v['severity'].lower()}) in `{v['pkg']}`" + (f", fixed in {v['fixed']}" if v["fixed"] else "")
    out = [f"## {app}: rebuilt by OneMind", "",
           f"Why now: {reason}.", "",
           f"Upstream version: {old_tag} to {new_tag}. OneMind took the upstream image `{base_ref}`, upgraded "
           f"{', '.join('`%s`' % p for p in patched)} from the operating system's security archive and pinned the result as "
           f"`{built_ref}`. Nothing else in the image was changed.", "",
           f"### Closed ({len(closed)} critical or high findings)"]
    out += [line(v) for v in closed[:40]] or ["- none"]
    if len(closed) > 40:
        out.append(f"- and {len(closed) - 40} more")
    out += ["", f"### New in this build ({len(opened)})"] + ([line(v) for v in opened[:40]] or ["- none"])
    out += ["", "### Still open that has a fix upstream",
            *([line(v) for v in left_fixable] or ["- no critical finding with a fix: the gate can pass"]), "",
            "Review: the CI gate (scan, secrets, ClamAV, install smoke test) re-ran on the rebuilt image. "
            "The tier below is what the gate computed; merging this pull request is the human approval."]
    return "\n".join(out) + "\n"


def apply_build(app_dir: Path, recipe: dict, *, upstream_tag: str, released_at: str | None, base_ref: str,
                built_ref: str, built_at: str, revision: int) -> list[str]:
    """Point every use of the app's image at the rebuilt one and record provenance. Returns the files changed."""
    up_image = recipe["upstream"]["image"]
    target = recipe["target"]["image"]
    changed = []
    for f in sorted((app_dir / "manifests").glob("*.y*ml")):
        text = f.read_text(encoding="utf-8")
        new = re.sub(rf"(?m)^(\s*(?:-\s*)?image:\s*)(?:{re.escape(up_image)}|{re.escape(target)})[:@][^\s#]+",
                     lambda m: m.group(1) + built_ref, text)
        if new != text:
            f.write_text(new, encoding="utf-8")
            changed.append(str(f))
    mf = app_dir / common.MANIFEST_NAME
    text = mf.read_text(encoding="utf-8")
    text = re.sub(r'(?m)^(  version:\s*).*$', lambda m: f'{m.group(1)}"{version_for(upstream_tag, revision)}"', text, count=1)
    text = re.sub(r"(?m)^(  upstream:\s*\{release:\s*)\"[^\"]*\"(, released_at:\s*)\"[^\"]*\"",
                  lambda m: f'{m.group(1)}"{upstream_tag}"{m.group(2)}"{released_at or common.UNVERIFIED}"', text, count=1)
    block = (f"  build:   # written by sdk/tools/app-factory; the image below is built by OneMind, not by upstream\n"
             f"    builder: {BUILDER}\n"
             f"    recipe: {RECIPE_NAME}\n"
             f"    revision: {revision}\n"
             f"    upstreamTag: \"{upstream_tag}\"\n"
             f"    base: {base_ref}\n"
             f"    patched: [{', '.join(next(iter(recipe['build']['patch'].values())))}]\n"
             f"    builtAt: \"{built_at}\"\n"
             f"    image: {built_ref}\n")
    text = re.sub(r"(?ms)^  build:.*?(?=^  \S)", "", text)           # replace an earlier block
    text = re.sub(r"(?m)^(  tier:)", lambda m: block + m.group(1), text, count=1)
    mf.write_text(text, encoding="utf-8")
    return changed + [str(mf)]
