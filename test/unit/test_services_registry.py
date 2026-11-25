# SPDX-License-Identifier: Apache-2.0
"""Lint (#623): no systemd unit ships without a service card.

Every unit file under os/ (.service, .socket, .timer, .path; the same set test_unit_security.py scores,
plus sockets, timers and paths) must have an entry in the services registry the image ships at
/usr/lib/onemind/services.yaml, so GET /v1/system/services and `onemind services list` can show a plain
name and description for it. A unit that is not listed would appear there as "unknown"; this test stops
it reaching the image at all. It also fails on stale entries, broken docs links, dependencies outside the
registry, and on a restart button for a unit that must never get one (rescue, first boot, host, data layout).
The field rules come from the contract, sdk/schema/onemind.services.schema.json.
"""
import glob, json, os, re, unittest

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REGISTRY = os.path.join(ROOT, "os", "rootfs", "layers", "onemind", "usr", "lib", "onemind", "services.yaml")
SCHEMA = os.path.join(ROOT, "sdk", "schema", "onemind.services.schema.json")
SUFFIXES = (".service", ".socket", ".timer", ".path")
# Units that are shown but never get a Restart button (issue #623 and its design): restarting them could
# stop the box booting, lose data, or cut off the way back in.
NEVER_RESTART = {
    "onemind-rescue.service", "onemind-firstboot.service", "onemind-host.service", "onemind-host.socket",
    "onemind-data-layout.service", "onemind-data-encrypt.service", "onemind-factory-reset.service",
    "onemind-recovery.service", "onemind-health-gate.service",
}


def shipped_units(root=ROOT):
    """Unit file names under os/, skipping wants/ links and Avahi service records (not systemd units)."""
    out = set()
    for suffix in SUFFIXES:
        for path in glob.glob(os.path.join(root, "os", "**", "*" + suffix), recursive=True):
            if os.path.islink(path) or "/avahi/" in path or not os.path.isfile(path):
                continue
            out.add(os.path.basename(path))
    return out


def load_registry(path=REGISTRY):
    with open(path) as f:
        return yaml.safe_load(f)


def problems(units, registry, schema, root=ROOT):
    """Every reason the registry does not cover `units`, as plain sentences (empty when it is good)."""
    out = []
    service = schema["$defs"]["service"]
    required = set(service["required"])
    unit_re = re.compile(schema["$defs"]["unit"]["pattern"])
    docs_re = re.compile(service["properties"]["docs"]["pattern"])
    risks = set(service["properties"]["risk"]["enum"])
    if registry.get("schema") != schema["properties"]["schema"]["const"]:
        out.append(f"registry schema is {registry.get('schema')!r}")
    entries = registry.get("services") or []
    seen = {}
    for e in entries:
        if not isinstance(e, dict):
            out.append(f"entry is not a mapping: {e!r}")
            continue
        unit = e.get("unit")
        if set(e) != required:
            out.append(f"{unit}: fields {sorted(e)} must be exactly {sorted(required)}")
        if not isinstance(unit, str) or not unit_re.match(unit):
            out.append(f"bad unit name {unit!r}")
            continue
        if unit in seen:
            out.append(f"{unit}: listed twice")
        seen[unit] = e
        if not isinstance(e.get("name"), str) or not 1 <= len(e["name"]) <= 60:
            out.append(f"{unit}: name must be 1 to 60 characters")
        if not isinstance(e.get("description"), str) or not 10 <= len(e["description"]) <= 300:
            out.append(f"{unit}: description must be 10 to 300 characters")
        if e.get("risk") not in risks:
            out.append(f"{unit}: risk {e.get('risk')!r} is not one of {sorted(risks)}")
        if not isinstance(e.get("restartable"), bool):
            out.append(f"{unit}: restartable must be true or false")
        elif e["restartable"] and (unit in NEVER_RESTART or "@." in unit):
            out.append(f"{unit}: must never be restartable")
        docs = e.get("docs")
        if not isinstance(docs, str) or not docs_re.match(docs) or not os.path.isfile(os.path.join(root, docs)):
            out.append(f"{unit}: docs page {docs!r} does not exist")
    for e in seen.values():
        for dep in e.get("depends_on") or []:
            if dep not in seen:
                out.append(f"{e['unit']}: depends on {dep}, which is not in the registry")
            if dep == e["unit"]:
                out.append(f"{dep}: depends on itself")
    for unit in sorted(units - set(seen)):
        out.append(f"{unit} ships without a service card: add it to os/rootfs/layers/onemind/usr/lib/onemind/services.yaml")
    for unit in sorted(set(seen) - units):
        out.append(f"{unit} is in the registry but no unit file under os/ has that name")
    return out


class ServicesRegistry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(SCHEMA) as f:
            cls.schema = json.load(f)
        cls.registry = load_registry()
        cls.units = shipped_units()

    def test_every_shipped_unit_has_a_card(self):
        self.assertGreater(len(self.units), 30, "the unit scan found too few units: is the glob right?")
        self.assertEqual(problems(self.units, self.registry, self.schema), [])

    def test_a_missing_unit_fails_the_lint(self):
        # The acceptance test of #623: take one entry out and the lint names the unit.
        reg = dict(self.registry, services=[e for e in self.registry["services"] if e["unit"] != "onemind-gateway.service"])
        found = problems(self.units, reg, self.schema)
        self.assertTrue(any(p.startswith("onemind-gateway.service ships without a service card") for p in found), found)

    def test_a_new_unit_file_without_an_entry_fails(self):
        found = problems(self.units | {"onemind-newthing.service"}, self.registry, self.schema)
        self.assertIn("onemind-newthing.service ships without a service card", found[-1])

    def test_never_restart_units_and_bad_fields_are_refused(self):
        bad = [dict(e) for e in self.registry["services"]]
        for e in bad:
            if e["unit"] == "onemind-rescue.service":
                e["restartable"] = True
            if e["unit"] == "onemind-nats.service":
                e["risk"], e["docs"], e["extra"] = "none", "docs/nope.md", 1
        found = "\n".join(problems(self.units, dict(self.registry, services=bad), self.schema))
        for want in ("onemind-rescue.service: must never be restartable", "onemind-nats.service: risk 'none'",
                     "onemind-nats.service: docs page 'docs/nope.md' does not exist", "onemind-nats.service: fields"):
            self.assertIn(want, found)

    def test_the_registry_ships_in_the_image_layer(self):
        # os/rootfs/Containerfile copies layers/onemind/ to /, so the file lands at /usr/lib/onemind/services.yaml,
        # the path onemindd host serve reads (internal/svcregistry.DefaultPath).
        with open(os.path.join(ROOT, "os", "rootfs", "Containerfile")) as f:
            self.assertIn("COPY os/rootfs/layers/onemind/ /", f.read())
        with open(os.path.join(ROOT, "internal", "svcregistry", "registry.go")) as f:
            self.assertIn('DefaultPath = "/usr/lib/onemind/services.yaml"', f.read())


if __name__ == "__main__":
    unittest.main()
