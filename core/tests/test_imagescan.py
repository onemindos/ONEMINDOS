# SPDX-License-Identifier: Apache-2.0
"""On-box image scan (CORE-DEPLOY-2): the Job documents, Trivy's answer, the verdict, and the wiring.

kubectl is a fake that records every call and answers `logs` with a Trivy report chosen by image.
The real-cluster test at the bottom runs only when ONEMIND_SCAN_IT=1 (a box with k3s and internet).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime, timedelta, timezone

import pytest
import yaml

from onemind_core.appstore import imagescan as im
from onemind_core.appstore.sources import NoImageScanner
from onemind_core.scan import read_scan, scan_problem

D1 = "sha256:" + "a" * 64
D2 = "sha256:" + "b" * 64
VULN = f"registry.example.org/lab/vulnerable:1@{D1}"
CLEAN = f"registry.example.org/lab/clean:1@{D2}"
NOW = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)


def report(*, critical_fixed=0, critical_unfixed=0, high=0, secrets=0) -> str:
    vulns = [{"VulnerabilityID": f"CVE-1-{i}", "PkgName": "p", "InstalledVersion": "1", "Severity": "CRITICAL",
              "FixedVersion": "2"} for i in range(critical_fixed)]
    vulns += [{"VulnerabilityID": f"CVE-2-{i}", "PkgName": "q", "InstalledVersion": "1", "Severity": "CRITICAL"}
              for i in range(critical_unfixed)]
    vulns += [{"VulnerabilityID": f"CVE-3-{i}", "PkgName": "r", "InstalledVersion": "1", "Severity": "HIGH"}
              for i in range(high)]
    res = [{"Target": "os", "Vulnerabilities": vulns}]
    if secrets:
        res.append({"Target": "app/.env", "Secrets": [{"RuleID": "aws", "StartLine": n} for n in range(secrets)]})
    return json.dumps({"SchemaVersion": 2, "Results": res})


class FakeKubectl:
    def __init__(self, reports: dict[str, str] | None = None):
        self.reports = reports or {VULN: report(critical_fixed=2, high=5), CLEAN: report(critical_unfixed=1, high=3)}
        self.calls: list[list[str]] = []
        self.jobs: dict[str, dict] = {}
        self.fail_scan_with: str | None = None  # a scan Job that does not complete; this is its log
        self.signed: set[str] = set()
        self.fail_kinds: set[str] = set()  # Job kinds whose Job does not complete (e.g. {"dbsync"})

    def __call__(self, argv, input=None, **kw):
        self.calls.append(list(argv))
        verb = argv[1]
        out, err, rc = "", "", 0
        if verb == "create":
            doc = yaml.safe_load(input)
            self.jobs[doc["metadata"]["name"]] = doc
        elif verb == "get":
            doc = self.jobs[argv[argv.index("-n") + 2].split("/")[1]]
            kind = doc["metadata"]["labels"]["app.kubernetes.io/component"]
            failed = kind in self.fail_kinds or (kind == "scan" and self.fail_scan_with is not None) or (
                kind == "cosign" and doc["spec"]["template"]["spec"]["containers"][0]["args"][-1] not in self.signed)
            out = "/1" if failed else "1/"
        elif verb == "wait":
            # The old code waited for "complete"; a failed Job never gets there, so this would hang.
            raise subprocess.TimeoutExpired(argv, 1500)
        elif verb == "logs":
            doc = self.jobs[argv[argv.index("-n") + 2].split("/")[1]]
            c = doc["spec"]["template"]["spec"]["containers"][0]
            if c["name"] == "scan":
                out = self.fail_scan_with if self.fail_scan_with is not None else self.reports[c["args"][-1]]
        return subprocess.CompletedProcess(argv, rc, out, err)

    def verbs(self):
        return [c[1] for c in self.calls]


def scanner(fake: FakeKubectl, **kw) -> im.KubeJobImageScanner:
    kw.setdefault("poll_s", 0)
    return im.KubeJobImageScanner(kubectl="kubectl", runner=fake, **kw)


# ---- the acceptance test: known-vulnerable image fails, clean image passes -----------------------

def test_vulnerable_image_fails_and_clean_image_passes():
    fake = FakeKubectl()
    s = scanner(fake)
    result, detail = s.scan([VULN])
    assert result == "fail" and "2 fixable CRITICAL" in detail
    result, detail = s.scan([CLEAN])  # a CRITICAL without a fix does not fail (same rule as app-gate)
    assert result == "pass", detail


def test_one_bad_image_fails_the_whole_app():
    assert scanner(FakeKubectl()).scan([CLEAN, VULN])[0] == "fail"


def test_secret_in_an_image_fails():
    fake = FakeKubectl({CLEAN: report(secrets=1)})
    assert scanner(fake).scan([CLEAN])[0] == "fail"


def test_an_app_with_no_images_passes_without_running_anything():
    fake = FakeKubectl()
    assert scanner(fake).scan([])[0] == "pass" and fake.calls == []


# ---- anything that goes wrong is "unavailable", never "pass" -------------------------------------

@pytest.mark.parametrize("log", ["", "no json here", "{not json", '{"x": 1}'])
def test_unreadable_scanner_output_is_unavailable(log):
    fake = FakeKubectl({CLEAN: log})
    result, _ = scanner(fake).scan([CLEAN])
    assert result == "unavailable"


def test_job_that_does_not_finish_is_unavailable():
    fake = FakeKubectl()
    fake.fail_scan_with = "FATAL timeout"
    result, detail = scanner(fake).scan([CLEAN])
    assert result == "unavailable" and "did not finish" in detail


def test_failed_job_returns_at_once_instead_of_waiting_out_the_timeout():
    import time

    fake = FakeKubectl()
    fake.fail_scan_with = "FATAL boom"
    s = scanner(fake)
    doc = im.job_doc("scan-x", "scan", im.TRIVY_IMAGE, im.trivy_scan_args(CLEAN), deadline_s=1500)
    t0 = time.monotonic()
    ok, out = s._run_job(doc, 1500)
    assert time.monotonic() - t0 < 2 and ok is False and "boom" in out
    assert "wait" not in fake.verbs()


def test_a_vanished_job_is_an_error_not_a_pass():
    class Gone(FakeKubectl):
        def __call__(self, argv, input=None, **kw):
            if argv[1] == "get":
                return subprocess.CompletedProcess(argv, 1, "", 'Error from server (NotFound): jobs "x" not found')
            return super().__call__(argv, input, **kw)

    assert scanner(Gone()).scan([CLEAN])[0] == "unavailable"


def test_a_job_that_never_ends_stops_at_the_overall_deadline():
    class Pending(FakeKubectl):
        def __call__(self, argv, input=None, **kw):
            if argv[1] == "get":
                return subprocess.CompletedProcess(argv, 0, "/", "")
            return super().__call__(argv, input, **kw)

    ticks = iter(range(0, 10_000, 100))
    s = im.KubeJobImageScanner(runner=Pending(), poll_s=0, _clock=lambda: next(ticks), _sleep=lambda _s: None)
    doc = im.job_doc("scan-x", "scan", im.TRIVY_IMAGE, im.trivy_scan_args(CLEAN), deadline_s=300)
    ok, _ = s._run_job(doc, 300)
    assert ok is False


def test_first_use_with_no_database_goes_straight_to_the_sync_and_is_fast():
    import time

    class NoDb(FakeKubectl):
        synced = False

        def __call__(self, argv, input=None, **kw):
            if argv[1] == "create":
                self.synced = self.synced or yaml.safe_load(input)["metadata"]["labels"]["app.kubernetes.io/component"] == "dbsync"
            self.fail_scan_with = None if self.synced else "FATAL --skip-db-update cannot be specified on the first run"
            return super().__call__(argv, input, **kw)

    fake = NoDb()
    t0 = time.monotonic()
    assert scanner(fake, cosign=False).scan([CLEAN])[0] == "pass"
    assert time.monotonic() - t0 < 2 and "wait" not in fake.verbs()


def test_a_nonexistent_digest_is_unavailable_quickly_and_does_not_start_a_sync():
    import time

    fake = FakeKubectl()
    fake.fail_scan_with = "FATAL unable to find the specified image: manifest unknown (registry.example.org/lab/mydb)"
    s = scanner(fake)
    t0 = time.monotonic()
    result, detail = s.scan([CLEAN])
    assert result == "unavailable" and "did not finish" in detail and time.monotonic() - t0 < 2
    assert not any(c.get("metadata", {}).get("labels", {}).get("app.kubernetes.io/component") == "dbsync"
                   for c in fake.jobs.values())
    # the lock was released: the next scan of a good image is not blocked
    fake.fail_scan_with = None
    assert s.scan([CLEAN])[0] == "pass"


def test_unsigned_image_is_a_quick_normal_result():
    fake = FakeKubectl()  # nothing is signed
    result, _ = scanner(fake).scan([CLEAN])
    assert result == "pass" and "wait" not in fake.verbs()


def test_missing_kubectl_is_unavailable():
    def boom(argv, **kw):
        raise FileNotFoundError(argv[0])

    assert im.KubeJobImageScanner(runner=boom).scan([CLEAN])[0] == "unavailable"


@pytest.mark.parametrize("ref", [
    "registry.example.org/x:1", "x@sha256:abc", "registry.example.org/x@sha256:" + "a" * 64 + " --foo",
    "-v/etc:/x@sha256:" + "a" * 64, "x;rm@sha256:" + "a" * 64,
])
def test_only_digest_pinned_plain_references_reach_a_command_line(ref):
    fake = FakeKubectl()
    assert scanner(fake).scan([ref])[0] == "unavailable"
    assert fake.calls == []


def test_first_use_syncs_the_pinned_database_once_then_scans_offline():
    class NoDbYet(FakeKubectl):
        synced = False
        created: list[str]

        def __call__(self, argv, input=None, **kw):
            if argv[1] == "create":
                kind = yaml.safe_load(input)["metadata"]["labels"]["app.kubernetes.io/component"]
                self.created.append(kind)
                self.synced = self.synced or kind == "dbsync"
            # Until the database is synced, an offline scan job dies with Trivy's real complaint.
            self.fail_scan_with = None if self.synced else "FATAL --skip-db-update cannot be specified on the first run"
            return super().__call__(argv, input, **kw)

    fake = NoDbYet()
    fake.created = []
    s = scanner(fake, cosign=False)
    assert s.scan([CLEAN])[0] == "pass"
    assert fake.created == ["scan", "dbsync", "javasync", "scan"]
    fake.created.clear()
    assert s.scan([CLEAN])[0] == "pass"
    assert fake.created == ["scan"]  # offline from now on: no sync


def test_a_failed_first_sync_is_retried_by_the_next_scan():
    class NoDbYet(FakeKubectl):
        synced = False

        def __call__(self, argv, input=None, **kw):
            if argv[1] == "create":
                kind = yaml.safe_load(input)["metadata"]["labels"]["app.kubernetes.io/component"]
                self.synced = self.synced or (kind == "dbsync" and "dbsync" not in self.fail_kinds)
            self.fail_scan_with = None if self.synced else "FATAL --skip-db-update cannot be specified on the first run"
            return super().__call__(argv, input, **kw)

    fake = NoDbYet()
    fake.fail_kinds = {"dbsync"}  # the network is down during the first sync
    s = scanner(fake, cosign=False)
    result, detail = s.scan([CLEAN])
    assert result == "unavailable" and "database sync" in detail
    fake.fail_kinds = set()  # network is back: no gateway restart needed
    assert s.scan([CLEAN])[0] == "pass"
    assert s._synced is True


def test_every_job_is_deleted_even_when_it_fails():
    fake = FakeKubectl()
    fake.fail_scan_with = "boom"
    scanner(fake).scan([CLEAN])
    created = [c for c in fake.calls if c[1] == "create"]
    deleted = [c for c in fake.calls if c[1] == "delete"]
    assert len(created) == len(deleted) == 1 and "--ignore-not-found" in deleted[0]


# ---- the Job pod is sandboxed ---------------------------------------------------------------------

def test_scan_job_is_hardened_and_pinned():
    fake = FakeKubectl()
    scanner(fake).scan([CLEAN])
    for doc in fake.jobs.values():
        spec = doc["spec"]["template"]["spec"]
        c = spec["containers"][0]
        assert doc["metadata"]["namespace"] == im.NAMESPACE
        assert re.search(r"@sha256:[0-9a-f]{64}$", c["image"])  # pinned by digest
        sc = c["securityContext"]
        assert sc["allowPrivilegeEscalation"] is False and sc["privileged"] is False
        assert sc["readOnlyRootFilesystem"] is True and sc["runAsNonRoot"] is True
        assert sc["capabilities"] == {"drop": ["ALL"]} and sc["seccompProfile"]["type"] == "RuntimeDefault"
        assert spec["automountServiceAccountToken"] is False
        assert not (spec["hostNetwork"] or spec["hostPID"] or spec["hostIPC"])
        assert all("hostPath" not in v for v in spec["volumes"])
        assert doc["spec"]["activeDeadlineSeconds"] > 0 and doc["spec"]["backoffLimit"] == 0
        assert c["resources"]["limits"]["memory"]


def test_scan_runs_offline_against_the_pinned_database():
    args = im.trivy_scan_args(CLEAN)
    for flag in ("--skip-db-update", "--skip-java-db-update", "--offline-scan"):
        assert flag in args
    assert args[-1] == CLEAN
    assert "@sha256:" in " ".join(im.trivy_sync_args()) and "@sha256:" in " ".join(im.trivy_java_sync_args())
    for pin in (im.TRIVY_IMAGE, im.TRIVY_DB_REPO, im.TRIVY_JAVA_DB_REPO, im.COSIGN_IMAGE):
        assert re.search(r"@sha256:[0-9a-f]{64}$", pin)


def test_namespace_is_restricted_with_minimal_egress():
    ns, policy, pvc = im.namespace_docs()
    assert ns["metadata"]["labels"]["pod-security.kubernetes.io/enforce"] == "restricted"
    assert "Ingress" in policy["spec"]["policyTypes"] and "ingress" not in policy["spec"]
    ports = {p["port"] for rule in policy["spec"]["egress"] for p in rule["ports"]}
    assert ports == {53, 443}
    block = policy["spec"]["egress"][1]["to"][0]["ipBlock"]
    assert block["except"] == list(im.NOT_REACHABLE) and len(block["except"]) == 5
    assert pvc["kind"] == "PersistentVolumeClaim"


def test_cosign_result_is_recorded_but_never_gates():
    fake = FakeKubectl()
    fake.signed.add(CLEAN)
    s = scanner(fake)
    result, _, entries = s.scan_images([CLEAN])
    assert result == "pass" and entries[0]["cosign"] == "signed"
    result, _, entries = scanner(FakeKubectl()).scan_images([CLEAN])
    assert result == "pass" and entries[0]["cosign"] == "unsigned"


# ---- the record has the shape of apps/*/scan.json and feeds the existing gate ---------------------

def test_scan_json_is_read_by_the_existing_approval_check(tmp_path):
    s = scanner(FakeKubectl())
    for refs, want in (([CLEAN], "pass"), ([VULN], "fail")):
        result, _, entries = s.scan_images(refs)
        im.write_scan_json(tmp_path, im.scan_json(entries, result, NOW))
        rec = read_scan(tmp_path)
        assert rec is not None and rec.result == want
        doc = json.loads((tmp_path / "scan.json").read_text())
        assert set(doc["images"][0]["trivy"]) == {"version", "critical_fixable", "critical", "high"}
        assert doc["images"][0]["ref"] == refs[0]
    assert scan_problem("x", rec, NOW) is not None  # fail: install refused
    im.write_scan_json(tmp_path, im.scan_json(entries, "pass", NOW))
    read_scan.__globals__["_CACHE"].clear()
    rec = read_scan(tmp_path)
    assert scan_problem("x", rec, NOW) is None
    assert scan_problem("x", rec, NOW + timedelta(days=8)) is not None  # stale after 7 days
    assert rec.malware is None  # ClamAV does not run on the box: never claimed clean


def test_modes():
    assert isinstance(im.make_image_scanner("auto", "noop", "kubectl"), NoImageScanner)
    assert isinstance(im.make_image_scanner("none", "kubernetes", "kubectl"), NoImageScanner)
    assert isinstance(im.make_image_scanner("auto", "kubernetes", "kubectl"), im.KubeJobImageScanner)
    assert isinstance(im.make_image_scanner("kubernetes", "noop", "kubectl"), im.KubeJobImageScanner)


# ---- wiring: community sources and migrate use the gateway's scanner ------------------------------

def test_default_gateway_has_no_scanner_on_the_noop_executor(client):
    assert isinstance(client.app.state.appstore.image_scanner, NoImageScanner)


def test_community_source_record_is_decided_by_the_on_box_scan(tmp_path):
    from test_appstore import DIGEST, source_app

    from onemind_core.appstore.sources import scan_entry
    from onemind_core.appstore.store import Source
    from onemind_core.catalog import AppEntry

    source_app(tmp_path, "comm-hello")
    ref = f"ghcr.io/example/comm-hello:1@{DIGEST}"
    entry = AppEntry(id="comm-hello", dir=tmp_path / "comm-hello",
                     manifest=yaml.safe_load((tmp_path / "comm-hello" / "onemind.app.yaml").read_text()))
    src = Source(id="src_" + "0" * 26, name="comm", url="https://git.example.org/r", commit="1" * 40,
                 added_by="owner", added_at=NOW, updated_at=NOW, action_id=None)
    for text, want in ((report(critical_fixed=1), "fail"), (report(), "pass")):
        rec = scan_entry(entry, scanner(FakeKubectl({ref: text})), NOW, src)
        assert rec.result == want and rec.checks["images"]["scanner"] == "onbox-trivy"
    # the default scanner still refuses: no scanner, no pass
    assert scan_entry(entry, NoImageScanner(), NOW, src).result == "fail"


# ---- the hardened install's gateway fence ----------------------------------------------------------

RBAC = os.path.join(os.path.dirname(__file__), "..", "..", "deploy", "k8s", "gateway-rbac.yaml")


def _rbac_docs() -> list[dict]:
    with open(RBAC, encoding="utf-8") as f:
        return [d for d in yaml.safe_load_all(f) if d]


def test_gateway_fence_and_rbac_let_the_scanner_work_and_nothing_more():
    """deploy/install.sh gives the gateway a narrow identity; the scanner must fit inside it exactly."""
    docs = _rbac_docs()
    ns = next(d for d in docs if d["kind"] == "Namespace" and d["metadata"]["name"] == im.NAMESPACE)
    # the namespace the gateway applies must carry what the fence demands (label + restricted PSA)
    mine = im.namespace_docs()[0]["metadata"]["labels"]
    for labels in (ns["metadata"]["labels"], mine):
        assert "onemind.io/app" in labels
        assert labels["pod-security.kubernetes.io/enforce"] == "restricted"
    role = next(d for d in docs if d["kind"] == "Role" and d["metadata"]["namespace"] == im.NAMESPACE)
    granted = {(g or "", r): set(rule["verbs"]) for rule in role["rules"] for g in rule["apiGroups"]
               for r in rule["resources"]}
    # exactly these resources, no secrets, no pods write, no roles
    assert set(granted) == {("batch", "jobs"), ("networking.k8s.io", "networkpolicies"),
                            ("", "persistentvolumeclaims"), ("", "pods"), ("", "pods/log")}
    assert granted[("", "pods")] <= {"get", "list", "watch"} and granted[("", "pods/log")] == {"get"}
    # everything the scanner writes is granted
    kinds = {"Job": ("batch", "jobs"), "NetworkPolicy": ("networking.k8s.io", "networkpolicies"),
             "PersistentVolumeClaim": ("", "persistentvolumeclaims")}
    for doc in im.namespace_docs() + [im.job_doc("j", "scan", im.TRIVY_IMAGE, [], deadline_s=60)]:
        if doc["kind"] in kinds:
            assert {"create"} <= granted[kinds[doc["kind"]]], doc["kind"]
    assert "delete" in granted[("batch", "jobs")] and {"patch", "create"} <= granted[("", "persistentvolumeclaims")]
    binding = next(d for d in docs if d["kind"] == "RoleBinding" and d["metadata"].get("namespace") == im.NAMESPACE)
    assert binding["roleRef"]["name"] == role["metadata"]["name"]
    assert binding["subjects"] == [{"kind": "ServiceAccount", "name": "onemind-gateway", "namespace": "onemind-system"}]
    # the admission fence names this one namespace and those three kinds, not a pattern
    policy = next(d for d in docs if d["kind"] == "ValidatingAdmissionPolicy")
    first = policy["spec"]["validations"][0]["expression"]
    assert 'request.name == "onemind-scan"' in first
    assert 'request.namespace == "onemind-scan"' in first
    assert '["jobs", "networkpolicies", "persistentvolumeclaims"]' in first
    assert 'startsWith("onemind-' not in first and "startsWith(\"onemind" not in first  # no widening to a prefix
    # the namespace-label rule and the roleBinding rule are untouched
    assert "restricted" in policy["spec"]["validations"][1]["expression"]
    assert "onemind-app-deployer" in policy["spec"]["validations"][2]["expression"]


# ---- real cluster (opt-in) ------------------------------------------------------------------------

@pytest.mark.skipif(os.environ.get("ONEMIND_SCAN_IT") != "1", reason="needs k3s and internet; set ONEMIND_SCAN_IT=1")
def test_real_cluster_known_vulnerable_then_clean():
    """Acceptance test of CORE-DEPLOY-2 on a real box: digests come from the environment."""
    vulnerable, clean = os.environ["ONEMIND_SCAN_IT_VULNERABLE"], os.environ["ONEMIND_SCAN_IT_CLEAN"]
    s = im.KubeJobImageScanner(kubectl=os.environ.get("ONEMIND_KUBECTL", "kubectl"))
    s.sync_database()
    assert s.scan([vulnerable])[0] == "fail"
    assert s.scan([clean])[0] == "pass"
