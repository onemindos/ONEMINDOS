<!-- SPDX-License-Identifier: Apache-2.0 -->
# OneMind OS core: threat model (v0)

**Status:** first edition, 2026-11-12. Written from the code, not from the plans.
**Scope:** `main` at `8838a28`, plus the wave-2 work about to land:

| Branch | Head | What it adds |
|---|---|---|
| `feat/gateway-agent-mcp` | `951470f` | `POST /mcp`, app agent principals (§11.2), scan check (§11.1) |
| `feat/deploy-v0` | `fa24b0a` | `deploy/install.sh`, gateway and NATS units, compose dev hub |
| `feat/onemindd-updater` | `8bf2fbc` (merged into `main` as #15 since) | `onemindd update`: TUF client, RAUC install, reboot |
| `feat/app-pipeline` | `3c22f91` | app CI gate (`sdk/tools/app-gate`), scaffolder |
| `feat/os-security-pipeline` | `a1f1fbf` | nightly security channel, TUF repo tooling, image `update.conf` |
| `feat/mobile-shell` | `cc62069` | Android and iPhone shells (Expo): connect, home, nodes, apps, approvals, activity, settings |

Line references such as `core/onemind_core/auth.py:144` point at `main`. References into a wave-2 branch name the branch first. Branch line numbers were re-checked against the heads in this table on 2026-11-12. A branch may change before it merges, so re-check a cited line when you act on it.

**Serves:** brief 30 B6 (D-B6.1, D-B6.2, D-B6.5), B4.5 (SB-1…SB-10), B9 (gateway), SEC-01…SEC-12 in [`research-output/07-security-compliance.md`](../../research-output/07-security-compliance.md) §10, and the founder focus of 2026-11-12: replace the founder's own Kubernetes cluster with OneMind OS and use it every day.
**Companion:** [`HARDENING-BACKLOG.md`](HARDENING-BACKLOG.md) holds the ranked fixes (`H-xx`) that this document refers to.

---

## 1. How to read this

**Threat model** means a list of the ways the system can be attacked, what stops each one today, and what is missing. It is written so that a fix can be checked by a test.

**STRIDE** is the checklist used for each component. Each letter is one kind of attack:

| Letter | Attack | Plain words | The property it breaks |
|---|---|---|---|
| **S** | Spoofing | pretending to be someone or something else | authentication |
| **T** | Tampering | changing data or code you should not change | integrity |
| **R** | Repudiation | doing something and being able to deny it | audit |
| **I** | Information disclosure | reading what you should not read | confidentiality |
| **D** | Denial of service | stopping the system from working | availability |
| **E** | Elevation of privilege | getting more power than you were given | authorization |

**Severity** in this document: **Critical** = one step from full control of the box or the cluster; **High** = a realistic attacker on the home network, or a malicious app, gets owner-level power or a secret; **Medium** = needs a second weakness, or leaks something useful; **Low** = hygiene.

---

## 2. The system and its trust boundaries

A **trust boundary** is a line where data passes from something we trust less to something we trust more. Every boundary is a place to check identity and input.

```
 Home LAN / tailnet (untrusted: phones, laptops, IoT, guests)
 ─────────────────────────────────────────────────────────────── B1
   browser / phone ──HTTP :8080──►  gateway (FastAPI, core/)  ──kubectl──► k3s API :6443
   AI agent        ──HTTP /mcp ──►     │  tokens, ledger, audit             │
   other nodes     ──NATS :4222──►  NATS (hub)  ◄──heartbeats── onemindd    ▼
   k3s agents      ──HTTPS :6443─►  k3s server (/data/k3s)        app pods in app-<id>
 ─────────────────────────────────────────────────────────────── B2 (pod ↔ host)
   app pods (untrusted code from the Market) ── can reach host ports, the bus, the gateway
 ─────────────────────────────────────────────────────────────── B3 (supply chain)
   GitHub repo, CI secrets, app images, TUF/RAUC keys ──► what every box installs
 ─────────────────────────────────────────────────────────────── B4 (physical)
   console, USB, disk removal
```

### 2.1 Assets (what we protect)

| Asset | Where it lives today | Why it matters |
|---|---|---|
| Owner token | sha256 in the tokens file (`core/onemind_core/auth.py:88-96`); the token itself in the browser's `sessionStorage` (`dashboard/src/session.tsx:41-57`) | Approves every action. Holding it is being the owner. |
| Gateway's Kubernetes identity | `/etc/onemind/gateway.kubeconfig` (`feat/deploy-v0`: `deploy/install.sh:410-470`) | Today it is `admin` in every namespace. |
| k3s server state | `/data/k3s` (`os/rootfs/layers/base/usr/lib/systemd/system/k3s.service:16-17`) | Holds the cluster CA keys, join tokens and every Secret. Whoever reads it owns the cluster. |
| Audit chain | `ONEMIND_AUDIT_PATH`, default `data/audit.jsonl` (`core/onemind_core/config.py:80`) | The record that an agent asked and a human approved. |
| App agent tokens | hashed in the ledger; plain in Secret `<name>` in `app-<id>` (`feat/gateway-agent-mcp`: `core/onemind_core/executors.py:52-66`) | Let an app's AI request actions. |
| Model-provider keys (Hermes) | Secret `hermes-agent-credentials`, created by the owner (`sdk/contracts/poc-v0.md` §7) | Cost money and can leak data if stolen. |
| Signing keys (RAUC, TUF targets/snapshot/timestamp) | GitHub repository secrets (`feat/os-security-pipeline`: `.github/workflows/security-nightly.yml:151, 217-219, 293-295, 392-394`) | Whoever holds them can push an OS image to every box. |
| User data (`/data`) | ext4, not encrypted (`os/boards/x86_64-efi/layout.yaml:13`, "LUKS2 planned") | Photos, home data, app volumes, backups' source. |

### 2.2 Attackers we design for now

| ID | Attacker | Example |
|---|---|---|
| A1 | **A device on the home network** | a compromised smart TV or IoT bulb, a guest laptop, malware on a family PC |
| A2 | **A malicious or compromised app** | a Market app whose image or manifests were swapped upstream, or an app with an exploitable bug |
| A3 | **A tricked AI agent** | Hermes reads a web page or email that tells it to install or remove something (prompt injection) |
| A4 | **A thief of a token or device** | a lost phone, a token pasted into a chat, a screenshot of the install banner |
| A5 | **The supply chain** | a compromised GitHub account, a CI secret leak, a poisoned npm or PyPI package, a swapped upstream image |
| A6 | **A rogue node** | a machine that joins with a leaked join token |
| A7 | **Physical access** | someone with the box, a keyboard and a USB stick |

Not modelled now (founder focus 2026-11-12): robots, drones, physical actuation, TAK. The rules for those (SEC-12 items 4-6, D-B6.4) stay in `research-output/07-security-compliance.md` §7.

---

## 3. The ten things that matter most

Ranked by how directly they lead to full control, for the founder's goal of running his own workloads on OneMind instead of his cluster. Each maps to a backlog item.

| # | Finding | Severity | Attacker | Evidence | Fix |
|---|---|---|---|---|---|
| 1 | **The executor applies any manifest.** `kubectl apply -k <app>/manifests -n app-<id>` applies whatever the kustomization renders: privileged pods, `hostPath: /`, `hostNetwork`, `NodePort`, and cluster-scoped kinds such as `Namespace`. No Pod Security level is enforced (the admission plugin defaults to `privileged`). A pod with `hostPath` on `/data` reads `/data/k3s` (cluster CA keys) and `/etc/onemind` (tokens file) and owns the box. | Critical | A2, A5 | `core/onemind_core/executors.py:74-82`; `os/.../k3s.service:17` (no PSA flags); `feat/app-pipeline`: `sdk/tools/app-gate` checks only for root (`nonroot`, lines 260-288), and accepts root when privilege escalation is off and all capabilities are dropped | H-01, H-02, H-03, H-04 |
| 2 | **The gateway's Kubernetes identity is `admin` in every namespace**, bound by a `ClusterRoleBinding`, plus create/delete on all namespaces. A gateway bug or a stolen kubeconfig gives `kube-system`, so node root. | Critical | A1 (via a gateway bug), A2 | `feat/deploy-v0`: `deploy/install.sh:436-451` | H-03 |
| 3 | **Owner token in clear text on the LAN.** The gateway serves plain HTTP on `0.0.0.0:8080`; anyone who can sniff the LAN or Wi-Fi reads the bearer token. Brief 30 (P6, REC-DEC-30) says the developer install binds the dashboard to localhost; `install.sh` binds `0.0.0.0` by default. | High | A1 | `core/onemind_core/config.py:86`; `feat/deploy-v0`: `deploy/install.sh:29`; brief 30 line 225 | H-05 |
| 4 | **NATS has no authentication and listens on every interface.** Any LAN device or any pod can publish fake heartbeats for any node id (including the hub's), read `onemind.audit`, or flood the bus. | High | A1, A2, A6 | `feat/deploy-v0`: `deploy/install.sh:281-285` ("no auth/TLS"); `core/onemind_core/bus.py:50-58` (no credentials) | H-06 |
| 5 | **Signing keys are plain repository secrets.** RAUC and all three online TUF keys are read by one workflow with no protected `environment:`. Anyone who can push a workflow to any branch of the repo can read them and sign an OS update for every box. | High | A5 | `feat/os-security-pipeline`: `.github/workflows/security-nightly.yml:151, 217-219, 293-295, 392-394` | H-07 |
| 6 | **Scan records are not bound to what is installed.** `scan.json` holds a date and `pass`, not a digest of the rendered manifests or images. A manifest edited after the scan still installs as "scanned". Kustomize can also pull remote bases at apply time. | High | A5 | `feat/gateway-agent-mcp`: `core/onemind_core/scan.py:31-66` | H-08, H-02 |
| 7 | **The audit chain proves order, not authorship.** Anyone who can write the file can rewrite it from the first line with fresh hashes, or cut the tail, and `verify()` still says OK. The NATS copy is not stored anywhere. | Medium | A2 (via #1), insider | `core/onemind_core/audit.py:37-38, 140-163` | H-10 |
| 8 | **Secrets at rest are not encrypted.** `/data` is plain ext4; k3s runs without `--secrets-encryption`, so model keys and agent tokens sit readable in the k3s datastore on disk. | Medium (High once the box holds the founder's real secrets) | A7, A2 | `os/boards/*/layout.yaml:13`; `k3s.service:17` | H-11, H-12 |
| 9 | **Tokens never expire and have no rotation tool.** Owner and agent tokens live until someone edits a file or reinstalls an app. The install prints the owner token and the node join token to the terminal. | Medium | A4 | `core/onemind_core/auth.py:100-144`; `feat/deploy-v0`: `deploy/install.sh:551-554` | H-09 |
| 10 | **On-box builds run third-party code as root.** The developer install runs `npm ci` and the Go build as root on the box. Lockfiles pin versions, but npm install scripts still run with root rights. | Medium | A5 | `feat/deploy-v0`: `deploy/install.sh:401-404` | H-15 |

---

## 4. STRIDE per component

Each table lists the threat, what stops it today (with evidence), what is missing, and the backlog item. "None" means nothing in the code stops it.

### 4.1 Gateway REST (`core/onemind_core/app.py`)

What it is: a FastAPI app on `:8080` that serves the §3 API and the dashboard files. It is the only component that changes the world, and only through an approved action.

| | Threat | Control today | Gap | Fix |
|---|---|---|---|---|
| S | Stolen or sniffed bearer token used from anywhere on the LAN | 256-bit tokens from the installer (`feat/deploy-v0`: `install.sh:477`); hash lookup (`auth.py:140-144`) | Plain HTTP (`config.py:86`); no binding of a token to a device; no expiry | H-05, H-09 |
| S | Forged browser request (CSRF) | Bearer header, which browsers never attach on their own (`app.py:112-120`) | none needed while auth stays a header; must stay true if cookies are added | H-16 (rule) |
| T | Path traversal through the SPA fallback | `candidate.is_relative_to(dist)` after `resolve()` (`app.py:194-196`) | none | — |
| T | Tampering with the apps folder changes what "install X" means | Folder owned by root (`feat/deploy-v0`: `install.sh` copies the repo's `apps/`) | Catalog is not signed; the future "catalog arrives through the gateway" (§10.2) has no signature format | H-08, H-19 |
| R | An owner denies approving | Every decision appended to the audit chain with principal id (`actions.py:163-170, 223`) | Chain is not signed or anchored (§4.3) | H-10 |
| I | Any principal (including `guest`) reads every node, app and action result | By design in v0 (§3 table) | Action `result.steps` include kubectl stdout/stderr tails (`executors.py:110-112`); acceptable now, revisit with multi-user | H-21 |
| I | `/openapi.json` open | Contract §3 | Reveals the version; low value | — |
| D | Unbounded request bodies or token-guessing floods | 401 audit rate-limited to 1/min (`app.py:93-110`) | No body-size limit on `/v1`, no per-IP rate limit | H-20 |
| E | A non-owner approves | `is_owner` requires `kind == person` and `role == owner` (`auth.py:43-46`; `actions.py:199-201`) | none found; tests in `core/tests/test_audit_auth_exec.py` | — |
| E | An owner approves without seeing what will run | Approvals show type + app id (contract §5) | The owner never sees the rendered objects, privileges, ports or images | H-13 |

### 4.2 MCP endpoint (`feat/gateway-agent-mcp`: `core/onemind_core/mcp.py`)

What it is: `POST /mcp`, so an AI agent can list nodes and apps and **request** an action. There is no approve tool.

| | Threat | Control today | Gap | Fix |
|---|---|---|---|---|
| S | A person's token used on `/mcp` | Agents only, else 403 (`mcp.py:159-160`) | none | — |
| S | DNS rebinding from a browser tab | Origin must equal Host when present (`mcp.py:161-165`) | none | — |
| T | Prompt-injected agent requests a harmful install | Every request waits for the owner (`mcp.py:230-252`); installs need a passing scan (`actions.py:235`) | Agent `reason` is free text shown to the owner (`mcp.py:98-101`); it can say "urgent security fix, approve". UI must mark it as agent-written | H-13 |
| R | Agent denies a request | `requested_by` and `reason` in the audit (`actions.py`, `action.requested`) | Same as §4.3 | H-10 |
| I | Agent learns the whole node inventory | Same as `/v1/nodes` | Fine for v0; later per-tool scopes (SEC-12 item 1) | H-22 |
| D | Approval fatigue: an agent files hundreds of requests | none | No cap on pending actions per principal | H-14 |
| E | Agent self-approves | No approve tool; `is_owner` false for agents (`auth.py:43-46`) | none | — |

### 4.3 Tokens and principals (`core/onemind_core/auth.py`, `ledger.py` agent tokens)

| | Threat | Control today | Gap | Fix |
|---|---|---|---|---|
| S | Guessing a token | sha256 lookup; tokens ≥ 16 chars (`auth.py:92-95`), 256-bit from the installer | 16 characters is weak for hand-written tokens | H-09 |
| T | Tokens file edited to add an owner | File mode 0640 root:onemind (`feat/deploy-v0`: `install.sh:474-490`) | Any pod with `hostPath` on `/etc` (finding #1) or the gateway user can add a hash; mtime reload picks it up silently (`auth.py:110-138`) | H-01, H-09 (audit token-set changes) |
| R | Unknown who used a token | Principal id in each audit line | No "last used" record; no token id in the audit | H-09 |
| I | Owner token leaks from the terminal or a screenshot | Printed once (`install.sh:551`) | Terminal scrollback and CI logs keep it; join token printed in the same banner | H-09 |
| I | Agent token readable in the app namespace | That is the delivery mechanism (§11.2); `automountServiceAccountToken: false` is required for Hermes (`sdk/contracts/poc-v0.md:116`) and set by the three wave-1 apps | Any pod in `app-<id>` reads it; cross-node pod traffic is unencrypted (§4.8) | H-17 |
| D | A broken tokens file locks the owner out | Keeps the last good set (`auth.py:125-136`) | none | — |
| E | A static-file agent with id `agent:<app>` collides with a DB agent | Ids are separate maps | Static ids are not checked against the `agent:` prefix | H-09 |

Revocation: static tokens are revoked only by editing the file; app tokens on `app.remove` or a failed install (`feat/gateway-agent-mcp`: `actions.py` `_agent_grant`, `_revoke_agent`). There is no expiry anywhere.

### 4.4 Audit chain (`core/onemind_core/audit.py`)

What it is: one JSON line per decision, `hash = sha256(prev_hash + line)`. It detects an edit in the middle of the file.

| | Threat | Control today | Gap | Fix |
|---|---|---|---|---|
| T | Edit one line | Next hash breaks; `verify()` reports it (`audit.py:140-163`) | none | — |
| T | **Rewrite the whole file** with fresh hashes, or **cut the tail** | none | No key signs a line or a checkpoint; no copy of the head hash lives anywhere else | H-10 |
| T | Crash garbage at the end | Moved to `.corrupt` and an `audit.recovered` event is written (`audit.py:70-106`) | An attacker can use the same path to hide a deleted tail; it is still logged as a recovery, which is good | H-10 |
| R | Owner or agent denies an action | Principal and ids in every line | The chain lives on the same disk as the attacker in finding #1 | H-10 |
| I | Audit lines published to `onemind.audit` with no NATS auth | none | Any LAN device can subscribe | H-06 |
| D | Disk full stops decisions | `fsync` per line (`audit.py:127-130`) | No size cap or rotation | H-20 |

### 4.5 Kubernetes executor (`core/onemind_core/executors.py`)

This is the most important section. The executor is where "the owner approved" turns into "code runs on the box".

**What happens today.** On approval of `app.install`, the gateway runs:

```
kubectl apply -f -                         # Namespace app-<id>
kubectl apply -n app-<id> -f -             # agent Secret (feat/gateway-agent-mcp, executors.py:135)
kubectl apply -k <apps_dir>/<id>/manifests -n app-<id>     (executors.py:81; branch :136)
```

What `-n app-<id>` does and does not do:
- For **namespaced** objects (Deployment, Secret, RoleBinding…), kubectl refuses an object whose `metadata.namespace` differs from `-n`. So an app cannot write into `kube-system` by naming it. This is kubectl client behaviour, not a server rule.
- For **cluster-scoped** objects (Namespace, ClusterRole, ClusterRoleBinding, CustomResourceDefinition, PersistentVolume, StorageClass, webhooks, PriorityClass, RuntimeClass) `-n` does nothing. They are sent as written. Whether they succeed depends only on the gateway's RBAC.
- **Inside** its namespace, nothing limits the pod spec. The Kubernetes PodSecurity admission plugin is on, but with no `AdmissionConfiguration` every namespace without labels is `privileged` (kubernetes.io/docs/concepts/security/pod-security-admission; the k3s CIS hardening guide, docs.k3s.io/security/hardening-guide, adds the config file). The image's `k3s.service:17` and the developer install set none.

**Attack paths that work today** with the `feat/deploy-v0` RBAC (`admin` everywhere + namespaces):

| # | App manifest contains | Result |
|---|---|---|
| E1 | a Pod with `hostPath: {path: /}` or `/data` | reads `/data/k3s/server` (cluster CA and service-account signing keys) and `/etc/onemind/tokens.yaml`; writes a new owner hash → owner and cluster-admin |
| E2 | `securityContext.privileged: true` or `hostPID: true` | root on the node (nsenter into PID 1) |
| E3 | `hostNetwork: true` | the pod sits on the host's network: reaches `127.0.0.1:8080` (gateway), `:4222` (NATS), `:6443`, `:10250`, and can sniff host traffic |
| E4 | a Service `type: NodePort` or a `hostPort` | opens a port on every node's LAN address, bypassing whatever reverse proxy OneMind puts in front |
| E5 | a `Namespace` object named `app-<id>` with `pod-security.kubernetes.io/enforce: privileged` | overrides the label the gateway set, so PSA **by namespace label alone** is bypassed |
| E6 | a `Namespace` named anything else, or an update to `kube-system`'s labels | allowed by the gateway's namespace rights (`install.sh:432-445`) |
| E7 | a `RoleBinding` in `app-<id>` that gives the app's ServiceAccount `admin`, and an app container that uses it | the app can create privileged pods in its own namespace at run time, after the scan |
| E8 | `resources: [https://github.com/…]` in `kustomization.yaml` | kubectl fetches remote content at apply time; what runs was never scanned or pinned |

The CI gate on `feat/app-pipeline` checks schema, pins, limits and non-root (`sdk/tools/app-gate`, `nonroot`), but has no kind allowlist and no check for `hostPath`, `hostNetwork`, `hostPID`, `hostIPC`, `privileged`, added capabilities, `NodePort`, `hostPort` or remote bases. The three wave-1 apps are clean (`apps/*/manifests/service.yaml` are `ClusterIP`, no host access), so the gap is in the gate, not in today's catalog.

**The fix (three layers; each closes a different subset of E1-E8, so all three are needed):**

1. **Allowlist, in the CI gate and again on the box.** The box renders the kustomization itself (`kubectl kustomize`, local files only), parses every object, and refuses the action before `kubectl apply` if any object is outside the allowlist. Allowed kinds for v0: `Deployment`, `StatefulSet`, `Service` (`ClusterIP` only), `ConfigMap`, `Secret`, `PersistentVolumeClaim`, `ServiceAccount`, `NetworkPolicy`, `Job`, `CronJob`, `PodDisruptionBudget`, `HorizontalPodAutoscaler`, `Ingress` (when the gateway proxy exists). Refused: every cluster-scoped kind, `Role`/`RoleBinding` (until the permission model of SEC-11 exists), `DaemonSet`, bare `Pod`, `Endpoints`/`EndpointSlice`, `NodePort`/`LoadBalancer`/`ExternalName` Services, `hostPort`, any image without `@sha256:`, and any `kustomization.yaml` with a non-local resource. The same rule file runs in CI (`sdk/tools/app-gate`) and in the gateway, so CI and box can never disagree. (H-02)
2. **Pod Security Admission, cluster-wide, from the API server.** A cluster default covers every namespace that sets no label, including any namespace created later. It does **not** stop E5 on its own: a namespace label overrides the cluster default, so E5 is closed by layer 1 (no `Namespace` objects in apps) and layer 3 (the gateway may not change `pod-security.kubernetes.io/*` labels). k3s takes an `AdmissionConfiguration` file through `--kube-apiserver-arg=admission-control-config-file=…` (k3s hardening guide). Default `enforce: baseline`, `audit`/`warn: restricted`, exemptions listed by name for `kube-system` and `onemind-system` only; the gateway labels each `app-<id>` `restricted` unless the app runs as root. Baseline already forbids `privileged`, host namespaces, `hostPath`, `hostPort` and added capabilities beyond the default set (E1-E3); restricted also forbids running as root (kubernetes.io/docs/concepts/security/pod-security-standards). `restricted` cannot be the cluster default yet because the gate accepts root apps with no capabilities, and `apps/home-assistant` is one (`apps/home-assistant/manifests/deployment.yaml:42-48`). (H-01)
3. **No cluster-scoped RBAC for the gateway.** Replace the two `ClusterRoleBinding`s with: one `ClusterRole` that can only `create` namespaces and `delete` namespaces carrying the label `onemind.io/app` (delete needs a small validating policy because RBAC cannot filter by label), and a `RoleBinding` per `app-<id>` created at install, to a namespaced role that covers the allowlist above and nothing else. The gateway then cannot touch `kube-system` even if it is fully compromised. (H-03)

Plus, for the pod ↔ host boundary (E3 and pods reaching host ports through the node IP): a **default-deny NetworkPolicy** in every `app-<id>` (D-B6.1, SEC-08), and a **host firewall** that drops traffic from the pod CIDR to `:4222`, `:6443`, `:7480`, `:8080`, `:10250` except from allowed sources. NetworkPolicy alone does not cover traffic to the node's own addresses in every CNI, so the host rule is required. (H-04)

| | Threat | Control today | Gap | Fix |
|---|---|---|---|---|
| S | Manifests pretend to be a different app | `metadata.id` must equal the folder (`catalog.py:140-141`) | none | — |
| T | Manifests changed after the scan | none | §4.6 | H-08 |
| T | `spec.manifests: ../../` escapes the app folder | `is_relative_to` check (`catalog.py:31-37`) | none | — |
| R | Unknown what was actually applied | argv and output tails in the ledger (`executors.py:96-115`) | The rendered objects and their digest are not recorded | H-13 |
| I | Token leaks through kubectl output | stdin never recorded; `_scrub` (`feat/gateway-agent-mcp`: `executors.py:177-181`) | none | — |
| D | `app.remove` deletes a namespace that is not the app's | Namespace name is `app-<id>` from a validated id (`catalog.py:21`) | The gateway can delete any namespace (`install.sh:432-445`) | H-03 |
| E | E1-E8 above | none | — | H-01…H-04 |

### 4.6 App manifests and the Market gate (`sdk/`, `apps/`, `feat/app-pipeline`, `feat/gateway-agent-mcp: scan.py`)

| | Threat | Control today | Gap | Fix |
|---|---|---|---|---|
| S | An app impersonates a known one | Licence checked in the gate (`app-gate` `licence_gate`, lines 88-98); a cosign signature must come from the source repo's GitHub owner (lines 207-221) | No publisher signature on the app package (SEC-11) | H-19 |
| T | Upstream swaps an image | Digest pinning required (contract §9.4 check 3; `validate-apps`) | The box does not re-check that every image is pinned | H-02 |
| T | Manifests edited after scanning | Scan freshness ≤ 7 days (`scan.py:69-80`) | `scan.json` has no digest of the rendered manifests or of `onemind.app.yaml` | H-08 |
| T | `javascript:` URL in `source` or `links` → script in the dashboard (`dashboard/src/pages/Market.tsx:136` renders `source` as a link) | Schema pattern `^https://` on `source` only (`sdk/schema/onemind.app.schema.json:49-54`) | `metadata.links` is not in the schema at all (metadata stays open, schema line 6); the built-in fallback check (`catalog.py:59-88`) checks no URL; it runs when the schema file is missing | H-18 |
| R | Who approved an app into the Market | Git history and PR review | — | — |
| I | Secrets in an image | Trivy secret scan (§9.4 check 6) | Wave-1 CI runs gitleaks only (`.github/workflows/ci-apps.yml:2-3`) | pipeline stream |
| D | One broken manifest hides the Market | Invalid apps skipped and listed (`catalog.py:125-148`) | none | — |
| E | Dangerous pod specs | Non-root check (`app-gate` `nonroot`) | See §4.5 | H-02 |

### 4.7 `onemindd` and NATS (`cmd/onemindd`, `internal/agent`, `core/onemind_core/bus.py`, `nodes.py`)

| | Threat | Control today | Gap | Fix |
|---|---|---|---|---|
| S | A LAN device or pod publishes heartbeats as any node, including the hub | Subject must match `node_id` in the body (`nodes.py:64-66`) | Nothing proves the publisher is that node: NATS has no users (`install.sh:281-285`) | H-06 |
| S | A rogue machine joins k3s with a leaked join token | Separate agent token, so a node can never join as a server (`install.sh:236-238`) | Joining needs no owner approval; the token never expires; the printed token carries the CA hash (`K10<hash>::`, see §7), so the agent verifies the server's certificate | H-23 |
| T | Fake audit lines on `onemind.audit` | none | Subscribers (future phone app) cannot tell real from fake | H-06, H-10 |
| R | — | — | — | — |
| I | `:7480` serves hardware, versions and update state to the whole LAN without auth | Heartbeat forbids serials, MACs, IPs, user names (`nodes.py:31`; `internal/heartbeat`) | Binds every interface (`internal/agent/agent.go:29`); versions help an attacker pick exploits | H-24 |
| D | Flood of fake node ids grows the registry without bound | 64 KiB per message (`nodes.py:27, 53`) | No cap on the number of nodes | H-06, H-20 |
| E | `onemindd` compromise | Runs with no capabilities, read-only filesystem, syscall filter (`deploy/systemd/onemindd.service:27-60`) | Runs as uid 0 (to read the k3s kubeconfig); acceptable with the bounding set empty | — |

### 4.8 Fabric: multi-node traffic

| | Threat | Control today | Gap | Fix |
|---|---|---|---|---|
| I | Pod-to-pod traffic between nodes is readable on the LAN (agent tokens, app data, gateway calls from pods) | k3s default flannel VXLAN, not encrypted | Use flannel's `wireguard-native` backend (k3s `--flannel-backend=wireguard-native`) | H-17 |
| I | Agent Secret URL is `http://<hostname>:8080` | `gateway_url()` falls back to plain HTTP (`feat/gateway-agent-mcp`: `config.py:67-80`) | `install.sh:509` writes `ONEMIND_GATEWAY_URL`, but the gateway reads `ONEMIND_PUBLIC_URL` (`config.py:101`), so the installer's value is ignored | H-05, H-25 |
| S/T | NATS between nodes | none | TLS + per-node credentials (D-B6.5 leaf design later) | H-06 |

### 4.9 OS image, RAUC, health gate, updater, TUF (`os/`, `feat/onemindd-updater`, `feat/os-security-pipeline`)

What is already strong: RAUC accepts only `verity` bundles (`os/rauc/system.conf.in:9-10`) checked against the image keyring; the trial marker is written before any slot is touched (`os/rauc/handlers/rauc-pre-install`); the updater trusts only the `root.json` inside the read-only image and walks root rotations from it (`feat/onemindd-updater`: `internal/update/tuf.go:55-80`), checks length and sha256 before RAUC sees a bundle (`download.go:23-130`), refuses plain HTTP except to loopback (`config.go:206-230`), and runs with only `CAP_DAC_READ_SEARCH` (`deploy/systemd/onemind-update.service:32-37`). The TUF root ceremony refuses to run in CI (`scripts/tuf-bootstrap-root.sh`). These follow the TUF design and are ahead of most competitors (TrueNAS: "signature produced optionally, no client check found", `research-output/02-competitors/MATRIX.md` [C-TD-truenas-scale-007, -008]; HAOS: no Secure Boot or TPM integration found, `research-output/07-security-compliance.md` §9 [C-W6-053]).

| | Threat | Control today | Gap | Fix |
|---|---|---|---|---|
| S | A fake update server | TUF + RAUC signatures | none on the box | — |
| T | **CI is compromised and signs a malicious release** | Keys only used when every secret exists and a publish switch is on (`security-nightly.yml:145-151`) | All signing keys in plain repository secrets, no protected environment, no second signer; RAUC key and TUF targets key leak together; the unattended 6-hourly `timestamp` job also holds the targets and snapshot keys (`security-nightly.yml:392-394`, it re-signs targets near expiry) | H-07 |
| T | `/data` override of `update.conf` changes `tuf_root_dir`, `rauc_binary` or `reboot_command` | The updater reads only `/etc/onemind/update.conf` today (`config.go:18`) | The image file promises "an owner's copy under /data overrides" (`feat/os-security-pipeline`: `etc/onemind/update.conf:5`). If that is built with all keys, a write to `/data` (finding #1) becomes root code execution, because `rauc_binary` runs as root | H-26 |
| T | Gate markers in `/data/onemind` (`pending`, `bad-releases`) edited to block security updates or commit a bad slot | root-only files | Any `hostPath` pod (finding #1) | H-01 |
| T | Console boot-line edit (`init=/bin/sh`) | none | GRUB has no superuser password (`os/assemble/grub.cfg.in:63-71`); the UKI + Secure Boot route is planned (SB-1, SB-7) | H-27 |
| R | Unknown which update ran | Status history (`internal/update/state.go`) | Not in the audit chain | H-10 |
| I | Version disclosure from the channel fetch | HTTPS | none | — |
| D | Freeze: an attacker blocks the channel | Timestamp expires after 1 day; failure logged | No alert to the owner yet | H-28 |
| E | Updater compromise | Bounding set `CAP_DAC_READ_SEARCH`, `ProtectSystem=strict` | none | — |

The cloud image's admin user has `NOPASSWD:ALL` (`os/boards/vm-do/rootfs/etc/sudoers.d/onemind:3`) with password SSH off and root login off (`.../sshd_config.d/onemind.conf:5-7`). That is a reasonable cloud default; for home boxes the first-boot credential rule SEC-15 applies.

### 4.10 Developer install `deploy/install.sh` (`feat/deploy-v0`)

What is strong: every download is pinned by version and sha256 and fetched with `--proto '=https'` (`install.sh:146-160`, `deploy/pins.env`); the k3s upstream script is pinned by commit and hash and run with downloads off; the owner token is stored only as its hash; the k3s admin kubeconfig stays root-only; security-only unattended upgrades plus `needrestart` are set up (`install.sh:166-205`).

| | Threat | Control today | Gap | Fix |
|---|---|---|---|---|
| S | — | — | — | — |
| T | A poisoned npm package runs as root during `npm ci` | `package-lock.json` | Install scripts run as root (`install.sh:401-404`) | H-15 |
| I | Join and owner tokens in terminal output | "shown once" | Scrollback; `--token` on a command line also lands in shell history and `ps` | H-09, H-23 |
| I | Gateway exposed on the LAN by default | `--gateway-bind` exists | Default `0.0.0.0` (`install.sh:29`) contradicts REC-DEC-30 (localhost) | H-05 |
| E | Gateway kubeconfig too powerful | not cluster-admin | `admin` everywhere (§4.5) | H-03 |
| E | Long-lived ServiceAccount token | — | A `kubernetes.io/service-account-token` Secret never expires (`install.sh:423-428`); prefer a bound token refreshed by a timer | H-03 |

The compose dev hub binds every port to `127.0.0.1` and uses the noop executor (`deploy/compose/compose.yaml:4, 17, 68, 84`); `ONEMIND_ALLOW_UNSCANNED=1` is refused with the kubernetes executor (`feat/gateway-agent-mcp`: `config.py` `check()`). That is the right shape.

### 4.11 Dashboard (`dashboard/`)

| | Threat | Control today | Gap | Fix |
|---|---|---|---|---|
| S | Phishing page asks for the token | — | Sign-in is "paste a token" (contract §5); later OIDC/passkeys (BD-03) | H-09 |
| T | Script injection from catalog fields | React escapes text; schema forces `https://` on `source` (not yet on `links`) | No Content-Security-Policy header from the gateway | H-18 |
| I | Token stolen by injected script | `sessionStorage`, per tab (`session.tsx:41-57`), not `localStorage` | Any script on the origin reads it; a CSP is the main control | H-18 |
| I | App links open plain `http://host:port` (`pages/Home.tsx:83`) | — | App UIs on the LAN have no auth in front; target is a gateway reverse proxy with forward-auth | H-29 |
| E | UI shows approve to a non-owner | Gateway enforces owner-only; UI follows a 403 (`session.tsx:7-14`) | none | — |

### 4.12 Mobile shells (`feat/mobile-shell` at `cc62069`)

What the branch does today: the hub URL and token are kept in the Keychain / Android Keystore through `expo-secure-store` with `AFTER_FIRST_UNLOCK_THIS_DEVICE_ONLY`, never AsyncStorage (`mobile/src/storage.ts:1-15`); the connect screen warns when the hub URL is plain HTTP to anything but loopback (`mobile/src/screens/ConnectScreen.tsx:15-20`); agent requests are labelled as AI-written (`mobile/src/screens/ApprovalsScreen.tsx:49`). Gaps: plain HTTP is allowed (Android `usesCleartextTraffic: true`, `mobile/app.json:47`; iOS `NSAllowsLocalNetworking`), and Approve sends the decision with no biometric or passcode check (`ApprovalsScreen.tsx:52`). The table is what the shell must meet before it approves anything on a real hub.

| | Threat | Requirement |
|---|---|---|
| S | Phone talks to a fake box on hostile Wi-Fi | Pair by scanning a QR code on the box's console or dashboard that carries the box's certificate fingerprint; pin it (H-05) |
| T | A tapped notification approves something different | The approve call names the action id **and** a hash of what the owner saw (type, app, rendered-plan digest); the gateway refuses on mismatch (H-13) |
| R | "I did not approve that from my phone" | Each phone gets its own device principal; the audit line names it (H-09) |
| I | Token on a lost phone | Token in Keychain / Android Keystore through `expo-secure-store`, never AsyncStorage; per-device token the owner can revoke from the dashboard (H-09) |
| I | Push payload content | D-005: APNs carries only an opaque "something new" signal; the app fetches details from the box |
| E | Phone approves without the owner present | Approve requires a biometric or device-passcode check at the moment of approval (step-up) (H-13) |

---

## 5. Cross-cutting topics the founder asked about

### 5.1 Token storage and rotation
Today: static hashed tokens in a YAML file, hot-reloaded; app agent tokens hashed in the ledger; no expiry; no rotation command; no per-device tokens. Target (H-09): a `onemind token` command and API (`create`, `list`, `revoke`, `rotate`), tokens with a recognisable prefix (`om_…`) so secret scanners catch leaks, an expiry per token (owner tokens long, device tokens renewable), a `last_used` record and token id in every audit line, and a token-set-changed audit event on file reload. Kanidm/OIDC with passkeys (BD-03) replaces person tokens later; agent and device tokens stay.

### 5.2 TLS / HTTPS on the LAN
Today: none. Target (H-05): the gateway serves HTTPS on `:8443` with a certificate from a **per-box CA** created at first boot (the private key never leaves `/data`, later sealed by the TPM); `:8080` answers only on `127.0.0.1` (health checks, the local CLI) or redirects. Phones and browsers trust the box through **QR pairing** that carries the CA fingerprint. On a tailnet the owner may use the tailnet's certificates instead. This is the pattern of Caddy's internal CA (`tls internal`); no code is copied.

### 5.3 NATS authentication
Today: anonymous, `0.0.0.0:4222`. Target (H-06): `nats.conf` with `authorization` users or nkeys: one credential per node (issued at join, after owner approval) allowed to **publish only** `onemind.node.<its-id>.status`; the gateway allowed to subscribe to heartbeats and publish `onemind.audit`; everyone else denied. TLS on the listener with the box CA. Later this becomes NATS accounts with JWTs and leaf nodes (D-B6.5).

### 5.4 Secrets at rest (LUKS2 plan)
Today: `/data` is plain ext4 (`layout.yaml:13`, "LUKS2 planned (SB-5, BM2; findings F-04)"); k3s Secrets unencrypted in the datastore. Plan, already decided (SEC-01, SEC-02, SB-5, SB-5b):
1. **Now (H-12):** k3s `--secrets-encryption` on every image and developer install; costs nothing and protects Secrets in a copied datastore or backup.
2. **Next (H-11):** LUKS2 on `onemind-data` from first boot, recovery key generated at install and shown once (P3 installer, brief 30 line 225); unlock by passphrase on boards without a TPM.
3. **Then:** TPM2 enrolment bound to PCR 7 + a signed PCR 11 policy with a systemd initrd (SB-5), and the PCR 15 volume-identity check (SB-5b). Pis bought by users stay "lower assurance" (key on disk or passphrase).
4. **Fabric extra (beyond competitors):** a second OneMind node can act as a network unlock server (the Tang/Clevis pattern, both GPL, so pattern only), so a headless box reboots unattended at home but not when stolen.

### 5.5 Supply chain
Strong now: pinned sha256 downloads, pinned base images by digest (`core/Dockerfile:6-7`), kubectl hash-checked (`core/Dockerfile:22-38`), GitHub Actions pinned by commit SHA (all `.github/workflows/*.yml`), gitleaks in CI, `uv.lock` and `package-lock.json`, TUF + RAUC. Gaps: signing keys in plain repository secrets (H-07), on-box builds as root (H-15), no build provenance or SBOM attached to releases yet (SEC-10; H-30), no app publisher signatures (SEC-11; H-19), scan not bound to content (H-08).

---

## 6. Competitors: what to copy (patterns only) and where OneMind beats them

Sources are the claim ids in `research-output/02-competitors/MATRIX.md` and `research-output/07-security-compliance.md` §9. **Licence rule:** these are patterns. umbrelOS is PolyForm Noncommercial; nothing from it is copied, not even text. Code may be copied only from MIT, BSD or Apache-2.0 projects, verified at the commit read, with a `NOTICE` entry. This document copies no code.

| Pattern | Who does it | OneMind version | Backlog |
|---|---|---|---|
| Numeric add-on security rating (1-8) | Home Assistant OS [C-W6-054] | Same, plus Kubernetes deductions (host paths, `hostNetwork`, privileged, cluster RBAC, devices), computed by the same allowlist file that gates installs | H-02, H-19 |
| Extension path allow-list | Talos [C-TD-talos-024] | Kind and field allowlist for app manifests | H-02 |
| Role-scoped mTLS API, no shell | Talos [C-TD-talos-028] | Per-device and per-node credentials; mTLS for nodes later | H-06, H-23 |
| App ID = signing key; M-of-N release key | Sandstorm [C-TD-tier-c-alt-022, -020] | Publisher keys for apps; threshold root for TUF (already in `tuf-repo.py init-root --threshold`) | H-07, H-19 |
| TOTP / WebAuthn for owners | Proxmox (TOTP, WebAuthn) [C-TD-proxmox-ve-031], Synology (2FA) [C-TD-tier-c-nas-031], umbrelOS (TOTP) [C-TD-umbrelos-033] | Passkeys with OIDC (BD-03); step-up at approval | H-09, H-13 |
| Encrypted backups (SecureTar, Kopia, restic) | HAOS, umbrelOS [C-TD-umbrelos-030], Cosmos [C-TD-tier-c-selfhost-008] (`MATRIX.md` backups column) | restic with three keys (REC-DEC-11) | backups stream |

**Where OneMind is already ahead, and must stay ahead:**
- **Agents never approve, enforced by the gateway.** umbrelOS's MCP agents act as the owner with one shared grant set and can install an OS update with only a client-side hint [C-TD-umbrelos-037, C-W6-052]; ZimaOS's MCP server logs in with the admin password [C-TD-casaos-zimaos-038]. OneMind: per-app agent principals, no approve tool, 403 in code.
- **A security-only update channel with TUF + RAUC and automatic rollback.** No competitor in the matrix ships all three.
- **"Nothing unscanned runs"** enforced at approval time, not only in CI.

**Features to build on top that beat them (each is in the backlog):**
1. **"What will change" approval card** (H-13): before approving, the owner sees the rendered objects, images with digests, ports, volumes, privileges and the security rating, and the approval is bound to that exact plan. No competitor shows this.
2. **Phone approval with step-up and plan binding** (H-13, §4.12): approve from the lock screen with Face ID or fingerprint, and the box refuses if the plan changed since the notification.
3. **Owner-approved node join** (H-23): a new machine appears as an approval request ("Beelink wants to join as a worker"), and its credentials are issued only after the owner says yes.
4. **Off-box audit anchor** (H-10): the phone and other nodes keep the chain's head hash, so a wiped or rewritten log is detected by a device the attacker does not control.
5. **Fabric network unlock** (§5.4): another OneMind node unlocks the data disk at boot; a stolen box stays locked.

---

## 7. Assumptions, limits and UNVERIFIED items

- **Checked in the k3s source (v1.37.2+k3s1, the version `deploy/pins.env` pins; Apache-2.0):** when `agent-token` is set, as `install.sh` does, k3s writes `<data-dir>/server/agent-token` through `FormatToken` with the server CA (`pkg/server/server.go:375-385`, `pkg/server/handlers/token.go:56-65`), giving `K10<sha256 of CA>::<creds>` (`pkg/clientaccess/token.go:614-625`). So the join token printed by `install.sh:547-554` does pin the CA. H-23's test still confirms it on a real install.
- **UNVERIFIED:** kubectl's client-side namespace mismatch refusal is recalled from kubectl behaviour, not re-run here. H-02's test covers it by applying a cross-namespace object.
- The image's core platform pod is still a `pause` stand-in (`os/rootfs/layers/base/usr/lib/onemind/manifests/onemind-core.yaml:2`); the gateway's RBAC **on the OS image** is not defined yet. H-03 must apply there too.
- Not modelled: robots, drones, TAK, the plugin UI (phase 2), multi-user households (roles `adult`/`guest` exist but have no distinct rights yet).
- Nothing in this document was tested against a running box. Each backlog item carries the test that proves the fix.
