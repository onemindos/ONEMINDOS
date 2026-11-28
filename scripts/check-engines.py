#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Validate D-032 engine metadata and deploy image coverage, offline.

The rules come from D-032, see docs/design/ONEMIND-APPS.md section 4 (rule 3 covers
GPL/AGPL engines).
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS_AS = {"container", "debian-package", "library-in-app"}
APP_LICENCES = {
    "0BSD", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "CC0-1.0",
    "LicenseRef-Public-Domain", "MIT", "MPL-2.0",
}
TEXT_FIELDS = ("upstream", "spdx", "licence_url", "adapter", "swap_plan")
ENGINE_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
DIGEST_IMAGE = re.compile(r"(?<![\w./:-])([\w./:-]+)@sha256:[a-f0-9]{64}\b")
TAGGED_IMAGE = re.compile(
    r"""^\s*(?:image:\s*|(?:-\s+)?Image=|FROM\s+(?:--platform=\S+\s+)?)[\"']?([\w./:-]+)""",
    re.IGNORECASE | re.MULTILINE,
)
YAML_IMAGE = re.compile(r"""^[ \t]*(?:-[ \t]+)?image:[ \t]+["']?([^\s"'#]+)""", re.MULTILINE)
ENV_PIN = re.compile(r"""=(["']?)([A-Za-z0-9_./:@%+,-]*)\1(?:[ \t]+(?:#.*)?)?""")


def image_repository(reference):
    """Strip the tag without confusing it with a registry's port."""
    head, _, tail = reference.rpartition("/")
    name = (head + "/" if head else "") + tail.split(":", 1)[0]
    name = name.removeprefix("index.docker.io/").removeprefix("docker.io/")
    if "/" not in name:
        return "docker.io/library/" + name
    first = name.split("/", 1)[0]
    return name if "." in first or ":" in first or first == "localhost" else "docker.io/" + name


def deploy_images(root):
    deploy = root / "deploy"
    for path in sorted(deploy.rglob("*")):
        if not path.is_file() or not (
            path.suffix in {".yaml", ".yml", ".env", ".py", ".sh", ".toml", ".container"}
            or "Dockerfile" in path.name
        ):
            continue
        content = path.read_text(encoding="utf-8")
        references = {match.group(1) for match in DIGEST_IMAGE.finditer(content)}
        for match in TAGGED_IMAGE.finditer(content):
            reference = match.group(1)
            # Any tag counts, including codename pins and build ARGs. Images that
            # OneMind builds locally (onemind-core, onemindd) are not third-party engines.
            if ":" in reference.rsplit("/", 1)[-1] and not reference.startswith("onemind"):
                references.add(reference)
        for reference in sorted(references):
            yield path.relative_to(root), image_repository(reference)


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def string_list(value):
    return isinstance(value, list) and all(nonempty(item) for item in value)


def has_version_selector(source, selector, *, image_pin):
    content = source.read_text(encoding="utf-8")
    if source.suffix != ".env":
        if image_pin and source.suffix in {".yaml", ".yml"}:
            return any(selector in image for image in YAML_IMAGE.findall(content))
        return selector in content

    # Find assignments before validating their values so unsupported shell
    # syntax cannot be ignored in favor of a different assignment to this key.
    assignments = re.findall(
        rf"^[ \t]*(?:export[ \t]+)?{re.escape(selector)}(\+?=.*)$",
        content,
        re.MULTILINE,
    )
    value = ""
    for assignment in assignments:
        literal = ENV_PIN.fullmatch(assignment)
        if literal is None:
            return False
        value = literal.group(2)
    return bool(value)


def validate(root, register):
    if not isinstance(register, dict) or not isinstance(register.get("engines"), list):
        return ["expected an engines list"]
    errors = []
    ids = set()
    images = {}
    for entry in register["engines"]:
        engine_id = entry.get("id") if isinstance(entry, dict) else None
        if not isinstance(engine_id, str) or not ENGINE_ID.fullmatch(engine_id):
            errors.append("engine entry needs a lowercase id")
            continue
        if engine_id in ids:
            errors.append(f"{engine_id}: duplicate engine id")
        ids.add(engine_id)
        for field in TEXT_FIELDS:
            if not nonempty(entry.get(field)):
                errors.append(f"{engine_id}: missing {field}")
        primary = entry.get("runs_as")
        other = entry.get("also_runs_as", [])
        if not isinstance(primary, str) or primary not in RUNS_AS or not string_list(other) or set(other) - RUNS_AS:
            errors.append(f"{engine_id}: invalid runtime")
            continue
        runtimes = {primary, *other}
        modified = entry.get("modified")
        if type(modified) is not bool:
            errors.append(f"{engine_id}: modified must be true or false")
        used_by = entry.get("used_by")
        if not string_list(used_by) or not used_by:
            errors.append(f"{engine_id}: used_by must list app ids or platform consumers")
        planned = entry.get("planned", False)
        pin = entry.get("pinned")
        repositories = entry.get("images", [])
        if type(planned) is not bool or not string_list(repositories):
            errors.append(f"{engine_id}: invalid planned flag or image list")
            continue
        if planned:
            if pin is not None or repositories:
                errors.append(f"{engine_id}: planned engine cannot declare a deployment pin or image")
        elif not isinstance(pin, dict) or not all(nonempty(pin.get(key)) for key in ("source", "selector")):
            errors.append(f"{engine_id}: pinned must name a repository source and selector")
        else:
            source = (root / pin["source"]).resolve()
            if not source.is_relative_to(root.resolve()) or not source.is_file():
                errors.append(f"{engine_id}: pinned source does not exist in the repository")
            elif not has_version_selector(source, pin["selector"], image_pin=bool(repositories)):
                errors.append(f"{engine_id}: version selector is missing from {pin['source']}")
        spdx = entry.get("spdx")
        if not nonempty(spdx):
            continue
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9.-]*", spdx):
            errors.append(f"{engine_id}: expected one SPDX id")
        if "library-in-app" in runtimes and spdx not in APP_LICENCES and not (planned and spdx == "UNVERIFIED"):
            errors.append(f"{engine_id}: D-032 forbids {spdx} in app binaries")
        if re.match(r"A?GPL-", spdx, re.IGNORECASE):
            if runtimes != {"container"} or not nonempty(entry.get("protocol")):
                errors.append(f"{engine_id}: GPL/AGPL requires its own container and a standard protocol")
            if modified is True and not nonempty(entry.get("fork_repo")):
                errors.append(f"{engine_id}: modified GPL/AGPL engine is missing fork_repo")
        for repository in repositories:
            if "container" not in runtimes:
                errors.append(f"{engine_id}: image requires a container runtime")
            name = image_repository(repository)
            if name in images:
                errors.append(f"{engine_id}: {name} is already listed by {images[name]}")
            images[name] = engine_id
    for path, repository in deploy_images(root):
        if repository not in images:
            errors.append(f"{path}: pinned image {repository} is missing from the engine register")
    return errors


def main():
    try:
        # JSON is a YAML 1.2 subset. Lint can read this register with Python's standard library.
        register = json.loads((ROOT / "deploy/engines.yaml").read_text(encoding="utf-8"))
        errors = validate(ROOT, register)
    except (OSError, ValueError) as exc:
        errors = [str(exc)]
    if errors:
        print("\n".join(f"engine register: {error}" for error in errors), file=sys.stderr)
        return 1
    print(f"engine register: {len(register['engines'])} entries and deploy images checked")
    return 0


if __name__ == "__main__":
    sys.exit(main())
