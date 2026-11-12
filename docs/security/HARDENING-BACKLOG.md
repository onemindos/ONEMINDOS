<!-- SPDX-License-Identifier: Apache-2.0 -->
# OneMind OS core: hardening backlog

**Status:** first edition, 2026-11-12. Ranked. Every item names the file it touches and an **acceptance test**: a check that fails today and passes once the fix is in. "Fails today" was established by reading the code (see [`THREAT-MODEL.md`](THREAT-MODEL.md)), not by running it on a box.
**Serves:** brief 30 B6 (D-B6.1, D-B6.2, D-B6.5), B4.5 (SB-1…SB-10), B9, SEC-01…SEC-17, founder focus 2026-11-12 (replace the founder's cluster with OneMind OS).

## How the ranking works
- **P0 — before the box runs anything the founder cares about.** A malicious app or a LAN device gets full control without these.
- **P1 — before daily use with real secrets and more than one node.**
- **P2 — before anyone else runs it** (Market launch, first sale).

Inside a tier, items are in the order to build them. **Owner** is the build stream that owns the file (gateway = `core/`, deploy = `deploy/`, image = `os/`, pipeline = `sdk/tools` + CI, updater = `internal/update`, dashboard, mobile).

## Summary

| ID | Tier | Item | Owner | Main files |
|---|---|---|---|---|
| H-01 | P0 | Pod Security cluster-wide by API-server admission config (`baseline` enforced, `restricted` per app) | image, deploy | `os/.../k3s.service`, new `os/.../etc/rancher/k3s/psa.yaml`, `deploy/install.sh` |
| H-02 | P0 | Manifest allowlist, one rule file, enforced in CI and in the gateway | pipeline, gateway | new `sdk/policy/app-objects.yaml`, `sdk/tools/app-gate`, `core/onemind_core/executors.py` |
| H-03 | P0 | Gateway RBAC: no cluster-wide `admin`, per-app RoleBinding, bound token | deploy, image | `deploy/install.sh` (`gateway_kubeconfig`), `core/onemind_core/executors.py` |
| H-04 | P0 | Default-deny NetworkPolicy per app namespace + host firewall | gateway, image, deploy | `core/onemind_core/executors.py`, new `os/.../etc/nftables.d/onemind.nft` |
| H-05 | P0 | HTTPS with a per-box CA; plain HTTP on loopback only; bind default localhost | gateway, deploy | `core/onemind_core/config.py`, `__main__.py`, `deploy/install.sh` |
| H-06 | P0 | NATS users with per-subject permissions + TLS | deploy, gateway, onemindd | `deploy/install.sh` (`nats_install`), `core/onemind_core/bus.py`, `internal/agent/agent.go` |
| H-07 | P0 | Signing keys behind a protected environment; split RAUC and TUF signers | pipeline | `.github/workflows/security-nightly.yml`, `os/update/README.md` |
| H-08 | P1 | Bind `scan.json` to a digest of what is installed | pipeline, gateway | `sdk/tools/app-gate`, `core/onemind_core/scan.py`, `sdk/contracts/poc-v0.md` §11.1 |
| H-09 | P1 | Token lifecycle: create/list/revoke/rotate, expiry, prefix, last-used, device tokens | gateway, CLI | `core/onemind_core/auth.py`, `ledger.py`, `cmd/onemind/` |
| H-10 | P1 | Signed, anchored audit checkpoints | gateway | `core/onemind_core/audit.py` |
| H-11 | P1 | LUKS2 on `onemind-data` from first boot, recovery key once | image | `os/boards/*/layout.yaml`, `os/assemble/assemble.py`, initrd units |
| H-12 | P0 | k3s secrets encryption on | image, deploy | `os/.../k3s.service`, `deploy/install.sh` (`k3s_server`) |
| H-13 | P1 | "What will change" approval card, bound to the approval | gateway, dashboard, mobile | `core/onemind_core/actions.py`, `executors.py`, `dashboard/src/pages/Approvals.tsx` |
| H-14 | P1 | Cap pending actions per agent | gateway | `core/onemind_core/actions.py` |
| H-15 | P1 | No third-party build code as root on the box | deploy | `deploy/install.sh` (`dashboard_build`, `onemindd_install`) |
| H-16 | P2 | Rule: no cookie auth without CSRF defence | gateway | `core/README.md` |
| H-17 | P1 | Encrypt pod traffic between nodes (flannel `wireguard-native`) | deploy, image | `deploy/install.sh`, `os/.../k3s.service` |
| H-18 | P1 | Content-Security-Policy and security headers; URL check in the built-in manifest check | gateway | `core/onemind_core/app.py`, `catalog.py` |
| H-19 | P2 | Signed catalog and publisher keys; security rating | pipeline, gateway | `sdk/`, `core/onemind_core/catalog.py` |
| H-20 | P2 | Limits: body size, rate, node count, audit rotation | gateway | `core/onemind_core/app.py`, `nodes.py`, `audit.py` |
| H-21 | P2 | Role-based read access (`adult`, `guest`) | gateway | `core/onemind_core/app.py` |
| H-22 | P2 | Per-tool capability scopes for agents (SEC-12 item 1) | gateway | `core/onemind_core/mcp.py`, `auth.py` |
| H-23 | P1 | Owner-approved node join; short-lived join token; CA-pinned token | deploy, gateway | `deploy/install.sh`, `core/onemind_core/actions.py` |
| H-24 | P1 | `onemindd` local API on loopback by default | onemindd | `internal/agent/agent.go`, `deploy/systemd/onemindd.service` |
| H-25 | P0 | Fix `ONEMIND_GATEWAY_URL` / `ONEMIND_PUBLIC_URL` mismatch | deploy | `deploy/install.sh` |
| H-26 | P1 | `/data` override of `update.conf` may set policy keys only | updater, image | `internal/update/config.go`, `os/.../etc/onemind/update.conf` |
| H-27 | P2 | Lock the boot line (UKI + Secure Boot route, SB-1/SB-7) | image | `os/assemble/`, `os/boards/x86_64-efi/` |
| H-28 | P1 | Alert the owner on update freeze, scan expiry, audit break | updater, gateway | `internal/update/engine.go`, notifications |
| H-29 | P1 | App web UIs behind the gateway's reverse proxy with forward-auth | gateway, dashboard | new proxy module, `dashboard/src/pages/Home.tsx` |
| H-30 | P2 | Build provenance and SBOM on every release | pipeline | `.github/workflows/` |

---

## P0 — before the box runs anything the founder cares about

### H-01 · Pod Security cluster-wide: `baseline` enforced, `restricted` per app
**Why:** without an enforced level, an app manifest with `privileged`, `hostPath` or `hostNetwork` owns the node (threat model §4.5, E1-E3). A cluster default does not stop an app that ships its own `Namespace` object and relabels itself (E5): a namespace label overrides the default. E5 is closed by H-02 (no `Namespace` objects) and H-03 (no PSA label changes by the gateway).
**Change:** ship an `AdmissionConfiguration` with `PodSecurity` defaults `enforce: baseline`, `audit/warn: restricted`, `exemptions.namespaces: [kube-system, onemind-system]` (and nothing else). The gateway labels each `app-<id>` `pod-security.kubernetes.io/enforce: restricted`, except an app that runs as root, which keeps `baseline` and shows "runs as root" on its approval card (H-13) and rating (H-19). `restricted` cannot be the cluster default today: the app gate accepts root with all capabilities dropped (`feat/app-pipeline`: `sdk/tools/app-gate:282-285`), and `apps/home-assistant` is such an app (`apps/home-assistant/manifests/deployment.yaml:42-48`). Start k3s with `--kube-apiserver-arg=admission-control-config-file=/etc/rancher/k3s/psa.yaml` (k3s hardening guide, docs.k3s.io/security/hardening-guide). Same file written by `deploy/install.sh` into `/etc/rancher/k3s/config.yaml`.
**Files:** `os/rootfs/layers/base/usr/lib/systemd/system/k3s.service:17`, new `os/rootfs/layers/base/etc/rancher/k3s/psa.yaml`, `deploy/install.sh` (`k3s_server`).
**Acceptance test:** on a fresh image and a fresh developer install, in an unlabelled namespace, `kubectl apply -f pod.yaml` is **refused** with a PodSecurity error for each of: `privileged: true`, `hostPath`, `hostNetwork`, `hostPID`, `capabilities.add: [NET_ADMIN]`; in an `app-<id>` labelled `restricted`, a pod with no `runAsNonRoot` is also refused. With H-03 in place, `kubectl label ns app-test pod-security.kubernetes.io/enforce=privileged --overwrite` using the gateway's kubeconfig is refused. `ntfy` and `uptime-kuma` install under `restricted` and reach Ready; `home-assistant` installs under `baseline` and reaches Ready (making it run non-root is a follow-up for the app, not an exemption).

### H-02 · Manifest allowlist, one rule file, CI and box
**Why:** PSA covers pods only. Cluster-scoped kinds, `NodePort`, `hostPort`, RoleBindings, unpinned images and remote kustomize bases need a separate check (E4-E8). CI alone is not enough, because the box must not trust that the catalog it holds is the one CI checked.
**Change:** a single file `sdk/policy/app-objects.yaml` listing allowed `apiVersion/kind` pairs and forbidden fields (threat model §4.5, "The fix", layer 1). A small pure-Python checker (`sdk/policy/check.py`, no network) that takes rendered YAML and returns violations. `sdk/tools/app-gate` calls it after `kustomize build`. The gateway calls it in `KubernetesExecutor.plan()` on the output of `kubectl kustomize <dir>` (local only; refuse any `resources:` entry that is a URL or `git` reference), then applies **the rendered YAML it checked** with `kubectl apply -f -`, never `-k`, so what is checked is what is applied. A violation fails the action with `failed` and lists the violations in the result; it never reaches the cluster.
**Files:** new `sdk/policy/app-objects.yaml`, new `sdk/policy/check.py`, `sdk/tools/app-gate` (`feat/app-pipeline`), `core/onemind_core/executors.py:69-88` (branch: 118-146).
**Acceptance test:** a test fixture app per forbidden case (cluster-scoped `Namespace`, `ClusterRoleBinding`, `RoleBinding`, `DaemonSet`, bare `Pod`, Service `NodePort`, `hostPort`, image without `@sha256:`, remote base in `kustomization.yaml`, object with `metadata.namespace: kube-system`) is rejected by **both** `app-gate` and `core/tests` (executor test with a fake runner asserts `kubectl` was never called). The three wave-1 apps pass both. The executor's first `kubectl` call for the app is `apply -f -` with the checked document on stdin.

### H-03 · Gateway RBAC without cluster-wide rights
**Why:** today the gateway's ServiceAccount is `admin` in every namespace plus full namespace rights (`feat/deploy-v0`: `deploy/install.sh:432-451`). A gateway bug becomes `kube-system` and so node root. Its token is a legacy Secret that never expires (`install.sh:423-428`).
**Change:**
1. `ClusterRole onemind-gateway-namespaces`: `create` on `namespaces` only, plus `get/list`.
2. Deleting and labelling namespaces: allowed only for namespaces labelled `onemind.io/app`, enforced by a `ValidatingAdmissionPolicy` (built into Kubernetes, GA since 1.30) that also refuses label changes to `pod-security.kubernetes.io/*` by the gateway.
3. At `app.install`, the gateway (still using a bootstrap right limited to `rolebindings` in `app-*` via the same policy) creates `RoleBinding onemind-gateway` in `app-<id>` to `ClusterRole onemind-app-deployer`, which lists only the kinds of the H-02 allowlist.
4. Replace the Secret-based token with a bound token from `kubectl create token --duration` refreshed by a systemd timer, or run the gateway in-cluster with a projected token.
5. Apply the same model to the OS image when the core chart replaces the `pause` stand-in (`os/.../manifests/onemind-core.yaml`).
**Files:** `deploy/install.sh` (`gateway_kubeconfig`, lines 410-470), new `deploy/k8s/gateway-rbac.yaml` (and the image's core chart later), `core/onemind_core/executors.py` (`plan`).
**Acceptance test:** with the gateway kubeconfig: `kubectl auth can-i create pods -n kube-system` → `no`; `kubectl auth can-i get secrets -n kube-system` → `no`; `kubectl delete ns kube-system --dry-run=server` → forbidden; `kubectl label ns app-x pod-security.kubernetes.io/enforce=privileged` → refused by the policy; install and remove of `uptime-kuma` still succeed; the kubeconfig token's `exp` claim is within 24 h.

### H-04 · Default-deny network per app + host firewall
**Why:** a pod can reach NATS, the gateway, the k3s API and the kubelet on the node's addresses, and other apps (threat model §4.5 E3, §4.7).
**Change:** at `app.install`, apply a `NetworkPolicy` in `app-<id>` that denies all ingress and egress except DNS to `kube-system`, ingress from the gateway proxy (H-29), and egress declared in a new manifest field `spec.network.egress` (default: internet only, no RFC 1918 ranges). On the host, an nftables table that drops new connections from the pod CIDR to the node's ports `4222, 6443, 7480, 8080, 8443, 10250` except the ones the core needs (k3s ships the kube-router NetworkPolicy controller, enabled by default).
**Files:** `core/onemind_core/executors.py` (`plan`), new `os/rootfs/layers/base/etc/nftables.d/onemind.nft` + a unit, `deploy/install.sh`, `sdk/schema/onemind.app.schema.json` (`spec.network`).
**Acceptance test:** from a pod in `app-uptime-kuma`: `nc -z <node-ip> 4222`, `:8080`, `:10250` and `<other-app-svc>:port` all time out; `nslookup kubernetes.default` works; an HTTPS request to a public site works; the gateway's `GET /healthz` from the host still works.

### H-05 · HTTPS on the LAN, plain HTTP on loopback only
**Why:** the owner token crosses the LAN in clear text (`core/onemind_core/config.py:86`; `feat/deploy-v0`: `install.sh:29`). REC-DEC-30 already says the developer install binds the dashboard to localhost.
**Change:** at first start the gateway creates a per-box CA and a server certificate (hostname, `<hostname>.local`, the box's addresses; ECDSA P-256, 1-year leaf, auto-renew) under `/data/onemind/tls/` (mode 0600, owner `onemind`). It serves HTTPS on `:8443` and keeps `:8080` on `127.0.0.1` for local tools and health checks. `deploy/install.sh` defaults `--gateway-bind 127.0.0.1` for the HTTP port and prints the CA fingerprint plus a pairing QR (fingerprint + URL, **no token** in the QR). `ONEMIND_PUBLIC_URL` defaults to the `https://` URL. App agent Secrets carry the CA bundle (`ONEMIND_GATEWAY_CA`).
**Files:** `core/onemind_core/config.py`, `core/onemind_core/__main__.py`, new `core/onemind_core/tls.py`, `deploy/install.sh`, `deploy/systemd/onemind-gateway.service`, `core/onemind_core/executors.py` (`AgentSecret.manifest`).
**Acceptance test:** from another machine, `curl http://<box>:8080/healthz` → connection refused; `curl --cacert box-ca.pem https://<box>:8443/healthz` → 200; `curl -k` against a different box's CA with `--pinnedpubkey` → fails; `testssl.sh` reports TLS 1.2+ only, no weak ciphers; the CA private key file is mode 0600 and not world-readable.

### H-06 · NATS authentication, per-subject permissions, TLS
**Why:** anyone on the LAN or in a pod can impersonate any node and read or forge `onemind.audit` (`feat/deploy-v0`: `install.sh:281-285`).
**Change:** `nats.conf` gets an `authorization { users = [...] }` block with nkeys (NATS public-key auth, no passwords on disk in clear): user `gateway` (subscribe `onemind.node.*.status`, publish `onemind.audit`), one user per node issued at join (publish **only** `onemind.node.<node_id>.status`), deny everything else. Add `tls {}` with the box CA (H-05). `onemindd` reads its seed from `/etc/onemind/nats.nk` (0600) and `ONEMIND_NATS_URL=tls://…`; `bus.py` passes `nkeys_seed` and the CA. Cap the registry at a configured node count.
**Files:** `deploy/install.sh` (`nats_install`, `onemindd_install`), `deploy/systemd/onemind-nats.service`, `core/onemind_core/bus.py:50-58`, `core/onemind_core/nodes.py`, `internal/agent/agent.go:211-228`, `cmd/onemindd/main.go`.
**Acceptance test:** `nats pub onemind.node.<hub-id>.status '{}'` with no credentials → `Authorization Violation`; with node A's credentials publishing as node B → permission violation and the hub's node B entry is unchanged; `nats sub onemind.audit` with node credentials → permission violation; the gateway still lists every real node; `nats-server --signal reload` keeps connections.

### H-07 · Signing keys behind a protected environment, split signers
**Why:** RAUC and all TUF online keys are repository secrets read by one workflow with no `environment:` (`feat/os-security-pipeline`: `.github/workflows/security-nightly.yml:151, 217-219, 293-295, 392-394`). A workflow pushed to any branch can read them. The unattended 6-hourly `timestamp` job also holds the targets and snapshot keys, because it re-signs them near expiry (`security-nightly.yml:392-394`).
**Change:** move each key to its own GitHub **environment** (`release-rauc`, `tuf-targets`, `tuf-timestamp`) restricted to `main` with required reviewers for `release-rauc` and `tuf-targets`; only the 6-hourly timestamp job runs unattended, and it gets the timestamp key only (snapshot too if it must re-sign snapshot); re-signing targets before expiry moves to the reviewed job. Split the jobs so one job never holds both the RAUC key and the TUF targets key. Use `tuf-repo.py init-root --threshold 2` for the root (already supported) and document the M-of-N plan (SEC-17). Later: HSM or cloud KMS signers.
**Files:** `.github/workflows/security-nightly.yml`, `os/update/README.md`, `handbook/keys/HIERARCHY.md` (brief 30 B4.6).
**Acceptance test:** a workflow on a non-`main` branch that echoes `${{ secrets.ONEMIND_RAUC_SIGNING_KEY }}` gets an empty value; the security workflow on `main` pauses for reviewer approval before the RAUC signing job; `grep -n 'secrets.ONEMIND_' .github/workflows/*.yml` shows every key use inside a job that declares `environment:`.

### H-12 · k3s secrets encryption on
**Why:** Secrets (model API keys, agent tokens) sit unencrypted in the k3s datastore under `/data/k3s`, and in every backup of it.
**Change:** add `--secrets-encryption` to `k3s.service` and `secrets-encryption: true` to the config written by `install.sh`. Add `k3s secrets-encrypt status` to the health gate's k3s check.
**Files:** `os/rootfs/layers/base/usr/lib/systemd/system/k3s.service:17`, `deploy/install.sh` (`k3s_server`), `os/gate/onemind-k3s-check`.
**Acceptance test:** `k3s secrets-encrypt status` → `Encryption Status: Enabled`; after creating a Secret with value `canary-…`, `grep -a canary- <data-dir>/server/db/state.db` finds nothing (`/data/k3s` on the image, `/var/lib/rancher/k3s` on the developer install).

### H-25 · Installer writes the variable the gateway reads
**Why:** `install.sh:509` writes `ONEMIND_GATEWAY_URL`, but the gateway reads `ONEMIND_PUBLIC_URL` (`feat/gateway-agent-mcp`: `core/onemind_core/config.py:101`), so the installer's URL is ignored and agent Secrets get `http://<hostname>:8080`. Small, but it decides which URL carries an agent token.
**Files:** `deploy/install.sh` (`gateway_service`).
**Acceptance test:** after install, the gateway's startup log does not print "ONEMIND_PUBLIC_URL not set", and the agent Secret's `ONEMIND_GATEWAY_URL` equals the URL the installer printed.

---

## P1 — before daily use with real secrets and several nodes

### H-08 · Bind the scan to what is installed
**Why:** `scan.json` says "pass" and a date (`scan.py:31-66`); edit the manifests afterwards and the box still treats them as scanned.
**Change:** add to the §11.1 record `subject: {manifest_sha256, rendered_sha256, images: [digest…]}`, where `rendered_sha256` is the sha256 of the canonical rendered YAML from H-02. At approval the gateway renders, hashes, and compares; any mismatch → `409 stale_precondition` ("app changed since its scan"). Contract change to §11.1 in its own PR.
**Files:** `sdk/contracts/poc-v0.md` §11.1, `sdk/tools/app-gate`, `core/onemind_core/scan.py`, `core/onemind_core/actions.py` (approve path).
**Acceptance test:** change one character in `apps/uptime-kuma/manifests/deployment.yaml` after a passing scan → approval returns 409 with that reason; revert → approval succeeds.

### H-09 · Token lifecycle
**Why:** no expiry, no rotation, no per-device tokens, no record of use (threat model §4.3, §5.1).
**Change:** tokens become rows in the ledger (hash, id, principal, `kind: person|agent|device`, `created_at`, `expires_at`, `last_used_at`, `revoked_at`); the YAML file stays as the bootstrap for the first owner. New tokens are `om_<kind>_<32 bytes base64url>` (a prefix lets gitleaks and GitHub secret scanning find them). API and CLI: `onemind token create|list|revoke|rotate` (owner only, each an audited event). Every audit line carries `token_id`. File reloads write `auth.tokens_reloaded` with the count and a hash of the set. Static ids starting with `agent:` are refused. Minimum length for hand-written tokens rises to 32. The installer prints the owner token only when stdout is a terminal, and the join command reads the token from a file or stdin, not from `--token`.
**Files:** `core/onemind_core/auth.py`, `ledger.py`, `app.py`, new routes under `/v1/tokens`, `cmd/onemind/`, `deploy/install.sh:551-554`.
**Acceptance test:** an expired token → 401; a revoked token → 401 within one request; `last_used_at` updates; `onemind token rotate <id>` returns a new token and the old one fails; adding a hash to the YAML file produces an `auth.tokens_reloaded` audit line; gitleaks with a rule for `om_` finds a planted token in a test file.

### H-10 · Signed, anchored audit checkpoints
**Why:** the hash chain catches an edit in the middle, not a full rewrite or a cut tail (`audit.py:140-163`).
**Change:** every N lines and every hour, append an `audit.checkpoint` line `{seq, head_hash}` signed with an Ed25519 key kept outside the audit file's directory (`/data/onemind/keys/audit.key`, 0600; TPM-sealed later). Publish each checkpoint to NATS **JetStream** on a stream replicated to other nodes when they exist, and let the phone app store the latest. `onemind-audit-verify` checks signatures and, given a remembered checkpoint, that the file still contains it. OS update results (`internal/update` status) are also written to the chain.
**Files:** `core/onemind_core/audit.py`, `core/onemind_core/bus.py`, `internal/update/state.go` (an event hook), contract §3 "Audit".
**Acceptance test:** rewrite the whole file with a valid recomputed chain → verify fails (signature); delete the last 50 lines → verify against the last published checkpoint fails ("checkpoint seq 1200 missing"); an unmodified log passes.

### H-11 · LUKS2 data partition from first boot
**Why:** a stolen disk gives every app's data and the k3s datastore (`os/boards/*/layout.yaml:13`).
**Change:** as decided in SEC-01/SEC-02/SB-5: format `onemind-data` as LUKS2 at install or first boot; generate a recovery key, show it once (installer screen and dashboard first-run), store nothing of it on disk; unlock by TPM2 (PCR 7 + signed PCR 11 policy, systemd initrd) where present, by passphrase or network unlock otherwise. Keep the layout unchanged (no repartition).
**Files:** `os/boards/*/layout.yaml`, `os/assemble/assemble.py`, initrd units under `os/rootfs/layers/base/usr/lib/systemd/system/`, the P3 installer.
**Acceptance test:** battery T-SB5: unlock on slot A, slot B and after rollback; `cryptsetup luksDump /dev/disk/by-partlabel/onemind-data` shows LUKS2 + a TPM2 token; with Secure Boot off the data stays locked and the recovery key opens it; the image boots with the data partition removed into a "locked" state, not a crash.

### H-13 · "What will change" approval card
**Why:** the owner approves "install X" without seeing what X does; an agent's `reason` is shown with no warning that an AI wrote it (threat model §4.1, §4.2). This is also the strongest feature against competitors.
**Change:** at request time the gateway renders the app (H-02) and stores a **plan**: objects by kind, images with digests, ports, volumes and sizes, egress (H-04), the security rating (H-19), and `plan_sha256`. `POST /v1/actions/{id}/approve` takes `{"plan_sha256": …}` and refuses with 409 if it differs from a fresh render. The dashboard and phone show the plan, label `reason` as "written by agent <id>", and the phone asks for biometric or passcode before sending.
**Files:** `core/onemind_core/actions.py`, `executors.py`, `ledger.py`, contract §3 (new optional field), `dashboard/src/pages/Approvals.tsx`, mobile approval screen.
**Acceptance test:** approve with a stale `plan_sha256` → 409; edit the manifests between request and approval → 409 and the card shows the new plan; the agent's `reason` renders inside a block marked as agent-written; approving without `plan_sha256` still works in v0 but logs `plan_unchecked` in the audit (to be removed in v1).

### H-14 · Cap pending actions per agent
**Why:** an agent can flood the Approvals screen (approval fatigue).
**Change:** at most 5 `awaiting_approval` actions per agent principal (setting); the sixth gets `409 conflict` "too many pending requests" and is audited.
**Files:** `core/onemind_core/actions.py` (`_create`), `ledger.py` (count query).
**Acceptance test:** an agent creates 5 actions, the 6th returns 409; after the owner denies one, a new request succeeds; owners are not capped.

### H-15 · No third-party build code as root
**Why:** `npm ci` and the Go build run as root on the box (`install.sh:401-404`); npm install scripts execute with root rights.
**Change:** prefer prebuilt, signed release artifacts for `onemindd` and the dashboard (the release pipeline already builds them); when building on the box, run the builds as the unprivileged `onemind` user (or a throwaway `DynamicUser` via `systemd-run`) with `npm ci --ignore-scripts`, and copy the result into place as root.
**Files:** `deploy/install.sh` (`dashboard_build`, `onemindd_install`).
**Acceptance test:** a test `package.json` with a `postinstall` that runs `id -u > /tmp/who` either does not run or writes a non-zero uid; the installed dashboard and binaries are owned by root and not writable by `onemind`.

### H-17 · Encrypt pod traffic between nodes
**Why:** with more than one node, pod traffic (including agent tokens and gateway calls) crosses the LAN in clear (flannel VXLAN).
**Change:** `flannel-backend: wireguard-native` in the k3s server config (image and installer). This is a cluster-creation setting; set it before the founder's data moves.
**Files:** `os/rootfs/layers/base/usr/lib/systemd/system/k3s.service:17` (or `/etc/rancher/k3s/config.yaml`), `deploy/install.sh` (`k3s_server`).
**Acceptance test:** with two nodes, `tcpdump -i <lan-if> udp port 8472` shows no VXLAN traffic and `udp port 51820` shows WireGuard; a pod-to-pod HTTP request across nodes still works.

### H-18 · Content-Security-Policy and security headers
**Why:** the token sits in `sessionStorage`; any injected script on the origin can read it. The schema forces `https://` on `metadata.source` only; `metadata.links` is not in the schema, and the built-in manifest check (used when the schema file is missing) checks no URL (`catalog.py:59-88`). The Market renders `source` as a link (`dashboard/src/pages/Market.tsx:136`).
**Change:** the gateway adds `Content-Security-Policy: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; connect-src 'self'`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer` to every response; the schema adds `metadata.links` with the same `^https://` pattern and `builtin_check` refuses `source` and `links.*` that do not start with `https://`; the gateway refuses to start with the kubernetes executor when the schema file is missing.
**Files:** `core/onemind_core/app.py`, `core/onemind_core/catalog.py`, `core/onemind_core/config.py`, `sdk/schema/onemind.app.schema.json`.
**Acceptance test:** `curl -I /` shows the headers; a fixture app with `source: javascript:alert(1)` is skipped in builtin mode; starting with `ONEMIND_EXECUTOR=kubernetes` and no schema exits with an error.

### H-23 · Owner-approved node join
**Why:** a leaked join token lets any machine join, forever; joining is the one state change that does not go through an approval. The printed token does pin the server CA (`K10<hash>::`, checked in the k3s source, threat model §7).
**Change:** a new action type `node.join`: a joining machine runs `onemind join <hub>`, which shows a short code; the request appears in Approvals with the machine's board, arch and OS from its heartbeat; on approval the gateway issues a one-hour k3s bootstrap token (`k3s token create --ttl 1h`; the default TTL is 24 h, `pkg/cli/cmds/token.go:55-59` at v1.37.2+k3s1) plus the node's NATS credentials (H-06), and deletes the token (`k3s token delete <id>`) as soon as the node registers, because a bootstrap token can be reused until it expires. The long-lived agent token is no longer printed.
**Files:** `deploy/install.sh` (`k3s_server`, `k3s_agent`, banner), `core/onemind_core/actions.py` (new type), contract §3, `cmd/onemind/`.
**Acceptance test:** the token printed or issued starts with `K10` and contains `::`; a second join with the same token after the first node registered fails (token deleted); a join token older than 1 h fails; a join without owner approval gets no credentials; the audit shows `node.join` with approver.

### H-24 · `onemindd` local API on loopback by default
**Why:** `:7480` gives hardware, versions and update state to the whole LAN without auth (`internal/agent/agent.go:29`).
**Change:** default `ONEMIND_AGENT_ADDR=127.0.0.1:7480`; the hub learns the same data from heartbeats. Remote access later behind the node's credentials.
**Files:** `internal/agent/agent.go:29`, `cmd/onemindd/main.go`, `deploy/systemd/onemindd.service`, contract §1 (note).
**Acceptance test:** `curl http://<node-ip>:7480/healthz` from another machine → refused; `curl http://127.0.0.1:7480/healthz` on the node → 200; the health gate's G6 check still passes.

### H-26 · `/data` override of `update.conf`: policy keys only
**Why:** the image's `update.conf` promises an owner override under `/data` (`feat/os-security-pipeline`: `os/rootfs/layers/base/etc/onemind/update.conf:5`). If that override accepts `tuf_root_dir`, `rauc_binary` or `reboot_command` (`feat/onemindd-updater`: `internal/update/config.go:159-175`), a write to `/data` becomes root code execution.
**Change:** when the override is implemented, it may set only `channel`, `window`, `policy`, `require_snapshot`, `check_interval`, `restic_repository`, `restic_password_file`; any other key in the override is an error. Path and binary keys come only from the read-only `/etc` file.
**Files:** `internal/update/config.go`, `os/rootfs/layers/base/etc/onemind/update.conf`, `internal/update/README.md`.
**Acceptance test:** an override file with `rauc_binary = /data/x` makes `onemindd update` refuse to start with "key not allowed in /data override"; an override with `window = 01:00-02:00` is applied.

### H-28 · Tell the owner when protection stops
**Why:** an expired TUF timestamp, a stale app scan or a broken audit chain are logged but nobody is told.
**Change:** emit notification events (ntfy / phone push per D-005) for: update check failing for more than 48 h, an installed app's scan becoming `fail` or older than 7 days, `audit verify` failing at startup, a new token or node created.
**Files:** `internal/update/engine.go`, `core/onemind_core/` (notifications module of the notifications stream).
**Acceptance test:** point `update.conf` at a channel with an expired timestamp and fake the clock forward 48 h → one notification; break one audit line and restart → one notification.

### H-29 · App web UIs behind the gateway's reverse proxy
**Why:** app links open `http://host:port` directly (`dashboard/src/pages/Home.tsx:83`); exposing apps by `NodePort` is forbidden by H-02, so apps need a safe way in.
**Change:** the gateway (or an ingress it controls) proxies `https://<box>:8443/apps/<id>/` (or per-app subdomains) to the app's `ClusterIP` Service after checking the session (forward-auth), so each app UI sits behind OneMind sign-in, the way umbrelOS's app proxy works (pattern only; umbrelOS is PolyForm-NC, no code).
**Files:** new `core/onemind_core/proxy.py` or an ingress manifest, `dashboard/src/pages/Home.tsx`.
**Acceptance test:** an unauthenticated request to an app path → redirect to sign-in; with a session → the app's page; the app's Service is not reachable on any node port.

---

## P2 — before other people run it

### H-16 · Rule: no cookie auth without CSRF protection
Write in `core/README.md` that the gateway authenticates only by `Authorization` header; if a cookie session is ever added (for OIDC), it must be `SameSite=Strict`, `Secure`, `HttpOnly` plus an anti-CSRF token. **Acceptance test:** a unit test asserts no route reads `request.cookies`.

### H-19 · Signed catalog, publisher keys, security rating (SEC-11)
Sign the app catalog as TUF targets (same machinery as OS updates) so the box verifies the catalog it receives; compute a 1-8 rating (HAOS pattern [C-W6-054]) from the H-02 rule file; show it on the Market card; below a threshold, require an explicit "I understand" and forbid agent principals. **Files:** `sdk/`, `core/onemind_core/catalog.py`, `dashboard/src/pages/Market.tsx`. **Acceptance test:** a catalog with one byte changed is refused; an app with rating < 4 cannot be requested by an agent (403).

### H-20 · Resource limits
Body size ≤ 64 KiB on `/v1`, per-IP rate limit on 401s, cap on registered nodes, audit file rotation with the checkpoint carried over. **Files:** `core/onemind_core/app.py`, `nodes.py`, `audit.py`. **Acceptance test:** a 1 MiB POST → 413; 1,000 distinct fake node ids → the registry stays at the cap and logs once.

### H-21 · Role-based reads
Define what `adult` and `guest` may read (e.g. guests see neither actions nor node details). **Files:** `core/onemind_core/app.py`, contract §3. **Acceptance test:** a guest token gets 403 on `GET /v1/actions`.

### H-22 · Per-tool scopes for agents (SEC-12 item 1)
Agent tokens carry scopes (`nodes:read`, `apps:read`, `actions:request:app.install`…); `/mcp` lists only allowed tools. **Files:** `core/onemind_core/mcp.py`, `auth.py`. **Acceptance test:** an agent without `actions:request` sees two tools and `request_action` returns an error.

### H-27 · Lock the boot line
Ship the UKI route (SB-1) with the command line inside the signed UKI, and enrol the db key (SB-7); until then, a GRUB superuser password on images sold to others. **Files:** `os/assemble/`, `os/boards/x86_64-efi/`. **Acceptance test:** battery under OVMF Secure Boot: editing the command line at boot is impossible or fails to boot.

### H-30 · Provenance and SBOM on every release
GitHub artifact attestations (SLSA Build L3 with an isolated reusable workflow, SEC-10), an SBOM per image and per app, attached to the release. **Files:** `.github/workflows/`. **Acceptance test:** `gh attestation verify <bundle> --repo onemindos/ONEMINDOS` succeeds; the release has an SPDX or CycloneDX SBOM.

---

## Dependencies at a glance
- H-02 before H-08 and H-13 (both need the checked render).
- H-05 before H-06 TLS, H-29 and the mobile shell.
- H-06 before H-23 (node credentials).
- H-01 + H-02 + H-03 together close the executor finding; any one alone leaves a path open.
- H-12 and H-17 are cluster-creation settings: do them before the founder's data moves, or plan a re-key.
