<!-- SPDX-License-Identifier: Apache-2.0 -->
# Install sandbox (CORE-SANDBOX)

**Date:** 2026-11-12 · **Status:** proposal · **Plan epic:** E0S (blocks launch L1) · **Deeper docs:** [`docs/security/HARDENING-BACKLOG.md`](../../security/HARDENING-BACKLOG.md) H-01…H-04, H-08, H-13 and [`THREAT-MODEL.md`](../../security/THREAT-MODEL.md) §4.5 (branch `docs/security-threat-model`) · **Serves:** contract §3 executor, §11.1; brief 30 D-B6.1, E2; research 29 §8.1.

> **Explain it like I am the founder**
> Today an app you approve is installed with `kubectl apply -k`, and nothing checks *what kinds of things* it creates. A bad app could hand itself cluster-admin or mount the host's disk.
> The sandbox is a fence: one list of the Kubernetes objects an app may create, checked in CI **and** on the box, plus Kubernetes' own "restricted" pod rules everywhere.
> What gets checked is exactly what gets applied, and the approval card shows it. Nothing outside the fence ever reaches the cluster.

## 1. Goals and non-goals

| Goals | Non-goals (now) |
|---|---|
| One rule file for allowed object kinds and forbidden fields, used by CI (`app-gate`) and the gateway | Host grants (hostNetwork, devices, GPU) through the E2 capability broker: later, Verified publishers only |
| Pod Security Admission `restricted` cluster-wide, exempting only `kube-system` and `onemind-system` | gVisor or Kata sandboxes for untrusted agent code (research 29 §8.1): later |
| Gateway Kubernetes rights limited to `app-*` namespaces | A full admission webhook; v0 uses built-in `ValidatingAdmissionPolicy` |
| Default-deny network per app namespace, egress only as declared | Per-app egress allowlists by hostname (needs a proxy) |
| The approval card shows the checked plan; approval is bound to its hash | Signed catalog and publisher keys (SECURITY CORE-SEC-10, H-19) |

## 2. What exists today

| Piece | Where | State |
|---|---|---|
| Executor runs `kubectl apply -k <apps_dir>/<id>/manifests -n app-<id>` | `core/onemind_core/executors.py` (`KubernetesExecutor.plan`, lines 61–118) | On `main`. **No kind allowlist.** |
| Pod securityContext checks (non-root, limits) | `sdk/tools/app-gate` | Branch `feat/app-pipeline` (pipeline worktree), check 8 |
| Scan gate refuses stale or failing `scan.json` | `core/onemind_core/scan.py` | Branch `feat/gateway-agent-mcp` |
| Gateway ServiceAccount is `admin` in every namespace | `deploy/install.sh` (`gateway_kubeconfig`) | Branch `feat/deploy-v0` |
| Seed apps already non-root with `RuntimeDefault` seccomp; Home Assistant without hostNetwork | `apps/*/manifests/` | On `main` |

## 3. Design

### 3.1 The rule file
`sdk/policy/app-objects.yaml` is the only source of truth. CI, the gateway and later the Go CLI read it.

```yaml
schema: onemind.io/app-objects/v1
version: 1                       # bump on every change; scan.json records it
allow:                           # apiVersion/kind an app may ship
  - {apiVersion: apps/v1, kind: Deployment}
  - {apiVersion: apps/v1, kind: StatefulSet}
  - {apiVersion: batch/v1, kind: Job}
  - {apiVersion: batch/v1, kind: CronJob}
  - {apiVersion: v1, kind: Service, where: {spec.type: [ClusterIP]}}
  - {apiVersion: v1, kind: ConfigMap}
  - {apiVersion: v1, kind: Secret}
  - {apiVersion: v1, kind: PersistentVolumeClaim, where: {spec.storageClassName: [onemind-local, null]}}
  - {apiVersion: v1, kind: ServiceAccount, where: {automountServiceAccountToken: [false]}}
  - {apiVersion: policy/v1, kind: PodDisruptionBudget}
forbid_fields:                   # anywhere in a pod template
  - spec.hostNetwork: true
  - spec.hostPID: true
  - spec.hostIPC: true
  - spec.volumes[].hostPath
  - spec.containers[].ports[].hostPort
  - spec.containers[].securityContext.privileged: true
  - spec.containers[].securityContext.capabilities.add      # any value
  - metadata.namespace: "!app-{id}"                          # only its own namespace
images:
  require_digest: true           # repo:tag@sha256:…
kustomize:
  remote_bases: false            # no URL or git refs in resources:
```

Every rule has an id (`K-01` kind not allowed, `F-01` hostNetwork, `I-01` image without digest, `Z-01` remote base…) so errors and docs can point at it.

### 3.2 Where the check runs

```
request ──► gateway renders `kubectl kustomize apps/<id>/manifests` (local only)
            └─► policy.check(rendered, app_id) ──► violations? ── yes ─► action refused (no cluster call)
                                                        │ no
                                                        ▼
            plan stored: kinds, images, ports, PVCs, egress, plan_sha256
approve ──► re-render, re-check, compare plan_sha256 ──► `kubectl apply -f -` with the checked bytes
```

- **At request time:** the gateway builds the plan so the approval card shows it (H-13).
- **At approval time:** it renders again. If anything changed, approval returns 409. What is checked is what is applied: the executor switches from `apply -k` to `apply -f -` with the exact rendered document.
- **In CI:** `app-gate` runs the same checker after `kustomize build`; `scan.json` records `policy_version` and `rendered_sha256` (H-08).

### 3.3 Examples

**A refused install (agent asks for an app that ships a ClusterRoleBinding):**
```http
POST /v1/actions/7f3c/approve
Authorization: Bearer om_owner_EXAMPLE
{"plan_sha256": "9a1e…"}

HTTP/1.1 409 Conflict
{"error": "policy_refused",
 "message": "app 'evil-demo' breaks 1 install rule",
 "violations": [{"rule": "K-01", "kind": "ClusterRoleBinding", "name": "evil-demo-admin",
                 "message": "kind is not allowed for apps"}]}
```
`policy_refused` is a **new error code** (contract change, §5). The action moves to `failed` with the violations in its result, and the audit records `policy.refused`.

**The same check from the CLI (owner or developer):**
```console
$ onemind app validate apps/evil-demo
FAIL  apps/evil-demo  (rules v1)
  K-01  ClusterRoleBinding/evil-demo-admin   kind is not allowed for apps
  F-01  Deployment/evil-demo                 spec.hostNetwork: true
2 violations
$ echo $?
1
```

**SDK (proposed shapes; the developer-surface specs fix the package names):**
```python
# Python
from onemind_sdk import Client
plan = Client.from_env().actions.preview(type="app.install", params={"app_id": "uptime-kuma"})  # POST /v1/plans (API §5.11)
print(plan.kinds, plan.images, plan.plan_sha256)
```
```ts
// TypeScript
import { OneMind } from "@onemind/sdk";
const plan = await OneMind.fromEnv().actions.preview({ type: "app.install", params: { app_id: "uptime-kuma" } });
```
```go
// Go
c, err := onemind.FromEnv()
plan, err := c.Actions.Preview(ctx, onemind.ActionRequest{Type: "app.install", Params: onemind.ActionParams{AppID: "uptime-kuma"}})
```
**MCP:** agents get the plan inside the `request_action` result (`plan` field), never a way to change it.

### 3.4 Cluster-side fences (defence in depth)

| Fence | What | Source |
|---|---|---|
| PSA `restricted` | `AdmissionConfiguration` with `enforce/audit/warn: restricted`; exemptions `kube-system`, `onemind-system` only | H-01 |
| Gateway RBAC | `ClusterRole` may only create `namespaces`; per-app `RoleBinding` to `onemind-app-deployer` listing only allowed kinds; `ValidatingAdmissionPolicy` refuses deleting or relabelling non-`onemind.io/app` namespaces and any change to `pod-security.kubernetes.io/*` labels; bound token ≤ 24 h | H-03 |
| Network | Gateway applies `NetworkPolicy` default-deny in `app-<id>`: DNS to `kube-system`, ingress from the gateway proxy, egress per `spec.network.egress` (default: internet, no RFC 1918); host nftables drops pod CIDR → node ports 4222, 6443, 7480, 8080, 8443, 10250 | H-04 |
| Storage | PVCs land on `onemind-local` (Retain), see BACKUPS CORE-BACKUP-1 | D-B7.1 |

## 4. Security model

- **Threat:** an approved app (or an agent-requested one the owner approved without reading) escalates to node root. **Answer:** three independent layers (rule file, PSA, RBAC); any one alone leaves a path open (H-01 + H-02 + H-03 together).
- **TOCTOU:** the check and the apply use the same bytes; approval is bound to `plan_sha256`.
- **Agents:** cannot see or alter the rule file through MCP; a refused request is audited with the agent as requester, which feeds the pending-request cap (H-14).
- **Owner override:** none in v0. A future "trusted host grant" goes through E2 with a countersigned package (research 29 §8.1).

## 5. Versioning and compatibility

| Item | Rule |
|---|---|
| Rule file `version` | Integer. A tightening bump makes every app re-run `app-gate`; apps that now fail become `tier: blocked` and cannot be installed; installed apps keep running and raise an alert (NOTIFICATIONS). |
| `scan.json` | Adds `policy_version` and `subject.rendered_sha256` (H-08). Contract §11.1 change, own PR. |
| Error set | Adds `policy_refused` (409) to contract §3. Old clients see an unknown error string; they must treat it as a refusal. |
| Approve body | `plan_sha256` optional in v0 (audit logs `plan_unchecked`), required from contract v1. |
| Manifest | New optional `spec.network.egress: [internet\|none\|"<cidr>"]`; default `internet`. Schema change in `sdk/schema/onemind.app.schema.json`. |

## 6. Test plan and acceptance

| Test | Pass when |
|---|---|
| Fixture apps under `sdk/policy/fixtures/bad-*`: Namespace, ClusterRoleBinding, RoleBinding, DaemonSet, bare Pod, NodePort, hostPort, hostPath, privileged, image without digest, remote base, `metadata.namespace: kube-system` | Each refused by `app-gate` **and** by `core/tests/test_policy.py`; executor test with a fake runner asserts `kubectl` never ran |
| Seed apps (uptime-kuma, ntfy, home-assistant) | Pass both checkers; install and remove on k3d in CI |
| PSA on a fresh dev install and image | `kubectl -n app-test apply` of a privileged pod refused for each forbidden field |
| RBAC | With the gateway kubeconfig: `auth can-i create pods -n kube-system` → no; relabel `app-x` to privileged → refused; token `exp` ≤ 24 h |
| Network | From a pod in `app-uptime-kuma`: node ports 4222, 8080, 10250 and another app's Service time out; DNS and a public HTTPS site work |
| TOCTOU | Edit a manifest between request and approval → 409 and the card shows the new plan |

**Acceptance (E0S):** the ClusterRoleBinding fixture is refused at approve, the privileged pod is refused, and the three seed apps still install and remove.

## 7. Build steps

| Epic | Step | Effort | Depends on |
|---|---|---|---|
| CORE-SANDBOX-1 | Rule file + pure-Python checker `sdk/policy/check.py` + fixtures | S | – |
| CORE-SANDBOX-2 | Gateway: render, check, plan, `apply -f -`; `policy_refused`; `plan_sha256` on approve | M | 1, contract PR |
| CORE-SANDBOX-3 | PSA `restricted` in image and `deploy/install.sh` | S | – |
| CORE-SANDBOX-4 | Gateway RBAC + `ValidatingAdmissionPolicy` + bound token | M | 3 |
| CORE-SANDBOX-5 | Default-deny NetworkPolicy per app + host nftables; `spec.network.egress` | M | 2 |
| CORE-SANDBOX-6 | `app-gate` uses the checker; `scan.json` gains `policy_version`, `rendered_sha256` | S | 1, `feat/app-pipeline` merged |

## 8. Who owns which files

| Branch (proposed) | Files |
|---|---|
| `feat/install-sandbox` | new `sdk/policy/app-objects.yaml`, `sdk/policy/check.py`, `sdk/policy/fixtures/`, new `core/onemind_core/policy.py`, `core/onemind_core/executors.py` (`plan`, `run`), `core/tests/test_policy.py` |
| `feat/deploy-v0` follow-up | `deploy/install.sh` (`k3s_server`, `gateway_kubeconfig`), new `deploy/k8s/gateway-rbac.yaml`, `deploy/k8s/psa.yaml` |
| image stream (`os/`) | new `os/rootfs/layers/base/etc/rancher/k3s/psa.yaml`, `k3s.service` args, `etc/nftables.d/onemind.nft` |
| `feat/app-pipeline` follow-up | `sdk/tools/app-gate` (calls the checker) |
| Hotspots (serialized) | contract §3 error set and §11.1 fields; `sdk/schema/onemind.app.schema.json` (`spec.network`) |
