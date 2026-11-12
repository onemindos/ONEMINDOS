<!-- SPDX-License-Identifier: Apache-2.0 -->
# Dogfood: running your own services on OneMind (CORE-DOGFOOD)

**Date:** 2026-11-12 · **Status:** proposal · **Plan epics:** spans E0–E13 · **Deeper docs:** core-alignment §4.4 and §5 (ranked backlog); [DEPLOYMENTS.md](DEPLOYMENTS.md) (migration kit) · **Serves:** founder focus 2026-11-12 ("replace his own cluster with OneMind OS and use it daily").

> **Explain it like I am the founder**
> This page is the checklist for moving real services onto OneMind, written for anyone who runs their own self-hosted stack, not for one particular setup.
> It lists what a daily-use platform must provide (sign-in, a way in from outside, secrets, monitoring, GPUs, databases, backups) and which spec delivers each one.
> Services move in waves, each wave only after its gate passes, and the old system stays running until the new one has a verified restore.

## 1. Goals and non-goals

| Goals | Non-goals |
|---|---|
| A generic capability checklist for self-hosters moving to OneMind | Describing anyone's private systems, names or addresses |
| Gates: what must pass before each class of service moves | Moving everything at once |
| Gaps found while dogfooding become issues in the right spec | Re-creating a full enterprise platform (service mesh, multi-cluster GitOps) |

## 2. The capability checklist

| Need | What "done" looks like | Delivered by | Epic(s) | State today |
|---|---|---|---|---|
| Identity | owner passkey; household accounts; sessions; apps behind one sign-in (forward-auth) | SECURITY | CORE-SEC-2, CORE-SEC-10, H-29 | static tokens only |
| Ingress | per-app subdomains on HTTPS, no node ports; exposure review page (LAN / tailnet / public) | SECURITY, DASHBOARD | CORE-SEC-1, CORE-DASH-7, REM-B1 | none |
| Remote access | Tailscale or Headscale app, off by default, enabled by approval; tailnet certificates | this page | CORE-DOGFOOD-3 | none |
| Public exposure | optional: make one app public via a tunnel or the owner's own reverse proxy, as a warned request | this page | CORE-DOGFOOD-3 | none |
| Secrets | write-only per-service secrets, encrypted at rest, in backups | DEPLOYMENTS, SECURITY | CORE-DEPLOY-4, CORE-SEC-5 | none |
| Your own services | deploy from kustomize/Helm/Compose; history; rollback | DEPLOYMENTS | CORE-DEPLOY-1…3 | executor only |
| Databases | Postgres (and others) as Market apps with backup hooks and retain storage | BACKUPS | CORE-BACKUP-1, -5 | none |
| Storage | `onemind-local` Retain class; delete data only by action | BACKUPS | CORE-BACKUP-1 | k3s default `Delete` |
| Backups | hourly, three keys, off-site, verified-restore badge | BACKUPS | CORE-BACKUP-2…7 | pre-update snapshot only (in flight) |
| Monitoring | node and app CPU/memory/disk, logs per app, uptime checks; a metrics stack as Market apps for those who want dashboards | DASHBOARD, this page | CORE-DOGFOOD-4 | heartbeat only; uptime-kuma app |
| Alerts | one inbox, private phone push, repairs | NOTIFICATIONS | CORE-NOTIFY-1…5 | none |
| GPU | NVIDIA nodes detected; GPU apps placed only there; device plugin installed by the OS | FABRIC, this page | CORE-FABRIC-4, CORE-DOGFOOD-5 | detection only |
| Messaging | NATS with per-app accounts inside the subject grammar (E7) | SECURITY | CORE-SEC-4, later E7 | open bus |
| Multi-node | approved join; placement; drain | FABRIC | CORE-FABRIC-1…4 | heartbeat + dev install |
| Updates | OS security channel with rollback; app updates through approval | UPDATES | CORE-UPDATE-1…6 | in flight |
| Automation | schedules and triggers as requests; standing approvals | AUTOMATION | CORE-AUTO-1…4 | none |
| AI agents | agent principals; MCP with no approve tool; kill switch | SECURITY | CORE-SEC-6 | in flight (`feat/gateway-agent-mcp`) |
| Phone | pair, approve, push | MOBILE | CORE-MOBILE-2…5 | shell in flight |

## 3. Migration waves and gates

| Wave | Service class (generic) | Gate before moving (all must pass) |
|---|---|---|
| 0 | Nothing moves; the box runs seed apps for 7 days | SANDBOX acceptance; SEC-1 HTTPS; UPDATE-1 landed; backups to USB with one manual test restore |
| 1 | Stateless tools (status pages, link pages, uptime checks) | SEC-2 passkey; NOTIFY-1 inbox; DEPLOY-1…3 |
| 2 | Personal stateful apps with small data (notes, bookmarks, recipes) | BACKUP-2…4 with off-site copy; BACKUP-7 badge green for 2 weeks |
| 3 | Shared household services (password manager, home automation, media) | SEC-10 accounts; FABRIC-1 second node; REM access app; restore drill onto a second machine |
| 4 | AI and GPU workloads | FABRIC-4 placement; DOGFOOD-5 GPU; agent principals with scopes (H-22) |
| 5 | Public-facing services | exposure review; public path as an approved request; rate limits (H-20); website self-hosted first as the test |

**Rule for every wave:** run old and new side by side; switch DNS only after the new copy has passed a verified restore; keep the old copy read-only for 14 days.

## 4. Design details for the pieces this page owns

### 4.1 Migration flow (uses DEPLOYMENTS CORE-DEPLOY-6)
```console
$ onemind migrate check ./exported/bookmarks/
OK    Deployment/bookmarks        limits set, non-root
FIX   image ghcr.example/bm:2.3   no digest → pin with: onemind migrate pin
FIX   PVC data (storageClass: fast-ssd) → onemind-local
DROP  Ingress/bookmarks           → served at https://bookmarks.onemind.local (gateway proxy)
MOVE  Secret/bookmarks-env        → onemind secret set bookmarks <KEY> (values not imported)
FAIL  ClusterRole/bookmarks-read  cluster-scoped objects are not allowed (rules v1, K-01)
1 blocking, 4 fixable
$ onemind migrate import ./exported/bookmarks/ --name bookmarks
private app bookmarks r1 created → action a_201 deploy.apply awaiting_approval
$ onemind restore --from-dir ./exported/bookmarks-data --app bookmarks   # data copy as an approved restore
```

### 4.2 Remote access app (CORE-DOGFOOD-3)
A Market app (`apps/tailscale` or `apps/headscale`), off by default; enabling it is an action with a warning that tailnet certificate names are public in certificate-transparency logs, so default machine names are non-identifying (research 12 §8.1). The exposure page lists every app's reachability and who approved it.

### 4.3 Monitoring (CORE-DOGFOOD-4)
Core shows per-node and per-app CPU, memory, disk and recent logs (UX-P4) from the kubelet and `onemindd`; no metrics stack is required. Owners who want history install a metrics/logs stack from the Market (Prometheus-compatible, retain storage, backup hooks); its alerts flow into the alert centre via a webhook receiver.

### 4.4 GPU (CORE-DOGFOOD-5)
On nodes where `onemindd` detects an NVIDIA GPU, the OS installs the NVIDIA container toolkit and device plugin (GPU Operator on x86 tiers; device plugin + CDI on Jetson, ARCHITECTURE §6) as core components in `onemind-system`, not as an app. Apps request `requires.gpu: true` and get `nvidia.com/gpu: 1` limits through the executor; an app cannot ask for host devices directly (SANDBOX).

### 4.5 Same call, every surface
```python
client.actions.request("deploy.apply", deploy_id="bookmarks", rev="r1")          # Python
```
```ts
await om.actions.request({ type: "deploy.apply", params: { deploy_id: "bookmarks", rev: "r1" } }); // TS
```
```go
om.Actions.Request(ctx, onemind.Action{Type: "deploy.apply", Params: map[string]any{"deploy_id": "bookmarks", "rev": "r1"}}) // Go
```
**MCP:** an assistant can run `migrate check` style reads through a future tool and can request `deploy.apply`; the owner approves each wave's switch.

## 5. Security model
- Imported manifests pass the same fence as Market apps; cluster-scoped objects never import.
- Secret values are never imported from files; they are re-entered with `onemind secret set` so they never pass through an agent or a chat log.
- Public exposure is always an owner-approved, logged, reversible request, listed on the exposure page.
- Dogfood notes in issues and docs use generic names only (no hostnames, addresses, tailnets or personal data).

## 6. Versioning and compatibility
- The checklist is versioned with this file; each row's "state today" is updated in the PR that changes it.
- `onemind migrate` outputs carry `generatedBy` so later converters can upgrade them (DEPLOYMENTS §5).

## 7. Test plan and acceptance

| Test | Pass when |
|---|---|
| Wave gate check | `onemind doctor --wave N` (proposed) prints pass/fail per gate row; a wave is entered only when all pass |
| Side by side | For each moved service: new copy healthy 7 days, verified restore green, old copy read-only 14 days, then retired |
| Daily use | 30 consecutive days with the founder's daily services on OneMind and no manual SSH fix (each fix needed becomes an issue) |
| Fixture migration | Generic fixtures (stateless web app, app + Postgres, GPU job) migrate in CI on k3d |

## 8. Build steps

| Epic | Step | Effort | Depends on |
|---|---|---|---|
| CORE-DOGFOOD-1 | `onemind doctor --wave N` gate checker | S | – |
| CORE-DOGFOOD-2 | Migration fixtures and docs (uses CORE-DEPLOY-6) | M | DEPLOY-6 |
| CORE-DOGFOOD-3 | Remote access app + exposure review | M | SEC-1 |
| CORE-DOGFOOD-4 | Core per-app metrics and logs; metrics stack as Market app | M | DASH-1 |
| CORE-DOGFOOD-5 | GPU enablement in the OS (toolkit, device plugin, placement) | M | FABRIC-4, image stream |
| CORE-DOGFOOD-6 | Run waves 0–5; log gaps as issues against the owning spec | L | all above |

## 9. Who owns which files

| Branch (proposed) | Files |
|---|---|
| `feat/doctor` | `cmd/onemind/cli/doctor.go`, new `internal/doctor/` |
| `feat/remote-access` | `apps/tailscale/` or `apps/headscale/`, new `core/onemind_core/exposure.py` |
| `feat/gpu` | image stream `os/` (toolkit, device plugin manifests), `internal/detect/` |
| `feat/app-metrics` | new `core/onemind_core/metrics.py`, `dashboard/src/pages/AppDetail.tsx` logs tab |
| Hotspots (serialized) | `cmd/onemind/main.go`, `os/versions.lock.yaml` (GPU components), `core/onemind_core/app.py` |
