# SPDX-License-Identifier: Apache-2.0
"""One streaming runtime for desktop apps (issue #786): the shared base, the app rules and the bake-off logic.

Covers apps/_bases/desktop (pinned Debian 13, uid 1000, SBOM, scan, notices), the refusals (root or privileged
images, a second runtime), the runtime-login switch that is allowed only when the gateway's own NetworkPolicies
admit the gateway alone, and test/gui/bakeoff.py's verdict and runtime order. No network and no docker.
Run: python3 -I -m unittest discover -s sdk/tools/tests -v
"""
from __future__ import annotations

import copy
import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TOOLS = Path(__file__).resolve().parents[1]
ROOT = TOOLS.parents[1]
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(ROOT / "core"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml  # noqa: E402

from factorylib import desktop  # noqa: E402
from onemind_core import policy as gw  # noqa: E402
from test_app_tools import load_tool  # noqa: E402

BASE_DIR = ROOT / "apps" / "_bases" / "desktop"
GUI = ROOT / "test" / "gui"
RULES = gw.load_rules(ROOT / "sdk" / "policy" / "app-objects.yaml")
validate = load_tool("validate-apps")
factory_cli = load_tool("app-factory")


def load_bakeoff():
    import importlib.machinery
    import importlib.util
    loader = importlib.machinery.SourceFileLoader("bakeoff", str(GUI / "bakeoff.py"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


bakeoff = load_bakeoff()


def base_doc() -> dict:
    return yaml.safe_load((BASE_DIR / "base.yaml").read_text(encoding="utf-8"))


def firefox() -> tuple[dict, list[dict]]:
    """apps/firefox as validate-apps sees it: the manifest and its Kubernetes objects."""
    app = ROOT / "apps" / "firefox"
    objs = []
    for f in sorted((app / "manifests").glob("*.yaml")):
        if f.name != "kustomization.yaml":
            objs += [o for o in yaml.safe_load_all(f.read_text(encoding="utf-8")) if isinstance(o, dict)]
    return yaml.safe_load((app / "onemind.app.yaml").read_text(encoding="utf-8")), objs


def deployment(objs: list[dict]) -> dict:
    return next(o for o in objs if o["kind"] == "Deployment")


def login_off(objs: list[dict]) -> list[dict]:
    """The same app with Neko's own login switched off (the noauth member provider)."""
    objs = copy.deepcopy(objs)
    env = deployment(objs)["spec"]["template"]["spec"]["containers"][0]["env"]
    env[:] = [e for e in env if not e["name"].startswith("NEKO_MEMBER")] + [{"name": "NEKO_MEMBER_PROVIDER", "value": "noauth"}]
    return objs


class BaseTests(unittest.TestCase):
    def test_shipped_desktop_base_is_valid(self):
        self.assertEqual(desktop.validate_base(base_doc(), BASE_DIR), [])

    def test_base_facts(self):
        doc = base_doc()
        self.assertEqual(doc["os"], "debian-13")                       # D-007
        self.assertEqual(doc["user"]["uid"], 1000)
        self.assertEqual(doc["runtime"]["name"], "neko")              # tried first
        self.assertEqual(doc["runtime"]["licence"], "Apache-2.0")
        self.assertRegex(doc["from"], r"^ghcr\.io/m1k1o/neko/base:3\.2\.0@sha256:[0-9a-f]{64}$")
        self.assertTrue(doc["build"]["sbom"] and doc["build"]["scan"])
        self.assertTrue((BASE_DIR / doc["build"]["notices"]).is_file())

    def test_refuses_a_bad_recipe(self):
        cases = {
            "user.uid": lambda d: d["user"].update(uid=0),
            "os must be debian-13": lambda d: d.update(os="debian-12"),
            "one streaming runtime only": lambda d: d.update(runtime=[d["runtime"], {"name": "selkies"}]),
            "runtime.name": lambda d: d["runtime"].update(name="kasmvnc"),
            "runtime.licence": lambda d: d["runtime"].update(licence="GPL-3.0-only"),
            "from must be": lambda d: d.update(**{"from": "ghcr.io/m1k1o/neko/base:latest"}),
            "build.sbom": lambda d: d["build"].update(sbom=False),
            "build.notices": lambda d: d["build"].update(notices="../../LICENSE"),
            "target.image": lambda d: d["target"].update(image="docker.io/someone/desktop"),
        }
        for want, change in cases.items():
            with self.subTest(want=want):
                doc = base_doc()
                change(doc)
                self.assertTrue(any(want in e for e in desktop.validate_base(doc, BASE_DIR)), want)

    def test_base_check_cli(self):
        self.assertEqual(factory_cli.main(["base-check"]), 0)
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "desktop"
            shutil.copytree(BASE_DIR, bad)
            text = (bad / "Dockerfile").read_text(encoding="utf-8")
            (bad / "Dockerfile").write_text(text.replace("USER 1000:1000\nCMD", "USER root\nCMD"), encoding="utf-8")
            with mock.patch.object(desktop, "BASES_DIR", Path(tmp)):
                self.assertEqual(factory_cli.main(["base-check", "desktop"]), 1)

    def test_build_command_carries_sbom_and_provenance_when_pushed(self):
        doc = base_doc()
        argv = desktop.build_command(doc, BASE_DIR, Path("/out"), True, "2026.11.21")
        self.assertIn("--sbom=true", argv)
        self.assertIn("--provenance=mode=max", argv)
        self.assertIn("--platform", argv)
        self.assertEqual(argv[argv.index("--platform") + 1], "linux/amd64,linux/arm64")
        self.assertIn("ghcr.io/onemindos/bases/desktop:2026.11.21", argv)

    def test_built_image_identity(self):
        trixie = 'PRETTY_NAME="Debian GNU/Linux 13 (trixie)"\nID=debian\nVERSION_ID="13"\n'
        self.assertEqual(desktop.check_identity(trixie, "1000\n"), [])
        self.assertTrue(desktop.check_identity(trixie.replace('"13"', '"12"'), "1000"))
        self.assertTrue(desktop.check_identity(trixie, "0"))


class DockerfileTests(unittest.TestCase):
    def setUp(self):
        self.doc = base_doc()
        self.text = (BASE_DIR / "Dockerfile").read_text(encoding="utf-8")

    def problems(self, text: str) -> list[str]:
        return desktop.dockerfile_problems(text, self.doc)

    def test_shipped_dockerfiles_pass(self):
        self.assertEqual(self.problems(self.text), [])
        # The Obsidian bake-off image builds on the base: no doc (its FROM is an ARG), same image rules.
        self.assertEqual(desktop.dockerfile_problems((GUI / "obsidian" / "Dockerfile").read_text(encoding="utf-8")), [])

    def test_refuses_root_privileged_sudo_setuid_and_a_second_runtime(self):
        cases = {
            "must not end as root": self.text.replace("USER 1000:1000\nCMD", "USER root\nCMD"),
            "privileged": self.text.replace("RUN set -eux;", "RUN --security=insecure set -eux;", 1),
            "sudo": self.text.replace("install -y --no-install-recommends openbox", "install -y --no-install-recommends openbox sudo"),
            "setuid": self.text.replace("chmod 0700 /tmp/runtime-neko", "chmod u+s /usr/bin/X"),
            "second streaming runtime (selkies)": self.text.replace("openbox;", "openbox selkies-gstreamer;"),
            "second streaming runtime (xpra)": self.text.replace("openbox;", "openbox xpra;"),
            "exactly one FROM": "FROM debian:trixie-slim AS x\n" + self.text,
            "COPY NOTICES.md": self.text.replace("COPY NOTICES.md", "COPY OTHER.md"),
        }
        for want, text in cases.items():
            with self.subTest(want=want):
                self.assertNotEqual(text, self.text)
                self.assertTrue(any(want in e for e in self.problems(text)), (want, self.problems(text)))

    def test_vendor_file_is_never_committed(self):
        obs = (GUI / "obsidian" / "Dockerfile").read_text(encoding="utf-8")
        self.assertRegex(obs, r"OBSIDIAN_SHA256=[0-9a-f]{64}")      # fetched at build, checked against GitHub's digest
        self.assertIn("sha256sum -c", obs)
        for p in ROOT.joinpath("test", "gui").rglob("*"):
            self.assertNotRegex(p.name.lower(), r"\.(deb|appimage|snap|rpm|tar\.gz)$")


class StreamRuleTests(unittest.TestCase):
    def setUp(self):
        self.manifest, self.objs = firefox()

    def check(self, objs, manifest=None, dependents=None, rules=RULES):
        return desktop.stream_problems(objs, "firefox", manifest or self.manifest, rules, dependents or set())

    def test_shipped_browser_apps_pass(self):
        self.assertEqual(self.check(self.objs), [])

    def test_refuses_root_privileged_and_added_capabilities(self):
        def pod(objs):
            return deployment(objs)["spec"]["template"]["spec"]
        cases = {
            "runAsNonRoot": lambda o: pod(o)["securityContext"].update(runAsNonRoot=False, runAsUser=0),
            "root, privileged": lambda o: pod(o)["containers"][0]["securityContext"].update(privileged=True),
            "privilege escalation": lambda o: pod(o)["containers"][0]["securityContext"].update(allowPrivilegeEscalation=True),
            "adding capabilities": lambda o: pod(o)["containers"][0]["securityContext"].update(capabilities={"add": ["SYS_ADMIN"]}),
        }
        for want, change in cases.items():
            with self.subTest(want=want):
                objs = copy.deepcopy(self.objs)
                change(objs)
                self.assertTrue(any(want in e for e in self.check(objs)), want)

    def test_refuses_a_second_runtime(self):
        objs = copy.deepcopy(self.objs)
        pod = deployment(objs)["spec"]["template"]["spec"]
        side = copy.deepcopy(pod["containers"][0])
        side.update(name="xpra", image=f"docker.io/example/xpra:6.3@sha256:{'c' * 64}", env=[{"name": "XPRA_PORT", "value": "14500"}])
        pod["containers"].append(side)
        self.assertTrue(any("one streaming runtime per app" in e for e in self.check(objs)))

    def test_login_off_is_allowed_behind_the_gateway_policy_alone(self):
        self.assertEqual(self.check(login_off(self.objs)), [])

    def test_login_off_without_the_gateway_policy_is_refused(self):
        errs = desktop.stream_problems(login_off(self.objs), "firefox", self.manifest, None)
        self.assertTrue(any("login is off" in e for e in errs))

    def test_login_off_refused_when_the_gateway_would_admit_more(self):
        real = gw.network_policies

        def wider(*a, **k):
            out = real(*a, **k)
            out[1]["spec"]["ingress"].append({"from": [{"ipBlock": {"cidr": "0.0.0.0/0"}}]})   # everyone
            return out
        with mock.patch.object(gw, "network_policies", wider):
            errs = self.check(login_off(self.objs))
        self.assertTrue(any("0.0.0.0/0" in e for e in errs), errs)
        with mock.patch.object(gw, "network_policies", wider):
            self.assertEqual(self.check(self.objs), [])                 # with its own login on, the wider rule is not this check

    def test_login_off_refused_with_another_path_in(self):
        objs = login_off(self.objs)
        two = copy.deepcopy(objs)
        extra = copy.deepcopy(deployment(two))
        extra["metadata"]["name"] = "helper"
        extra["spec"]["template"]["spec"]["containers"][0]["env"] = []
        two.append(extra)
        own_policy = copy.deepcopy(objs) + [{"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy",
                                             "metadata": {"name": "mine"}, "spec": {"podSelector": {}}}]
        replicas = copy.deepcopy(objs)
        deployment(replicas)["spec"]["replicas"] = 2
        cases = {
            "depending on it (notes-app)": (objs, self.manifest, {"notes-app"}),
            "ship its own ingress rules": (own_policy, self.manifest, set()),
            "podSelector": (two, self.manifest, set()),
            "podSelector ": (replicas, self.manifest, set()),
            "hostPorts": (objs, {**self.manifest, "spec": {**self.manifest["spec"], "hostPorts": [{"port": 8080}]}}, set()),
        }
        for want, (o, m, deps) in cases.items():
            with self.subTest(want=want):
                errs = self.check(o, m, deps)
                self.assertTrue(any(want.strip() in e for e in errs), errs)

    def test_validate_apps_finds_dependents(self):
        with tempfile.TemporaryDirectory() as tmp:
            for app, deps in {"notes": [{"id": "firefox"}], "other": [{"id": "x", "alternatives": ["firefox"]}], "alone": None}.items():
                (Path(tmp) / app).mkdir()
                spec = {"dependencies": deps} if deps else {}
                (Path(tmp) / app / "onemind.app.yaml").write_text(yaml.safe_dump({"spec": spec}), encoding="utf-8")
            got = validate.dependents_map(validate.all_app_dirs(Path(tmp)))
        self.assertEqual(got["firefox"], {"notes", "other"})
        self.assertEqual(got["x"], {"other"})


class ReviewProbeTests(unittest.TestCase):
    """The independent review's probes on PR 799: each was a way past check 12."""

    def setUp(self):
        self.manifest, self.objs = firefox()

    def check(self, objs, manifest=None, dependents=None, rules=RULES):
        return desktop.stream_problems(objs, "firefox", manifest or self.manifest, rules, dependents or set())

    def env(self, objs) -> list[dict]:
        return deployment(objs)["spec"]["template"]["spec"]["containers"][0]["env"]

    def test_the_only_allowed_runtime_is_the_bases(self):
        self.assertEqual(desktop.base_runtime(), base_doc()["runtime"]["name"])
        for other in ("selkies", "xpra"):
            with self.subTest(other=other):
                objs = copy.deepcopy(self.objs)
                c = deployment(objs)["spec"]["template"]["spec"]["containers"][0]
                c["image"] = f"ghcr.io/linuxserver/{other}:1.0@sha256:{'d' * 64}"
                c["env"] = [{"name": f"{other.upper()}_PORT", "value": "8080"}]
                for manifest in (self.manifest, {**self.manifest, "spec": {**self.manifest["spec"], "desktop": {"runtime": other}}}):
                    errs = self.check(objs, manifest)
                    self.assertTrue(any(f"streaming runtime {other} is refused" in e for e in errs), errs)
        # A different base runtime moves the allowed one: neko is then refused.
        self.assertTrue(any("runtime neko is refused" in e for e in
                            desktop.stream_problems(self.objs, "firefox", self.manifest, RULES, set(), runtime="selkies")))

    def test_login_off_through_a_reference_fails_closed(self):
        cm = {"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "neko-env"}, "data": {"NEKO_MEMBER_PROVIDER": "noauth"}}
        cases = {}
        o = copy.deepcopy(self.objs)                                           # probe B: envFrom a ConfigMap it ships
        self.env(o)[:] = [e for e in self.env(o) if e["name"] != "NEKO_MEMBER_PROVIDER"]
        deployment(o)["spec"]["template"]["spec"]["containers"][0]["envFrom"] = [{"configMapRef": {"name": "neko-env"}}]
        cases["envFrom ConfigMap"] = o + [cm]
        p = copy.deepcopy(o)                                                   # the same key through a prefix
        deployment(p)["spec"]["template"]["spec"]["containers"][0]["envFrom"] = [{"prefix": "NEKO_", "configMapRef": {"name": "neko-env"}}]
        cases["envFrom prefix"] = p + [{**cm, "data": {"MEMBER_PROVIDER": "noauth"}}]
        q = copy.deepcopy(o)                                                   # a ConfigMap or Secret it does not ship
        deployment(q)["spec"]["template"]["spec"]["containers"][0]["envFrom"] = [{"secretRef": {"name": "elsewhere"}}]
        cases["envFrom Secret"] = q
        d = copy.deepcopy(self.objs)                                           # probe D: valueFrom
        for e in self.env(d):
            if e["name"] == "NEKO_MEMBER_PROVIDER":
                e.pop("value")
                e["valueFrom"] = {"configMapKeyRef": {"name": "neko-env", "key": "NEKO_MEMBER_PROVIDER"}}
        cases["valueFrom"] = d + [cm]
        m = copy.deepcopy(self.objs)                                           # a mounted Neko config file
        pod = deployment(m)["spec"]["template"]["spec"]
        pod["volumes"].append({"name": "conf", "configMap": {"name": "neko-yaml"}})
        pod["containers"][0]["volumeMounts"].append({"name": "conf", "mountPath": "/etc/neko/neko.yaml", "subPath": "neko.yaml"})
        cases["mounted /etc/neko"] = m + [{"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "neko-yaml"},
                                            "data": {"neko.yaml": "member:\n  provider: multiuser\n"}}]
        f = copy.deepcopy(self.objs)                                           # the flag inside the shipped supervisord.conf
        for obj in f:
            if obj["kind"] == "ConfigMap":
                obj["data"]["supervisord.conf"] = obj["data"]["supervisord.conf"].replace(
                    "neko serve", "neko serve --member.provider noauth")
        cases["noauth in a mounted ConfigMap"] = f
        a = copy.deepcopy(self.objs)
        deployment(a)["spec"]["template"]["spec"]["containers"][0]["args"] = ["--member.provider=noauth"]
        cases["noauth flag"] = a
        for want, objs in cases.items():
            with self.subTest(want=want):
                self.assertTrue(any("login is off, but apps depending on it" in e for e in
                                    self.check(objs, dependents={"notes-app"})), want)
                self.assertTrue(any("login is off and the gateway's policy is unknown" in e for e in
                                    desktop.stream_problems(objs, "firefox", self.manifest, None)), want)
                self.assertEqual(self.check(objs), [], want)                # behind the gateway alone it is still allowed
        self.assertEqual(self.check(self.objs, dependents={"notes-app"}), [])   # login on: dependents are fine

    def test_a_desktop_is_known_by_the_base_not_by_its_name(self):
        objs = copy.deepcopy(self.objs)
        pod = deployment(objs)["spec"]["template"]["spec"]
        c = pod["containers"][0]
        c["image"] = f"ghcr.io/onemindos/apps/notes-desktop:1.0@sha256:{'e' * 64}"   # built FROM the base, no NEKO_ env
        c["env"] = []
        pod["securityContext"].update(runAsUser=0, runAsNonRoot=False)               # probe C
        manifest = {**self.manifest, "spec": {**self.manifest["spec"], "desktop": {"runtime": "neko", "base": "desktop"}}}
        errs = self.check(objs, manifest)
        self.assertTrue(any("runAsNonRoot" in e for e in errs), errs)
        bare = {**self.manifest, "spec": {k: v for k, v in self.manifest["spec"].items() if k != "desktop"}}
        self.assertEqual(self.check(objs, bare), [])                                # no field, no base image: invisible
        c["image"] = f"ghcr.io/onemindos/bases/desktop:local@sha256:{'e' * 64}"
        errs = self.check(objs, bare)
        self.assertTrue(any("declare spec.desktop" in e for e in errs), errs)
        self.assertTrue(any("runAsNonRoot" in e for e in errs), errs)
        self.assertTrue(any("declare spec.desktop" in e for e in self.check(self.objs, bare)))   # a Neko image too

    def test_base_labels_mark_every_image_built_from_it(self):
        doc = base_doc()
        good = {desktop.BASE_LABEL: "desktop", desktop.RUNTIME_LABEL: doc["runtime"]["name"]}
        self.assertTrue(desktop.image_is_desktop(good))
        self.assertFalse(desktop.image_is_desktop({}))
        self.assertEqual(desktop.label_problems(good, doc), [])
        self.assertTrue(desktop.label_problems({desktop.BASE_LABEL: "desktop"}, doc))
        text = (BASE_DIR / "Dockerfile").read_text(encoding="utf-8")
        self.assertTrue(any("com.onemindos.base" in e for e in desktop.dockerfile_problems(
            text.replace('com.onemindos.base="desktop"', 'com.onemindos.base="other"'), doc)))

    def test_schema_and_shipped_apps_declare_the_desktop(self):
        schema = json.loads((ROOT / "sdk" / "schema" / "onemind.app.schema.json").read_text(encoding="utf-8"))
        field = schema["properties"]["spec"]["properties"]["desktop"]
        self.assertEqual(field["required"], ["runtime"])
        self.assertEqual(set(field["properties"]["runtime"]["enum"]), set(desktop.RUNTIME_ORDER))
        for app in ("firefox", "chromium"):
            doc = yaml.safe_load((ROOT / "apps" / app / "onemind.app.yaml").read_text(encoding="utf-8"))
            self.assertEqual(doc["spec"]["desktop"], {"runtime": desktop.base_runtime()})


class CiTests(unittest.TestCase):
    def test_ci_apps_runs_the_base_check_and_watches_what_check_12_reads(self):
        wf = yaml.safe_load((ROOT / ".github" / "workflows" / "ci-apps.yml").read_text(encoding="utf-8"))
        paths = (wf.get("on") or wf[True])["pull_request"]["paths"]
        for p in ("test/gui/**", "core/onemind_core/policy.py", "core/onemind_core/sections.py", "sdk/policy/app-objects.yaml"):
            self.assertIn(p, paths)
        runs = [s.get("run", "") for s in wf["jobs"]["validate"]["steps"]]
        self.assertIn("python3 -I sdk/tools/app-factory base-check", runs)


class BakeoffTests(unittest.TestCase):
    def result(self, runtime, passed=True, **checks):
        c = {k: passed for k in bakeoff.CHECKS}
        c.update(checks)
        return {"schema": bakeoff.SCHEMA, "runtime": runtime, "checks": c}

    def test_every_check_is_in_the_run(self):
        self.assertEqual(bakeoff.CHECKS, ("stream", "clipboard_to_desktop", "clipboard_from_desktop", "audio", "resize", "reconnect"))

    def test_verdict_needs_every_check(self):
        self.assertTrue(bakeoff.verdict(self.result("neko")["checks"]))
        self.assertFalse(bakeoff.verdict(self.result("neko", audio=False)["checks"]))
        missing = self.result("neko")["checks"]
        del missing["reconnect"]
        self.assertFalse(bakeoff.verdict(missing))

    def test_runtime_order_neko_then_selkies_then_xpra(self):
        pick = bakeoff.pick_runtime
        self.assertEqual(pick([self.result("neko")]), "neko")
        self.assertEqual(pick([self.result("neko"), self.result("selkies")]), "neko")
        self.assertIsNone(pick([self.result("selkies")]))               # Neko was never tried
        self.assertEqual(pick([self.result("neko", clipboard_from_desktop=False), self.result("selkies")]), "selkies")
        self.assertIsNone(pick([self.result("neko", False), self.result("xpra")]))
        self.assertEqual(pick([self.result("neko", False), self.result("selkies", False), self.result("xpra")]), "xpra")
        with self.assertRaises(ValueError):
            pick([{"schema": "x", "runtime": "kasmvnc"}])

    def test_pick_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "neko.json"
            f.write_text(json.dumps(self.result("neko", resize=False)), encoding="utf-8")
            self.assertEqual(bakeoff.main(["pick", str(f)]), 1)
            f.write_text(json.dumps(self.result("neko")), encoding="utf-8")
            self.assertEqual(bakeoff.main(["pick", str(f)]), 0)

    def test_percentile(self):
        self.assertIsNone(bakeoff.percentile([], 50))
        self.assertEqual(bakeoff.percentile([3.0, 1.0, 2.0, None], 50), 2.0)
        self.assertEqual(bakeoff.percentile([float(i) for i in range(1, 101)], 95), 95.0)

    def test_run_refuses_a_driverless_runtime_and_needs_no_password_flag(self):
        src = (GUI / "bakeoff.py").read_text(encoding="utf-8")
        self.assertNotIn("--password", src)                            # the password comes from the environment
        self.assertTrue(re.search(r"BAKEOFF_PASSWORD", src))


if __name__ == "__main__":
    unittest.main()
