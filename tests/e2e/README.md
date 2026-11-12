<!-- SPDX-License-Identifier: Apache-2.0 -->
# tests/e2e: the golden path, end to end

**Serves:** contract [`sdk/contracts/poc-v0.md`](../../sdk/contracts/poc-v0.md) §3 (gateway, actions,
audit), §5 (dashboard), §6 (deploy), §7 and §11.3 (agent principals, `/mcp`), §10.3 ("nothing
unscanned runs"), and the §12 routes as they ship. Epic **E2E-GOLDEN** in
[`docs/leap/STATUS.md`](../../docs/leap/STATUS.md).

> **In plain words.** Unit tests prove each part works on its own. This test proves the parts work
> **together**, the way a person would use them: install OneMind on a fresh Debian machine with the
> real installer, open the dashboard in a real browser, sign in, see the machine, install an app,
> approve it, watch it run, remove it. Then an AI agent asks for the same app over MCP (the protocol
> AI assistants use to call tools), cannot approve it itself, and the owner approves it. Finally the
> audit log, a hash chain where every line includes the fingerprint of the line before, is
> re-checked so nobody can have quietly edited history.

## What runs

| Step | How | Proves |
|---|---|---|
| 1. A real hub | [`harness/run.sh`](harness/run.sh): fresh Debian 13 VM, `deploy/install.sh --role hub` | the installer works from scratch (k3s, NATS, onemindd, gateway, dashboard) |
| 2. Owner flow | [`specs/01-owner-golden-path.spec.ts`](specs/01-owner-golden-path.spec.ts), Chromium | sign in (and a wrong token refused), hub node **Online**, Market trust facts, an unscanned app's Install disabled with the reason, Install → Approvals → Approve → **succeeded** → Installed, Remove → Approve → **succeeded** |
| 3. Agent flow | [`specs/02-agent-mcp.spec.ts`](specs/02-agent-mcp.spec.ts), official MCP TypeScript client (`@modelcontextprotocol/sdk`, MIT) over Streamable HTTP | the agent lists tools (no approve/deny tool), reads nodes and apps, `request_action` → `awaiting_approval`; its own approve is `403`; a person token on `/mcp` is `403`; the owner sees "AI agent e2e-agent" on the card and approves; the agent's removal is approved the same way |
| 4. Audit | [`specs/03-audit.spec.ts`](specs/03-audit.spec.ts) + [`lib/audit.ts`](lib/audit.ts) | the hub's whole `audit.jsonl` re-hashes (a second, TypeScript implementation of `core/onemind_core/audit.py`); every action of this run names the right requester, an owner approver and `action.succeeded`; the agent's refused approve is audited |
| 5. Contract check | `deploy/verify/verify.sh` on the hub, after the suite | the scripted §3/§11 checks (45 items) and the full audit file again |
| 6. Not merged yet | [`specs/04-landing-streams.spec.ts`](specs/04-landing-streams.spec.ts) | skipped with the reason; see below |

Unit tests for the audit verifier (no hub, no browser) are the `unit` project:
`npm run test:unit`. [`unit/fixtures/audit-sample.jsonl`](unit/fixtures/audit-sample.jsonl) was
written by core's own `AuditLog`, so the TypeScript check is pinned to the Python one.

### Steps that wait for other streams (skipped with a reason, switch on by themselves)
Contract §12 says a route exists only once its module ships. Each step below looks for its route in
`/openapi.json` (or its name in `GET /v1/instance` `features`) and runs as soon as it is there; the
owning stream then deepens the step.

| Step | Waits for | Detects |
|---|---|---|
| Open the installed app through the box app proxy | CORE-NET-P1 (networking stream: mesh proxy) | `features` has `app-proxy` |
| `GET /v1/me` names owner and agent | DEV-API-5, CORE-SEC-2 (identity) | `/v1/me` |
| Passkey registration options | CORE-SEC-2 (passkeys, F-2), CORE-SEC-10 (household accounts) | `/v1/auth/passkeys/register/options` |
| Box CA published for pairing | CORE-SEC-1 (HTTPS, F-1) | `/v1/tls` |
| Events stream (SSE) | DEV-API-8 | `/v1/events` |
| Alerts | CORE-NOTIFY-1 | `/v1/alerts` |
| Backup status | CORE-BACKUP-2, CORE-BACKUP-8 | `/v1/backups/status` |
| `GET /v1/audit/verify` agrees | CORE-SEC-6, DEV-API-9 | `/v1/audit/verify` |

## Run it

```sh
# Locally (macOS or Linux with Lima 2.x): about 2.5 minutes on an Apple-silicon Mac
tests/e2e/harness/run.sh --backend lima            # --keep leaves the VM up, --reuse re-runs on it

# Linux with KVM (what CI does on ubuntu-24.04)
sudo apt-get install qemu-system-x86 qemu-utils cloud-image-utils
tests/e2e/harness/run.sh --backend qemu

# Against a hub you already have (no VM): the suite only
cd tests/e2e && npm ci --ignore-scripts && npx playwright install chromium
E2E_HUB_URL=http://127.0.0.1:8080 E2E_OWNER_TOKEN_FILE=owner.token E2E_AGENT_TOKEN_FILE=agent.token npm test
```

Without `E2E_HUB_URL` every golden step is skipped (with that reason) instead of failing.

**What the harness does, in order.** Start the VM (Lima: `template:debian-13`, no host mounts, only
the gateway port forwarded to `127.0.0.1:18080`; QEMU: the Debian 13 `genericcloud` image pinned by
sha512 in [`os/versions.lock.yaml`](../../os/versions.lock.yaml) `e2e_vm`, a cloud-init seed with a
fresh ssh key, user-mode network with `127.0.0.1` port forwards, KVM when `/dev/kvm` is usable). Copy
the working tree in. Run `install.sh --role hub`. Keep the owner token it prints once. Add an agent
principal `e2e-agent` the way an owner adds one by hand (a `sha256:` line in `/etc/onemind/tokens.yaml`).
Give the test app a scan record (below). Run Playwright from the host, then `verify.sh` on the hub.
Save the evidence and delete the VM.

**The scan record is a stand-in.** The hub refuses to install an app without a passing scan from
the last 7 days (§10.3, F-7). The §9.4 app-gate that writes `scan.json` (PR #25) does not run on the
hub yet, so the harness writes one for `ntfy` only, marked `"e2e_fixture"`. Every other app stays
unscanned, and step 2 checks that the dashboard blocks it. When the app-gate lands, the harness should
run it instead (follow-up).

**Secrets.** The owner token and the generated agent token live in `out/secrets/` (0700, never
uploaded) and in `/root/e2e/` inside the VM. On GitHub both are masked. `install.log` is saved with
the owner and join tokens redacted. The suite reads tokens only from files.

**Artifacts** (`out/`, uploaded by CI without `secrets/` and `vm/`): `summary.txt`, `harness.log`,
`install.log`, `verify.txt`, `playwright-report/` (HTML), `test-results/` (a screenshot and a video
per browser test, a trace on failure), `junit.xml`, `audit.jsonl`, `journal.txt` (gateway, onemindd,
NATS), `k8s.txt`.

## CI
[`.github/workflows/e2e.yml`](../../.github/workflows/e2e.yml): on pull requests that touch `core/`,
`dashboard/`, `deploy/`, `cmd/`, `internal/`, `apps/` or `tests/e2e/`, and nightly. Job `unit`
(typecheck, verifier unit tests, shellcheck) and job `golden-path` (KVM enabled by a udev rule, then
`run.sh --backend qemu`). Actions are pinned by commit as listed in `os/versions.lock.yaml`;
`test/unit/test_versions_lock.py` enforces it.

## Run record

### 2026-11-12, Lima, from scratch (Apple-silicon Mac, Lima 2.3.0, arm64)
`tests/e2e/harness/run.sh --backend lima` on a fresh VM (deleted afterwards):

```text
backend: lima
host: Darwin arm64
guest: Debian GNU/Linux 13 (trixie), kernel 6.12.115+deb13.1-cloud-arm64, arm64
install.sh: rc 0 in 46s
playwright: rc 0          16 passed, 8 skipped (the 8 steps above that wait for other streams)
verify.sh: rc 0, Summary: 45 passed, 0 failed, 0 skipped   (incl. "§3 audit file hash chain intact")
total: 150s
```
The approved install of ntfy ran `kubectl apply -k` through the k3s kubectl, and the removal deleted
the namespace, for both the owner's and the agent's requests. No token appeared in any saved file
outside `out/secrets/` (checked with `grep -F` for both tokens over `out/`).

Earlier runs on the same day found three problems in the suite itself, all fixed before the run above:
a link name shared by the top bar and the Home page ("Market" vs "Browse the Market"), accessible-name
matching that is a substring by default (cards "Install ntfy" also matched "ntfy"), and the audit
check looking at every action on a reused hub instead of this run's.
