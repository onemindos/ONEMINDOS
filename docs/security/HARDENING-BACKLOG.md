<!-- SPDX-License-Identifier: Apache-2.0 -->
# OneMind OS core: hardening backlog (edition 2)

**Status:** edition 2, 2026-11-12, from the code on `main` at `ad557c6` plus the fixes in this PR. Ranked. Every open item names the file it touches and an **acceptance test**: a check that fails today and passes once the fix is in. Edition 1 (PR #18) is in git history; ids (`H-01`…`H-30`) are stable, new ones continue at `H-31`.
**Companion:** [`THREAT-MODEL.md`](THREAT-MODEL.md) (edition 2) holds the reasoning and the line evidence for each row.
**Serves:** brief 30 B6 (D-B6.1, D-B6.2, D-B6.5), B4.5 (SB-1…SB-10), B9, SEC-01…SEC-17, Wave G item 3 ([`docs/leap/NEXT-WAVE.md`](../leap/NEXT-WAVE.md)), founder focus 2026-11-12 (replace the founder's cluster with OneMind OS).

> **Explain it like I am the founder**
> This is the to-do list for making the box safe to live on, in the order to do it. P0 means "before anything you care about runs on it", P1 "before daily use with real secrets", P2 "before other people use it".
> Since the first edition, about half of the 30 items are done or mostly done. This edition adds 12 more (H-31 to H-42): two are already fixed in this PR, ten are new work. The four P0 items still open are all infrastructure (HTTPS, NATS passwords, CI signing keys, and the OS image's k3s settings), not gateway code.

## How the ranking works
- **P0**: a malicious app or a LAN device gets full control, or a secret that signs updates is exposed, without it.
- **P1**: before daily use with real secrets and more than one node.
- **P2**: before anyone else runs it (Market launch, first sale).

Inside a tier, items are in the order to build them. **Owner** is the build stream that owns the file (gateway = `core/`, deploy = `deploy/`, image = `os/`, pipeline = `sdk/tools` + CI, updater = `internal/update`, dashboard, mobile). Items touching code that only exists on one of Agent A's open branches are listed under "For Agent A" at the end, not here.

## Summary of open work

| ID | Tier | Item | Owner | Evidence (main) |
|---|---|---|---|---|
| H-05 | P0 | HTTPS with a per-box CA; plain HTTP on loopback only; bind default localhost | gateway, deploy | `deploy/install.sh:29, 524`; `core/onemind_core/__main__.py:19`; `ca.py` not imported by `app.py` |
| H-06 | P0 | NATS users with per-subject permissions + TLS | deploy, gateway, onemindd | `deploy/install.sh:314-320`; `core/onemind_core/bus.py:50-58` |
| H-07 | P0 | Signing keys behind a protected environment; split RAUC and TUF signers | pipeline | `.github/workflows/security-nightly.yml:151, 217-219, 293-295, 392-394` (no `environment:`) |
| H-01 / H-12 (image half) | P0 | OS image k3s: PSA admission config + `--secrets-encryption` (the developer install has both) | image | `os/rootfs/layers/base/usr/lib/systemd/system/k3s.service:17` |
| H-13 | P1 | Plan rendered and stored at request time, shown on the card, bound by `plan_sha256` | gateway, dashboard, mobile, desktop | `core/onemind_core/identity/service.py:951, 989` read it; nothing sets it |
| H-35 | P1 | Minting an API token needs passkey step-up once passkeys are on | gateway | `core/onemind_core/identity/service.py:766` (compare `:687`) |
| H-36 | P1 | Static-file tokens: expiry or retirement; do not print the owner token to scrollback | gateway, deploy | `core/onemind_core/auth.py:100-144`; `deploy/install.sh:570` |
| H-34 | P1 | Reverse proxy must strip identity's cookie names and use household sessions before it is wired | gateway | `core/onemind_core/proxy.py:61, 87-101, 298` vs `identity/service.py:134-135` |
| H-42 | P1 | `app.remove` deletes app data: snapshot first and say so on the card | gateway, backups | `core/onemind_core/executors.py:253-264` |
| H-04 (host half) | P1 | Host nftables dropping pod CIDR to node ports | image, deploy | SECURITY.md §7a "Not done here" |
| H-08 | P1 | Bind `scan.json` to a digest of what is installed | pipeline, gateway | `core/onemind_core/scan.py:35-51`; the box records `rendered_sha256` (`executors.py:316`) but does not compare |
| H-10 | P1 | Signed, anchored audit checkpoints | gateway | `core/onemind_core/audit.py` |
| H-11 | P1 | LUKS2 on `onemind-data` from first boot | image | `os/boards/x86_64-efi/layout.yaml:13` |
| H-15 | P1 | No third-party build code as root on the box | deploy | `deploy/install.sh` (`dashboard_build`, `onemindd_install`) |
| H-17 | P1 | Encrypt pod traffic between nodes (flannel wireguard-native) | deploy, image | no `wireguard` in `deploy/install.sh` or `os/rootfs` |
| H-23 | P1 | Owner-approved k3s join; short-lived join token (mesh enrolment keys are already single-use, 15 min: `internal/mesh/enroll.go`) | deploy, gateway | `deploy/install.sh` agent-token |
| H-28 | P1 | Alert the owner on update freeze, scan expiry, audit-chain break | gateway, updater | all notification sources exist except the audit-chain check |
| H-33 | P1 | Sign-in limiter and challenge table must survive a proxy and a spray | gateway | `identity/service.py:95-124, 424-431`; `guard.py` bucket table |
| H-26 | P1 | `/data` override of `update.conf` may set policy keys only (not re-reviewed in edition 2) | updater, image | `internal/update/config.go` |
| H-21 | P2 | Role-based reads: `GET /v1/actions` shows kubectl tails to every principal | gateway | `core/onemind_core/routers/actions.py:43-55` |
| H-22 | P2 | Per-tool capability scopes for agents | gateway | `core/onemind_core/mcp/tools.py` |
| H-19 | P2 | Signed catalog, publisher keys, security rating | pipeline, gateway | `core/onemind_core/catalog.py` |
| H-20 | P2 | Remaining limits: audit rotation | gateway | `core/onemind_core/audit.py` |
| H-27 | P2 | Lock the boot line (UKI + Secure Boot) | image | `os/assemble/` |
| H-30 | P2 | Build provenance and SBOM on every release (not re-reviewed) | pipeline | `.github/workflows/` |
| H-37 | P2 | First-owner setup is not atomic | gateway | `identity/service.py:495-503` |
| H-38 | P2 | `login.failed` writes the typed username to the audit (people paste passwords there) | gateway | `identity/service.py:384` |
| H-39 | P2 | Agent-sent notifications: label as written by an app, never render as system text | gateway, clients | `notify/service.py:536-560` |
| H-40 | P2 | Notification channels: clear `lan` when an owner is demoted; cap outbound tests by adults | gateway | `routers/notifications.py:292, 317, 345-356` |
| H-41 | P2 | Seal TOTP seeds with the notify `SecretBox` | gateway | `identity/models.py:44-45` |

## Closed or fixed since edition 1

| ID | Item | Where it landed |
|---|---|---|
| H-01 (gateway, developer install) | Pod Security cluster default + per-app `restricted` | `deploy/k8s/psa.yaml`, `deploy/install.sh:247-251`, `executors.py:188-199` (namespace labels) |
| H-02 | Manifest allowlist: render, check every object, apply the checked bytes | `sdk/policy/app-objects.yaml`, `core/onemind_core/policy.py:145-470`, `executors.py:296-330, 256` (app-gate does not call the checker yet: follow-up) |
| H-03 | Gateway RBAC without cluster-wide rights | `deploy/k8s/gateway-rbac.yaml`, `executors.py:201-214` |
| H-04 (cluster half) | Default-deny NetworkPolicy per app | `policy.py:472`, `executors.py:245-246` |
| H-09 | Token lifecycle: create, list, expire, rotate, revoke, prefix, last-used | `identity/service.py:766-860`, `identity/scopes.py` |
| H-12 (developer install) | k3s Secrets encryption on, checked | `deploy/install.sh:251, 269` |
| H-14 | Pending-action cap | `actions.py:197-212`, `guard.py` (`max_pending`), `mcp/limits.py:27` |
| H-16 | CSRF rule | cookie sessions need the `OneMind-CSRF` header on unsafe methods: `identity/service.py:215-238` |
| H-18 | CSP and security headers; https-only `source` | `guard.py:32-45`, `catalog.py:130-132` |
| H-20 (most) | Body limit, rate buckets, auth back-off | `guard.py`; node count cap added in this PR (`nodes.py`) |
| H-24 | `onemindd` API on loopback | `internal/agent/agent.go:31` |
| H-25 | Installer writes the variable the gateway reads | `deploy/install.sh:528` |
| **H-31** (new) | **Alert `fix` with `approve` skipped passkey step-up and the approve scope** | **Fixed in this PR**: `routers/notifications.py:208-250`; tests `test_identity_notify.py::test_fix_with_approve_cannot_skip_the_approval_gates`, `::test_fix_with_approve_still_works_without_passkeys` |
| **H-32** (new) | **Node registry grew without bound (any LAN device can invent node ids on an open NATS)** | **Fixed in this PR**: `nodes.py` `MAX_NODES = 256`; test `test_nodes_catalog.py::test_registry_is_bounded_against_invented_node_ids` |
| H-29 | App web UIs behind a reverse proxy | Built (`proxy.py`) but not wired; see H-34 |

A scripted route inventory (`core/tests/test_route_authz.py`) now fails CI if a route is added without authentication or an owner-only operation stops refusing agents, guests and adults.

---

## New items (H-33 to H-42)

### H-33 · Sign-in limiter and challenge table under a proxy or a spray
**Why:** the failure limiter keys on `request.client.host` (`identity/service.py:95-124`, `source_of`); when the reverse proxy is wired every household member shares one address and ten typos lock everyone out for 15 minutes. Separately, 1000 open login challenges (`:424-431`) can be filled by one source in two minutes, and the bucket table in `guard.py` holds 10,000 keys, so 10,000 bogus tokens reset real principals' buckets to full.
**Change:** key the limiter on the forwarded client address only for a trusted proxy peer (`X-Forwarded-For` from the proxy's address), limit open challenges per source, and evict buckets by least recently used only among keys that have no debt.
**Files:** `core/onemind_core/identity/service.py`, `core/onemind_core/guard.py`.
**Acceptance test:** with the proxy header from a trusted peer, ten failures from client A do not block client B; one source cannot hold more than 20 open login challenges.

### H-34 · Make the reverse proxy safe before it is wired
**Why:** `proxy.py` strips only a cookie called `onemind_session` (`:61, 298`) and the default resolver knows only static tokens (`:87-101`). Identity's cookies are `__Host-onemind_session` and `__Host-onemind_csrf` (`identity/service.py:134-135`), so once the proxy is added an app would receive them, and household sign-ins and per-app sharing would not apply.
**Change:** strip every cookie whose name starts with `onemind_` or `__Host-onemind_`; resolve the person through the identity authenticators and `can_open` (per-app sharing); forbid `Set-Cookie` for those names from apps.
**Files:** `core/onemind_core/proxy.py`, `core/tests/test_proxy.py`.
**Acceptance test:** a request carrying `__Host-onemind_session` reaches the upstream without it; a guest not in an app's `people` gets 403 at the proxy.

### H-35 · Passkey step-up to mint an API token
**Why:** a stolen owner session cookie can `POST /v1/tokens` with all scopes for 365 days (`identity/service.py:766`), a durable foothold. Creating users already steps up (`:687`). Such a token cannot approve once passkeys are on (threat model §5.1) but can read everything and file requests.
**Change:** call `require_step_up` in `create_token` when the new token has any scope beyond `*:read`, or always for `*`.
**Files:** `core/onemind_core/identity/service.py`.
**Acceptance test:** with a passkey registered, a password session without a recent passkey gets `401 step_up_required` for a token with `*`; a read-only token still mints.

### H-36 · Static-file tokens
**Why:** they never expire, skip the scope table and the step-up for everything but approvals (`auth.py:100-144`), and the installer prints the owner token to the terminal (`deploy/install.sh:570`).
**Change:** after the first household owner exists, mark the file owner token break-glass (works only from loopback or the console), log each use, and let the installer write the token to a 0600 file instead of the banner.
**Files:** `core/onemind_core/auth.py`, `context.py`, `deploy/install.sh`.
**Acceptance test:** after setup, the file token from a non-loopback address gets 401 and every use of it is audited.

### H-37 · First-owner setup is atomic
**Why:** "no accounts yet" and the insert are separate steps (`identity/service.py:495-503`); two simultaneous setups with the install token can both succeed.
**Change:** insert inside one transaction guarded by a unique singleton row, or take the process lock.
**Acceptance test:** two concurrent `POST /v1/auth/setup` calls: one 201, one 409.

### H-38 · Do not write typed usernames to the audit
**Why:** `login.failed` stores the first 64 characters typed in the username box (`identity/service.py:384`); people paste passwords there, and the audit is readable by adults and streamed.
**Change:** store a keyed hash of the name plus whether it exists.
**Acceptance test:** the audit line for a failed login contains no part of the submitted username.

### H-39 · Agent-sent notifications are untrusted text
**Why:** an app's agent can put any text in the owner's inbox under its own topic (`notify/service.py:536-560`); a persuasive "urgent: approve this" is a phishing vector.
**Change:** clients render the sender as "written by app <id>", never in the style of system alerts; titles may not contain approval wording links.
**Acceptance test:** inbox JSON marks `source: agent` and clients show it (dashboard, mobile).

### H-40 · Channel destinations after demotion; outbound abuse
**Why:** a channel keeps `lan: true` forever (`routers/notifications.py:292, 317`), even if its owner is later demoted; adults can fire 5 outbound tests a minute at any public host (`:345-356`).
**Change:** recompute `lan` from the person's current role at send time; cap total channels per person and outbound sends per hour.
**Acceptance test:** demote an owner, the next send to a LAN-address channel is refused.

### H-41 · Seal TOTP seeds
**Why:** `users.totp_secret` and `totp_pending` are clear text in the database (`identity/models.py:44-45`).
**Change:** seal with the notify `SecretBox` (row id as associated data), migrate on read.
**Acceptance test:** the stored column is not valid base32.

### H-42 · `app.remove` and data
**Why:** removal deletes the namespace, which deletes the app's volumes (`executors.py:253-264`); the owner's card says "remove" and nothing more.
**Change:** the card says "this deletes the app's data"; the removal action first takes a snapshot of the app's volumes through the backup unit when one exists, or refuses unless the request is marked `delete_data: true` and the owner approves that wording.
**Files:** `core/onemind_core/actions.py`, `executors.py`, `internal/backup`.
**Acceptance test:** removing an app with a volume and no snapshot is refused unless `delete_data` is set.

---

## Items still open from edition 1 (original text)

The sections below are edition 1's text for items that are still open or partly done, unchanged except for a status line. Their evidence column is in the summary above.
### H-05 · HTTPS on the LAN, plain HTTP on loopback only
**Status (edition 2): open.**
**Why:** the owner token crosses the LAN in clear text (`core/onemind_core/config.py:86`; `feat/deploy-v0`: `install.sh:29`). REC-DEC-30 already says the developer install binds the dashboard to localhost.
**Change:** at first start the gateway creates a per-box CA and a server certificate (hostname, `<hostname>.local`, the box's addresses; ECDSA P-256, 1-year leaf, auto-renew) under `/data/onemind/tls/` (mode 0600, owner `onemind`). It serves HTTPS on `:8443` and keeps `:8080` on `127.0.0.1` for local tools and health checks. `deploy/install.sh` defaults `--gateway-bind 127.0.0.1` for the HTTP port and prints the CA fingerprint plus a pairing QR (fingerprint + URL, **no token** in the QR). `ONEMIND_PUBLIC_URL` defaults to the `https://` URL. App agent Secrets carry the CA bundle (`ONEMIND_GATEWAY_CA`).
**Files:** `core/onemind_core/config.py`, `core/onemind_core/__main__.py`, new `core/onemind_core/tls.py`, `deploy/install.sh`, `deploy/systemd/onemind-gateway.service`, `core/onemind_core/executors.py` (`AgentSecret.manifest`).
**Acceptance test:** from another machine, `curl http://<box>:8080/healthz` → connection refused; `curl --cacert box-ca.pem https://<box>:8443/healthz` → 200; `curl -k` against a different box's CA with `--pinnedpubkey` → fails; `testssl.sh` reports TLS 1.2+ only, no weak ciphers; the CA private key file is mode 0600 and not world-readable.
### H-06 · NATS authentication, per-subject permissions, TLS
**Status (edition 2): open.**
**Why:** anyone on the LAN or in a pod can impersonate any node and read or forge `onemind.audit` (`feat/deploy-v0`: `install.sh:281-285`).
**Change:** `nats.conf` gets an `authorization { users = [...] }` block with nkeys (NATS public-key auth, no passwords on disk in clear): user `gateway` (subscribe `onemind.node.*.status`, publish `onemind.audit`), one user per node issued at join (publish **only** `onemind.node.<node_id>.status`), deny everything else. Add `tls {}` with the box CA (H-05). `onemindd` reads its seed from `/etc/onemind/nats.nk` (0600) and `ONEMIND_NATS_URL=tls://…`; `bus.py` passes `nkeys_seed` and the CA. Cap the registry at a configured node count.
**Files:** `deploy/install.sh` (`nats_install`, `onemindd_install`), `deploy/systemd/onemind-nats.service`, `core/onemind_core/bus.py:50-58`, `core/onemind_core/nodes.py`, `internal/agent/agent.go:211-228`, `cmd/onemindd/main.go`.
**Acceptance test:** `nats pub onemind.node.<hub-id>.status '{}'` with no credentials → `Authorization Violation`; with node A's credentials publishing as node B → permission violation and the hub's node B entry is unchanged; `nats sub onemind.audit` with node credentials → permission violation; the gateway still lists every real node; `nats-server --signal reload` keeps connections.
### H-07 · Signing keys behind a protected environment, split signers
**Status (edition 2): open.**
**Why:** RAUC and all TUF online keys are repository secrets read by one workflow with no `environment:` (`feat/os-security-pipeline`: `.github/workflows/security-nightly.yml:151, 217-219, 293-295, 392-394`). A workflow pushed to any branch can read them. The unattended 6-hourly `timestamp` job also holds the targets and snapshot keys, because it re-signs them near expiry (`security-nightly.yml:392-394`).
**Change:** move each key to its own GitHub **environment** (`release-rauc`, `tuf-targets`, `tuf-timestamp`) restricted to `main` with required reviewers for `release-rauc` and `tuf-targets`; only the 6-hourly timestamp job runs unattended, and it gets the timestamp key only (snapshot too if it must re-sign snapshot); re-signing targets before expiry moves to the reviewed job. Split the jobs so one job never holds both the RAUC key and the TUF targets key. Use `tuf-repo.py init-root --threshold 2` for the root (already supported) and document the M-of-N plan (SEC-17). Later: HSM or cloud KMS signers.
**Files:** `.github/workflows/security-nightly.yml`, `os/update/README.md`, `handbook/keys/HIERARCHY.md` (brief 30 B4.6).
**Acceptance test:** a workflow on a non-`main` branch that echoes `${{ secrets.ONEMIND_RAUC_SIGNING_KEY }}` gets an empty value; the security workflow on `main` pauses for reviewer approval before the RAUC signing job; `grep -n 'secrets.ONEMIND_' .github/workflows/*.yml` shows every key use inside a job that declares `environment:`.
### H-01 · Pod Security cluster-wide: `baseline` enforced, `restricted` per app
**Status (edition 2): partial.** Gateway and developer install done; the OS image half is open.
**Why:** without an enforced level, an app manifest with `privileged`, `hostPath` or `hostNetwork` owns the node (threat model §4.5, E1-E3). A cluster default does not stop an app that ships its own `Namespace` object and relabels itself (E5): a namespace label overrides the default. E5 is closed by H-02 (no `Namespace` objects) and H-03 (no PSA label changes by the gateway).
**Change:** ship an `AdmissionConfiguration` with `PodSecurity` defaults `enforce: baseline`, `audit/warn: restricted`, `exemptions.namespaces: [kube-system, onemind-system]` (and nothing else). The gateway labels each `app-<id>` `pod-security.kubernetes.io/enforce: restricted`, except an app that runs as root, which keeps `baseline` and shows "runs as root" on its approval card (H-13) and rating (H-19). `restricted` cannot be the cluster default today: the app gate accepts root with all capabilities dropped (`feat/app-pipeline`: `sdk/tools/app-gate:282-285`), and `apps/home-assistant` is such an app (`apps/home-assistant/manifests/deployment.yaml:42-48`). Start k3s with `--kube-apiserver-arg=admission-control-config-file=/etc/rancher/k3s/psa.yaml` (k3s hardening guide, docs.k3s.io/security/hardening-guide). Same file written by `deploy/install.sh` into `/etc/rancher/k3s/config.yaml`.
**Files:** `os/rootfs/layers/base/usr/lib/systemd/system/k3s.service:17`, new `os/rootfs/layers/base/etc/rancher/k3s/psa.yaml`, `deploy/install.sh` (`k3s_server`).
**Acceptance test:** on a fresh image and a fresh developer install, in an unlabelled namespace, `kubectl apply -f pod.yaml` is **refused** with a PodSecurity error for each of: `privileged: true`, `hostPath`, `hostNetwork`, `hostPID`, `capabilities.add: [NET_ADMIN]`; in an `app-<id>` labelled `restricted`, a pod with no `runAsNonRoot` is also refused. With H-03 in place, `kubectl label ns app-test pod-security.kubernetes.io/enforce=privileged --overwrite` using the gateway's kubeconfig is refused. `ntfy` and `uptime-kuma` install under `restricted` and reach Ready; `home-assistant` installs under `baseline` and reaches Ready (making it run non-root is a follow-up for the app, not an exemption).
### H-12 · k3s secrets encryption on
**Status (edition 2): partial.** Developer install done (`deploy/install.sh:251, 269`); the OS image half is open.
**Why:** Secrets (model API keys, agent tokens) sit unencrypted in the k3s datastore under `/data/k3s`, and in every backup of it.
**Change:** add `--secrets-encryption` to `k3s.service` and `secrets-encryption: true` to the config written by `install.sh`. Add `k3s secrets-encrypt status` to the health gate's k3s check.
**Files:** `os/rootfs/layers/base/usr/lib/systemd/system/k3s.service:17`, `deploy/install.sh` (`k3s_server`), `os/gate/onemind-k3s-check`.
**Acceptance test:** `k3s secrets-encrypt status` → `Encryption Status: Enabled`; after creating a Secret with value `canary-…`, `grep -a canary- <data-dir>/server/db/state.db` finds nothing (`/data/k3s` on the image, `/var/lib/rancher/k3s` on the developer install).
### H-13 · "What will change" approval card
**Status (edition 2): open.** `plan_sha256` is read by the passkey code and sent by the clients but never produced by the server.
**Why:** the owner approves "install X" without seeing what X does; an agent's `reason` is shown with no warning that an AI wrote it (threat model §4.1, §4.2). This is also the strongest feature against competitors.
**Change:** at request time the gateway renders the app (H-02) and stores a **plan**: objects by kind, images with digests, ports, volumes and sizes, egress (H-04), the security rating (H-19), and `plan_sha256`. `POST /v1/actions/{id}/approve` takes `{"plan_sha256": …}` and refuses with 409 if it differs from a fresh render. The dashboard and phone show the plan, label `reason` as "written by agent <id>", and the phone asks for biometric or passcode before sending.
**Files:** `core/onemind_core/actions.py`, `executors.py`, `ledger.py`, contract §3 (new optional field), `dashboard/src/pages/Approvals.tsx`, mobile approval screen.
**Acceptance test:** approve with a stale `plan_sha256` → 409; edit the manifests between request and approval → 409 and the card shows the new plan; the agent's `reason` renders inside a block marked as agent-written; approving without `plan_sha256` still works in v0 but logs `plan_unchecked` in the audit (to be removed in v1).
### H-04 · Default-deny network per app + host firewall
**Status (edition 2): partial.** The per-app default-deny NetworkPolicy is built (`policy.py:472`); the host nftables half is open.
**Why:** a pod can reach NATS, the gateway, the k3s API and the kubelet on the node's addresses, and other apps (threat model §4.5 E3, §4.7).
**Change:** at `app.install`, apply a `NetworkPolicy` in `app-<id>` that denies all ingress and egress except DNS to `kube-system`, ingress from the gateway proxy (H-29), and egress declared in a new manifest field `spec.network.egress` (default: internet only, no RFC 1918 ranges). On the host, an nftables table that drops new connections from the pod CIDR to the node's ports `4222, 6443, 7480, 8080, 8443, 10250` except the ones the core needs (k3s ships the kube-router NetworkPolicy controller, enabled by default).
**Files:** `core/onemind_core/executors.py` (`plan`), new `os/rootfs/layers/base/etc/nftables.d/onemind.nft` + a unit, `deploy/install.sh`, `sdk/schema/onemind.app.schema.json` (`spec.network`).
**Acceptance test:** from a pod in `app-uptime-kuma`: `nc -z <node-ip> 4222`, `:8080`, `:10250` and `<other-app-svc>:port` all time out; `nslookup kubernetes.default` works; an HTTPS request to a public site works; the gateway's `GET /healthz` from the host still works.
### H-08 · Bind the scan to what is installed
**Status (edition 2): partial.** The box now checks the bytes it applies; the scan record is still not bound to them.
**Why:** `scan.json` says "pass" and a date (`scan.py:31-66`); edit the manifests afterwards and the box still treats them as scanned.
**Change:** add to the §11.1 record `subject: {manifest_sha256, rendered_sha256, images: [digest…]}`, where `rendered_sha256` is the sha256 of the canonical rendered YAML from H-02. At approval the gateway renders, hashes, and compares; any mismatch → `409 stale_precondition` ("app changed since its scan"). Contract change to §11.1 in its own PR.
**Files:** `sdk/contracts/poc-v0.md` §11.1, `sdk/tools/app-gate`, `core/onemind_core/scan.py`, `core/onemind_core/actions.py` (approve path).
**Acceptance test:** change one character in `apps/uptime-kuma/manifests/deployment.yaml` after a passing scan → approval returns 409 with that reason; revert → approval succeeds.
### H-10 · Signed, anchored audit checkpoints
**Status (edition 2): open.**
**Why:** the hash chain catches an edit in the middle, not a full rewrite or a cut tail (`audit.py:140-163`).
**Change:** every N lines and every hour, append an `audit.checkpoint` line `{seq, head_hash}` signed with an Ed25519 key kept outside the audit file's directory (`/data/onemind/keys/audit.key`, 0600; TPM-sealed later). Publish each checkpoint to NATS **JetStream** on a stream replicated to other nodes when they exist, and let the phone app store the latest. `onemind-audit-verify` checks signatures and, given a remembered checkpoint, that the file still contains it. OS update results (`internal/update` status) are also written to the chain.
**Files:** `core/onemind_core/audit.py`, `core/onemind_core/bus.py`, `internal/update/state.go` (an event hook), contract §3 "Audit".
**Acceptance test:** rewrite the whole file with a valid recomputed chain → verify fails (signature); delete the last 50 lines → verify against the last published checkpoint fails ("checkpoint seq 1200 missing"); an unmodified log passes.
### H-11 · LUKS2 data partition from first boot
**Status (edition 2): open.**
**Why:** a stolen disk gives every app's data and the k3s datastore (`os/boards/*/layout.yaml:13`).
**Change:** as decided in SEC-01/SEC-02/SB-5: format `onemind-data` as LUKS2 at install or first boot; generate a recovery key, show it once (installer screen and dashboard first-run), store nothing of it on disk; unlock by TPM2 (PCR 7 + signed PCR 11 policy, systemd initrd) where present, by passphrase or network unlock otherwise. Keep the layout unchanged (no repartition).
**Files:** `os/boards/*/layout.yaml`, `os/assemble/assemble.py`, initrd units under `os/rootfs/layers/base/usr/lib/systemd/system/`, the P3 installer.
**Acceptance test:** battery T-SB5: unlock on slot A, slot B and after rollback; `cryptsetup luksDump /dev/disk/by-partlabel/onemind-data` shows LUKS2 + a TPM2 token; with Secure Boot off the data stays locked and the recovery key opens it; the image boots with the data partition removed into a "locked" state, not a crash.
### H-15 · No third-party build code as root
**Status (edition 2): open.**
**Why:** `npm ci` and the Go build run as root on the box (`install.sh:401-404`); npm install scripts execute with root rights.
**Change:** prefer prebuilt, signed release artifacts for `onemindd` and the dashboard (the release pipeline already builds them); when building on the box, run the builds as the unprivileged `onemind` user (or a throwaway `DynamicUser` via `systemd-run`) with `npm ci --ignore-scripts`, and copy the result into place as root.
**Files:** `deploy/install.sh` (`dashboard_build`, `onemindd_install`).
**Acceptance test:** a test `package.json` with a `postinstall` that runs `id -u > /tmp/who` either does not run or writes a non-zero uid; the installed dashboard and binaries are owned by root and not writable by `onemind`.
### H-17 · Encrypt pod traffic between nodes
**Status (edition 2): open.**
**Why:** with more than one node, pod traffic (including agent tokens and gateway calls) crosses the LAN in clear (flannel VXLAN).
**Change:** `flannel-backend: wireguard-native` in the k3s server config (image and installer). This is a cluster-creation setting; set it before the founder's data moves.
**Files:** `os/rootfs/layers/base/usr/lib/systemd/system/k3s.service:17` (or `/etc/rancher/k3s/config.yaml`), `deploy/install.sh` (`k3s_server`).
**Acceptance test:** with two nodes, `tcpdump -i <lan-if> udp port 8472` shows no VXLAN traffic and `udp port 51820` shows WireGuard; a pod-to-pod HTTP request across nodes still works.
### H-23 · Owner-approved node join
**Status (edition 2): partial.** Mesh enrolment uses single-use 15-minute keys; the k3s join token still never expires.
**Why:** a leaked join token lets any machine join, forever; joining is the one state change that does not go through an approval. The printed token does pin the server CA (`K10<hash>::`, checked in the k3s source, threat model §7).
**Change:** a new action type `node.join`: a joining machine runs `onemind join <hub>`, which shows a short code; the request appears in Approvals with the machine's board, arch and OS from its heartbeat; on approval the gateway issues a one-hour k3s bootstrap token (`k3s token create --ttl 1h`; the default TTL is 24 h, `pkg/cli/cmds/token.go:55-59` at v1.37.2+k3s1) plus the node's NATS credentials (H-06), and deletes the token (`k3s token delete <id>`) as soon as the node registers, because a bootstrap token can be reused until it expires. The long-lived agent token is no longer printed.
**Files:** `deploy/install.sh` (`k3s_server`, `k3s_agent`, banner), `core/onemind_core/actions.py` (new type), contract §3, `cmd/onemind/`.
**Acceptance test:** the token printed or issued starts with `K10` and contains `::`; a second join with the same token after the first node registered fails (token deleted); a join token older than 1 h fails; a join without owner approval gets no credentials; the audit shows `node.join` with approver.
### H-26 · `/data` override of `update.conf`: policy keys only
**Status (edition 2): not re-reviewed.**
**Why:** the image's `update.conf` promises an owner override under `/data` (`feat/os-security-pipeline`: `os/rootfs/layers/base/etc/onemind/update.conf:5`). If that override accepts `tuf_root_dir`, `rauc_binary` or `reboot_command` (`feat/onemindd-updater`: `internal/update/config.go:159-175`), a write to `/data` becomes root code execution.
**Change:** when the override is implemented, it may set only `channel`, `window`, `policy`, `require_snapshot`, `check_interval`, `restic_repository`, `restic_password_file`; any other key in the override is an error. Path and binary keys come only from the read-only `/etc` file.
**Files:** `internal/update/config.go`, `os/rootfs/layers/base/etc/onemind/update.conf`, `internal/update/README.md`.
**Acceptance test:** an override file with `rauc_binary = /data/x` makes `onemindd update` refuse to start with "key not allowed in /data override"; an override with `window = 01:00-02:00` is applied.
### H-28 · Tell the owner when protection stops
**Status (edition 2): partial.** Sources for approvals, nodes, updates, backups and scans exist; the audit-chain check does not.
**Why:** an expired TUF timestamp, a stale app scan or a broken audit chain are logged but nobody is told.
**Change:** emit notification events (ntfy / phone push per D-005) for: update check failing for more than 48 h, an installed app's scan becoming `fail` or older than 7 days, `audit verify` failing at startup, a new token or node created.
**Files:** `internal/update/engine.go`, `core/onemind_core/` (notifications module of the notifications stream).
**Acceptance test:** point `update.conf` at a channel with an expired timestamp and fake the clock forward 48 h → one notification; break one audit line and restart → one notification.
### H-29 · App web UIs behind the gateway's reverse proxy
**Status (edition 2): built, not wired.** See H-34 for what must change first.
**Why:** app links open `http://host:port` directly (`dashboard/src/pages/Home.tsx:83`); exposing apps by `NodePort` is forbidden by H-02, so apps need a safe way in.
**Change:** the gateway (or an ingress it controls) proxies `https://<box>:8443/apps/<id>/` (or per-app subdomains) to the app's `ClusterIP` Service after checking the session (forward-auth), so each app UI sits behind OneMind sign-in, the way umbrelOS's app proxy works (pattern only; umbrelOS is PolyForm-NC, no code).
**Files:** new `core/onemind_core/proxy.py` or an ingress manifest, `dashboard/src/pages/Home.tsx`.
**Acceptance test:** an unauthenticated request to an app path → redirect to sign-in; with a session → the app's page; the app's Service is not reachable on any node port.

---
### H-19 · Signed catalog, publisher keys, security rating (SEC-11)
**Status (edition 2): open.**
Sign the app catalog as TUF targets (same machinery as OS updates) so the box verifies the catalog it receives; compute a 1-8 rating (HAOS pattern [C-W6-054]) from the H-02 rule file; show it on the Market card; below a threshold, require an explicit "I understand" and forbid agent principals. **Files:** `sdk/`, `core/onemind_core/catalog.py`, `dashboard/src/pages/Market.tsx`. **Acceptance test:** a catalog with one byte changed is refused; an app with rating < 4 cannot be requested by an agent (403).
### H-21 · Role-based reads
**Status (edition 2): open.**
Define what `adult` and `guest` may read (e.g. guests see neither actions nor node details). **Files:** `core/onemind_core/app.py`, contract §3. **Acceptance test:** a guest token gets 403 on `GET /v1/actions`.
### H-22 · Per-tool scopes for agents (SEC-12 item 1)
**Status (edition 2): open.**
Agent tokens carry scopes (`nodes:read`, `apps:read`, `actions:request:app.install`…); `/mcp` lists only allowed tools. **Files:** `core/onemind_core/mcp.py`, `auth.py`. **Acceptance test:** an agent without `actions:request` sees two tools and `request_action` returns an error.
### H-27 · Lock the boot line
**Status (edition 2): open.**
Ship the UKI route (SB-1) with the command line inside the signed UKI, and enrol the db key (SB-7); until then, a GRUB superuser password on images sold to others. **Files:** `os/assemble/`, `os/boards/x86_64-efi/`. **Acceptance test:** battery under OVMF Secure Boot: editing the command line at boot is impossible or fails to boot.
### H-30 · Provenance and SBOM on every release
**Status (edition 2): not re-reviewed.**
GitHub artifact attestations (SLSA Build L3 with an isolated reusable workflow, SEC-10), an SBOM per image and per app, attached to the release. **Files:** `.github/workflows/`. **Acceptance test:** `gh attestation verify <bundle> --repo onemindos/ONEMINDOS` succeeds; the release has an SPDX or CycloneDX SBOM.

---

---

## For Agent A (code that exists only on open branches)

Nothing in this pass was found in code that exists only on an Agent A branch, because those branches were not read. Re-review when they merge, in this order of risk:
1. `feat/automation` (a new way to cause actions: confirm it cannot call `ActionService.approve`, and that automation tokens never get approve scope; `scopes.py:44` already lists `automation:write` as person-only).
2. `feat/app-secrets` (new secret storage: encrypt at rest, never in audit or action results).
3. `feat/files` and `feat/photos-server` (new inbound uploads and outbound shares: path traversal, size limits, SSRF if they fetch URLs).
4. `feat/storage-actions` and `feat/backups-on` (execution of the plans that are plan-only on main: destructive steps need owner approval and the checks in `internal/storage/plan.go:105-125`).
5. `feat/migrate-kit` (reads another system's data: treat it as untrusted input).
6. `feat/dashboard-v2`, `feat/deploy-port27` (UI and port changes: keep CSP intact, do not widen the bind).

## Dependencies at a glance

- H-05 before H-33 (client addresses) and before removing cleartext from the phone app (`mobile/app.json:67`).
- H-06 needs the node join flow (H-23) so per-node credentials can be issued at approval.
- H-13 (plan card) before the automation branch lands, so automation approvals show the same plan.
- H-34 before the proxy is imported by `app.py`.
- H-11 and the image half of H-12 before the founder moves real data.
