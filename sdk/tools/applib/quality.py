# SPDX-License-Identifier: Apache-2.0
"""Quality tiers for apps and plugins (issue #174): Bronze, Silver, Gold.

The tier is never typed by a person. app-gate computes it from the evidence of its own run and writes
it into apps/<id>/scan.json under "quality" (the manifest has no such field and its schema is closed).
Each level lists named yes/no checks; a tier is the highest level whose checks, and every lower
level's, all hold. The gateway recomputes the tier from the same evidence when it reads scan.json, so
a tier that the evidence does not back is never shown.

  Bronze  fully machine-checked: the gate passed, the licence is green (L1 or L2), every image is
          clean (no fixable CRITICAL, no malware, no secret), the upstream is alive and nothing in the
          app directory says UNVERIFIED.
  Silver  tests and support duties: the smoke test really ran and passed, the app runs non-root, the
          links people need to get help are confirmed, security updates install automatically.
  Gold    supply chain and recovery: every image carries a verified cosign signature and has no
          CRITICAL at all, patch updates may be merged automatically, and the app declares how it is
          backed up.

Modelled on the Home Assistant integration quality scale (research-output/evidence/sources/W19/
ha-quality-scale.txt); the checks themselves are OneMind's, from what app-gate can prove.
"""
from __future__ import annotations

TIERS = ("none", "bronze", "silver", "gold")
LEVELS = ("bronze", "silver", "gold")

CHECKS: dict[str, tuple[str, ...]] = {
    "bronze": ("gate_pass", "licence_green", "images_clean", "upstream_alive", "nothing_unverified"),
    "silver": ("smoke_pass", "non_root", "support_links", "security_updates"),
    "gold": ("images_signed", "no_critical", "patch_automerge", "backup_declared"),
}

# What the person sees for each check, in plain words.
LABELS: dict[str, str] = {
    "gate_pass": "The app gate passed",
    "licence_green": "Licence is permissive or copyleft (L1 or L2)",
    "images_clean": "Images have no fixable CRITICAL, no malware, no secrets",
    "upstream_alive": "Upstream is not archived and released in the last 18 months",
    "nothing_unverified": "No fact in the app files is marked UNVERIFIED",
    "smoke_pass": "The smoke test ran and passed",
    "non_root": "Runs without root rights",
    "support_links": "Docs, source and support links are confirmed",
    "security_updates": "Security updates install automatically",
    "images_signed": "Every image has a verified signature",
    "no_critical": "Images have no CRITICAL vulnerability at all",
    "patch_automerge": "Patch updates are merged automatically",
    "backup_declared": "Declares how the app is backed up",
}


def _int(v: object) -> int | None:
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def images_clean(images: object) -> bool:
    """At least one image; each with zero fixable CRITICAL, zero malware from a known signature database, zero secrets."""
    if not isinstance(images, list) or not images:
        return False
    for img in images:
        if not isinstance(img, dict):
            return False
        trivy, clam = img.get("trivy"), img.get("clamav")
        trivy, clam = trivy if isinstance(trivy, dict) else {}, clam if isinstance(clam, dict) else {}
        sigs = clam.get("signatures")
        if (_int(trivy.get("critical_fixable")) != 0 or _int(clam.get("infected")) != 0 or _int(img.get("secrets")) != 0
                or not isinstance(sigs, str) or not sigs or sigs.endswith("-unknown")):
            return False
    return True


def images_signed(images: object) -> bool:
    return (isinstance(images, list) and bool(images)
            and all(isinstance(i, dict) and i.get("cosign") == "verified" for i in images))


def no_critical(images: object) -> bool:
    return (isinstance(images, list) and bool(images)
            and all(isinstance(i, dict) and isinstance(i.get("trivy"), dict) and _int(i["trivy"].get("critical")) == 0
                    for i in images))


def _confirmed(v: object) -> bool:
    return isinstance(v, str) and bool(v.strip()) and v != "UNVERIFIED"


def evidence(scan: dict, manifest: dict, facts: dict) -> dict[str, dict[str, bool]]:
    """Every check's yes/no. `facts` holds what only the live gate run knows: upstream_alive, non_root,
    nothing_unverified (all booleans; a missing one counts as no)."""
    meta = manifest.get("metadata") if isinstance(manifest.get("metadata"), dict) else {}
    spec = manifest.get("spec") if isinstance(manifest.get("spec"), dict) else {}
    links = meta.get("links") if isinstance(meta.get("links"), dict) else {}
    updates = spec.get("updates") if isinstance(spec.get("updates"), dict) else {}
    licence = scan.get("licence") if isinstance(scan.get("licence"), dict) else {}
    images = scan.get("images")

    def fact(name: str) -> bool:
        return facts.get(name) is True

    return {
        "bronze": {
            "gate_pass": scan.get("result") == "pass",
            "licence_green": licence.get("class") in ("L1", "L2"),
            "images_clean": images_clean(images),
            "upstream_alive": fact("upstream_alive"),
            "nothing_unverified": fact("nothing_unverified"),
        },
        "silver": {
            "smoke_pass": scan.get("smoke") == "pass",
            "non_root": fact("non_root"),
            "support_links": all(_confirmed(links.get(k)) for k in ("docs", "github", "support")),
            "security_updates": updates.get("channel") == "security",
        },
        "gold": {
            "images_signed": images_signed(images),
            "no_critical": no_critical(images),
            "patch_automerge": updates.get("automerge") == "patch",
            "backup_declared": isinstance(spec.get("backup"), dict) and bool(spec["backup"]),
        },
    }


def tier_of(ev: object) -> str:
    """The highest level whose checks, and all lower levels', are true. Anything malformed is 'none'."""
    if not isinstance(ev, dict):
        return "none"
    tier = "none"
    for level in LEVELS:
        row = ev.get(level)
        if not isinstance(row, dict) or any(row.get(name) is not True for name in CHECKS[level]):
            break
        tier = level
    return tier


def compute(scan: dict, manifest: dict, facts: dict) -> dict:
    """The record app-gate writes to scan.json as "quality"."""
    ev = evidence(scan, manifest, facts)
    return {"tier": tier_of(ev), "evidence": ev}


def claim_error(committed: object, computed_tier: str) -> str | None:
    """A committed scan.json may not claim a higher quality tier than the gate computes now."""
    if not isinstance(committed, dict) or not isinstance(committed.get("quality"), dict):
        return None
    claimed = committed["quality"].get("tier")
    if claimed in TIERS and TIERS.index(claimed) > TIERS.index(computed_tier):
        return f"the committed scan.json says quality '{claimed}' but the gate computes '{computed_tier}'"
    return None


def verify_record(scan: dict, manifest: dict) -> str | None:
    """Offline check of a committed record: the tier follows from its evidence, and the evidence the
    scan and manifest can reproduce equals what is written. Returns an error, or None."""
    q = scan.get("quality")
    if not isinstance(q, dict):
        return None
    ev = q.get("evidence")
    if q.get("tier") != tier_of(ev):
        return f"quality tier {q.get('tier')!r} does not follow from its evidence ({tier_of(ev)!r})"
    facts = {n: ev[lvl][n] for lvl in ("bronze", "silver") for n in ("upstream_alive", "nothing_unverified", "non_root")
             if isinstance(ev.get(lvl), dict) and n in ev[lvl]}
    again = evidence(scan, manifest, facts)
    if again != ev:
        diff = [n for lvl in LEVELS for n in CHECKS[lvl] if again[lvl][n] != (ev.get(lvl) or {}).get(n)]
        return "quality evidence differs from what scan.json and the manifest show: " + ", ".join(diff)
    return None
