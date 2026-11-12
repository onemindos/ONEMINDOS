# The `onemind` CLI (complete spec)

**Status:** spec, 2026-11-12. Nothing in this file is built unless the "Exists today" column says so.
**Epic ids:** DEV-CLI-1 … DEV-CLI-14 (section 12).
**Serves:** brief 30 BD-02 (Go for the CLI), B4.2 (`onemind update …`), 29 §7 (plugin CLI), contract `sdk/contracts/poc-v0.md` §2, §3, §10, §11; `docs/strategy/core-alignment.md` ONB-B1, UX-B2, DEP-P1, FAB-P1, PLG-P2, MOB-B3 (arch worktree, in progress).
**Siblings (same `docs/leap/dev/` folder, written in parallel):** the REST API spec, the SDK specs (Go, Python, TypeScript), the MCP spec and the plugin SDK spec. Where this file names an SDK function or a gateway endpoint that does not exist yet, the sibling spec owns its final shape; this file only says what the CLI needs from it.

> **Explain it like I am the founder**
> `onemind` is one program you run in a terminal, on your Mac or on the box itself. It does everything the dashboard does: see your machines, install apps, approve what your AI asked for, check the audit record, run backups and updates, add a node with a QR code.
> It also builds things: it starts a new app or plugin, checks it with the same gate the store uses, and runs it on your dev box.
> It is a thin layer over the Go SDK, so every command is also one SDK call and one REST call, and `--json` gives a script the same data.
> It never lets an AI skip you. `onemind mcp` hands an agent the three request-only tools, and approving still needs you.

---

## 1. Goals and non-goals

| Goals | Non-goals (for this spec) |
|---|---|
| One binary for macOS (arm64, amd64) and Linux (amd64, arm64), also shipped inside the OneMind image | A Windows build (later; nothing here blocks it) |
| Every dashboard task has a CLI command, and every command has `--json` | A full-screen terminal UI (TUI) |
| Built only on the public Go SDK: the CLI gets no private gateway calls | Talking to Kubernetes, NATS or the ledger directly; the CLI goes through the gateway (or `onemindd` on the box) like any client |
| Contexts like `kubectl`: one config file, many boxes, safe credential storage | Managing the founder's existing (non-OneMind) cluster |
| Stable exit codes and output so shell scripts and CI can rely on them | Running AI models or agents itself |
| Works headless on the box (SSH, rescue, no browser) | Replacing the first-boot wizard (that is `onemind init`, ONB-B1, a separate spec; it reuses this CLI's config layer) |
| The developer surface: app and plugin scaffolding, validation, local gate, dev install, packing, publishing, a stdio MCP bridge | Robot, drone and TAK commands (later; they will be plugins that register CLI verbs through E6) |
| The core rule holds: agents and plugins only **request**; a person who is an owner **approves**; the OS **executes**; everything is **audited** | Any command that approves on an agent's behalf, or any `--yes` that bypasses the owner's step-up |

---

## 2. What exists today

| Thing | Where | State |
|---|---|---|
| `onemind node info`, `onemind nodes`, `onemind version` (stdlib `flag`, no config file, `--hub`/`ONEMIND_HUB`, `--token`/`ONEMIND_TOKEN`, `--json` on `nodes`) | `cmd/onemind/main.go`, `cmd/onemind/main_test.go`, `cmd/onemind/README.md` | On `main` |
| Local detection reused by `node info` | `internal/detect/`, `internal/heartbeat/` | On `main` |
| `onemind update status\|check\|apply` (runs the update engine in-process, needs root except `status`) | `cmd/onemind/update.go`, `internal/update/` | In flight, `updater` worktree (commit `8bf2fbc`) |
| Gateway REST: `/healthz`, `/v1/instance`, `/v1/nodes`, `/v1/apps`, `/v1/actions` (+ approve, deny) | `core/onemind_core/app.py`, `actions.py`, `nodes.py`, `catalog.py` | On `main` |
| Hash-chained audit log and a Python `verify()` | `core/onemind_core/audit.py` (`python -m onemind_core.audit`) | On `main` |
| Scan gate, agent principals, `POST /mcp` with `list_nodes`, `list_apps`, `request_action` | `core/onemind_core/scan.py`, `mcp.py` | In flight, `gwmcp` worktree (`6dffda5`) |
| `app-scaffold`, `app-gate` (writes `scan.json`), `app-readme`, `validate-apps` (Python) | `sdk/tools/` | In flight, `pipeline` worktree (`0aa6d93`, `eed7a79`); `validate-apps` is on `main` |
| Manifest schema | `sdk/schema/onemind.app.schema.json` | On `main`; extended in `pipeline` |
| Go SDK | `sdk/go/` | **Not built** (sibling spec) |
| Audit, backup, fabric, notify, rules and token endpoints on the gateway | – | **Not built** (section 7 lists what the CLI needs) |

---

## 3. Command tree

```
onemind
├── login | logout                         sign in to a box, forget the credential
├── context  list | use | show | rename | delete
├── status                                 one-screen health of the current box
├── nodes    [list] | info <id>            machines in this OneMind (alias: node)
│   └── node info --local                  this machine's heartbeat (today's `node info`)
├── apps     list | info <id> | install <id> | remove <id>
├── actions  list | info <id> | watch | approve <id> | deny <id>
├── audit    verify | tail
├── backup   status | now | list | verify <snap>   (alias: backup run = now)
├── restore  <snap> [--app <id>]   (alias: backup restore)
├── update   status | check | apply
├── fabric   qr | join <code> | leave | remove <node>     (alias: node join <code>)
├── notify   test | devices                         (NOTIFICATIONS.md, MOBILE.md)
├── alerts   [list] | fix <id>                    alert centre (NOTIFICATIONS.md)
├── auto     list | create | dry-run | disable    automations (AUTOMATION.md; alias: rules)
├── policy   list | create | revoke               standing approvals (AUTOMATION.md)
├── tokens   list | create | rotate | revoke <id>  (SECURITY.md §3.3)
├── tls      show                                 box CA fingerprint (SECURITY.md)
├── deploy   <dir|git-url> | history | rollback | watch   your own services (DEPLOYMENTS.md)
├── secret   set | list                           write-only app secrets (DEPLOYMENTS.md)
├── migrate  check | import | pin                 (DEPLOYMENTS.md, DOGFOOD.md)
├── doctor   [--wave N]                           dogfood gate checker (DOGFOOD.md)
├── app      scaffold | validate | gate | dev               developer: Market apps
├── plugin   init | dev | pack | publish                    developer: plugins (29 §7)
├── mcp                                    stdio MCP server that bridges to the box's /mcp
├── completion bash | zsh | fish | powershell
└── version
```

`apps` (plural) acts on a box. `app` (singular) works on a source folder on your machine. The help text says so on both, and each suggests the other on a likely typo (`onemind app install` → "did you mean `onemind apps install`?").

### 3.1 Global flags and environment

| Flag | Env | Default | Meaning |
|---|---|---|---|
| `--context NAME` | `ONEMIND_CONTEXT` | `current-context` in the config | Which box to talk to |
| `--hub URL` | `ONEMIND_HUB` | from the context | Override the gateway URL (kept for today's scripts) |
| `--token-stdin` | `ONEMIND_TOKEN` | from the credential store | One-off credential; `--token` still works but prints a warning (flags land in shell history) |
| `--json` | – | off | Machine output (section 4) |
| `-q, --quiet` | – | off | Only errors and the essential value (an id) |
| `--no-color` | `NO_COLOR` | color on a TTY | |
| `--timeout DUR` | `ONEMIND_TIMEOUT` | `30s` | Per request; `watch`, `tail -f` and `--wait` have their own |
| `-v, --verbose` | `ONEMIND_DEBUG=1` | off | Log HTTP method, path, status and timing to stderr, with `Authorization` always redacted |
| `--config FILE` | `ONEMIND_CONFIG` | section 5 | Alternate config file |

Precedence: flag, then environment, then context, then built-in default.

---

## 4. Output, `--json` and exit codes

### 4.1 Rules

1. **Human output** goes to stdout as tables or key/value blocks. Progress, warnings and prompts go to stderr, so `onemind apps list | grep ntfy` stays clean.
2. **`--json` works on every command.** Stdout then holds exactly one JSON document (or, for `watch` and `tail`, one JSON object per line: NDJSON). Nothing else is written to stdout.
3. **Gateway objects pass through unchanged.** `onemind nodes --json` prints the gateway's `GET /v1/nodes` list as is (today's behaviour, kept). The contract versions those shapes.
4. **CLI-built objects carry a schema id**, for example `"schema": "onemind.cli.status/v1"`, so scripts can detect a change.
5. **Errors with `--json`:** stdout is empty; stderr gets one line `{"error": "<code>", "message": "…", "exit_code": N}`, where `<code>` is the contract §3 error code when the gateway sent one.
6. Prompts never appear when stdin is not a TTY. A command that would need to ask fails with exit code 2 and says which flag answers the question, except approval, which cannot be answered by a flag once step-up exists (section 8.2).

### 4.2 Exit codes

| Code | Name | When | Gateway source |
|---|---|---|---|
| 0 | ok | Success; for `--wait`, the action reached `succeeded` | 2xx |
| 1 | error | Anything not listed below | 5xx, unexpected |
| 2 | usage | Bad flags or arguments, or a prompt needed with no TTY | – |
| 3 | unauthenticated | No credential, or it was refused | 401 `unauthenticated` |
| 4 | permission_denied | Principal not allowed (for example an agent token tried to approve) | 403 `permission_denied` |
| 5 | not_found | Unknown node, app, action, snapshot or context | 404 `not_found` |
| 6 | conflict | `conflict`, `stale_precondition` (for example a stale scan), `expired` | 409 |
| 7 | unreachable | DNS, connect or TLS failure, timeout | – |
| 8 | verify_failed | `audit verify`, `backup verify`, a signature or digest check, a TLS fingerprint mismatch | – |
| 9 | pending | `--wait` timed out while the action was still `awaiting_approval` | – |
| 10 | refused | The action ended `cancelled` (denied) or `expired` | – |
| 11 | action_failed | The action ended `failed` | – |
| 12 | outcome_unknown | The action ended `outcome_unknown` | – |
| 13 | too_many_requests | Pending-request limit reached (plan E3, 11th pending → 429) | 429 |
| 14 | unsupported | The box is too old for this command (section 9) | 404/405 on a probed path, or a missing feature flag |

The Go SDK maps HTTP errors to typed errors (`*onemind.APIError` with `.Code`); the CLI maps those to this table in one place (`cmd/onemind/cli/exit.go`). The table is part of the CLI's public interface: a number is never reused for another meaning.

---

## 5. Config file and contexts

**Location:** `$ONEMIND_CONFIG`, else `$XDG_CONFIG_HOME/onemind/config.yaml`, else `~/.config/onemind/config.yaml` (on macOS too, to match other developer CLIs). Mode `0600`, created on first `login`. It holds **no secrets**.

```yaml
# ~/.config/onemind/config.yaml
schema: onemind.cli.config/v1
current-context: home
contexts:
  home:
    hub: https://hub.local:8443
    principal: owner             # who the credential belongs to, as the gateway reported at login
    ca-fingerprint: sha256:4f1c…e9   # pinned at login (section 8.1)
    credential: keychain         # keychain | file
  devbox:
    hub: http://devbox.local:8080
    principal: dev
    insecure-http: true          # v0 shortcut, only allowed for this context, warned on every call
    credential: file
defaults:
  output: table
  wait: 10m                      # default for --wait
```

**Credentials:** in the OS keychain (macOS Keychain, Linux Secret Service) under service `onemind`, account `<context>`. When no keychain is available (a headless Linux box, CI), they go in `credentials.yaml` next to the config, mode `0600`, and `login` says so. `logout` deletes the credential and, once the gateway supports it, revokes the session server-side.

**Contexts:**

```console
$ onemind context list
CURRENT  NAME    HUB                         PRINCIPAL  BOX VERSION
*        home    https://hub.local:8443      owner      0.3.0
         devbox  http://devbox.local:8080    dev        0.2.1 (insecure http)

$ onemind context use devbox
Switched to context "devbox".

$ onemind --context home apps list      # one command against another box
```

---

## 6. Commands in detail

Each row gives the gateway call underneath, so the dashboard's "show the equivalent call" (UX-B2) can print the CLI line and the CLI's `--verbose` prints the REST line. "New" means the endpoint is not in the contract yet (section 7).

### 6.1 Sign-in and context

| Command | Does | Gateway |
|---|---|---|
| `onemind login [--hub URL] [--name CTX] [--token-stdin]` | v0: asks for a token without echo (or reads stdin), calls `/v1/instance` and a whoami, pins the CA, saves the context. v1 (after E3/E8): device sign-in: prints a short code and a URL/QR; you approve with your passkey on the phone or in the browser | `GET /v1/instance`; `GET /v1/me` (new); v1 device flow (new, OAuth 2.0 device authorization grant, RFC 8628) |
| `onemind logout [--all]` | Forget the credential (and revoke the session in v1) | `POST /v1/auth/logout` (new, v1) |
| `onemind context list\|use\|show\|rename\|delete` | Local config only | – |

```console
$ onemind login --hub https://hub.local:8443
Box:          home-hub (OneMind 0.3.0)
Certificate:  sha256:4f1c…e9  (first time seen; compare with Settings → Security on the box screen)
Trust this certificate? [y/N] y
Token: ********
Signed in as owner (person, owner). Context "home" saved and selected.
```

### 6.2 Status and nodes

```console
$ onemind status
Box        home-hub · OneMind 0.3.0 · hub node 3f9c2a1b7d4e
Nodes      3 online · 0 stale · 1 offline
Approvals  2 waiting  → onemind actions list --pending
Updates    up to date (0.3.0, slot B, committed)
Backups    last verified 6 h ago ✓
Audit      seq 1532, chain ok at last check
```

`status --json` returns `{"schema": "onemind.cli.status/v1", "instance": {…}, "nodes": {"online": 3, …}, "actions": {"awaiting_approval": 2}, "update": {…}|null, "backup": {…}|null, "audit": {"seq": 1532, "head": "…"}|null}`. Sections the box does not support yet are `null`, and the human view shows "not available on this box".

| Command | Gateway | Notes |
|---|---|---|
| `onemind nodes [list] [--status online\|stale\|offline]` | `GET /v1/nodes` | Today's table and `--json`, kept byte-compatible |
| `onemind nodes info <node_id>` | `GET /v1/nodes/{id}` | |
| `onemind node info --local [--root DIR] [--arch A]` | none (local `internal/detect`) | Today's `node info`; `--agent URL` kept for `onemindd :7480` |

### 6.3 Apps on a box

| Command | Gateway |
|---|---|
| `onemind apps list [--installed] [--category C]` | `GET /v1/apps` |
| `onemind apps info <id>` | `GET /v1/apps` (filtered) → later `GET /v1/apps/{id}` (new) |
| `onemind apps install <id> [--reason TEXT] [--wait[=DUR]] [--no-approve]` | `POST /v1/actions` `{type: app.install}`, then the approval flow |
| `onemind apps remove <id> [--reason TEXT] [--wait] [--no-approve]` | `POST /v1/actions` `{type: app.remove}` |

**The owner flow is still request then approve.** When an owner runs `apps install`, the CLI creates the action, prints what the gateway says will happen, and asks the owner to approve it in the same session. That is two audit entries (requested by `owner`, approved by `owner`). With `--no-approve` it stops after the request, which is how a script or a non-owner principal behaves.

```console
$ onemind apps install ntfy
Requested action 01JC8Q…  app.install ntfy 2.14.0
What the box will do (worked out by the gateway):
  namespace     app-ntfy (new)
  images        binwiederhier/ntfy@sha256:9b1e…  (scan pass, 2 days old, licence Apache-2.0/GPL-2.0, L1)
  web           port 80 → https://ntfy.hub.local
  grants        none
Approve now? [y/N] y
approved · dispatched · succeeded in 14 s
```

```console
$ onemind apps install ntfy --json --no-approve
{"id":"01JC8Q…","type":"app.install","params":{"app_id":"ntfy"},"state":"awaiting_approval",
 "requested_by":"owner","expires_at":"2026-11-13T10:00:00Z", …}
```

The "what the box will do" block comes from the action's effects as worked out by the gateway (plan §4 E3: effects computed by the gateway, not by the agent). Until that field exists the CLI prints the catalog entry and scan record instead and says it is doing so.

### 6.4 Actions (the approval queue)

| Command | Gateway |
|---|---|
| `onemind actions list [--pending] [--state S] [--by PRINCIPAL] [--limit N]` | `GET /v1/actions` (filters client-side until the gateway adds query params) |
| `onemind actions info <id>` | `GET /v1/actions/{id}` |
| `onemind actions watch [--pending]` | `GET /v1/events?types=action.*` (new, Server-Sent Events); falls back to polling `GET /v1/actions` every 2 s |
| `onemind actions approve <id>` | `POST /v1/actions/{id}/approve` (owner only; step-up in v1) |
| `onemind actions deny <id> [--reason TEXT]` | `POST /v1/actions/{id}/deny` |

An agent's reason is untrusted text. The CLI prints it inside a labelled, quoted block and strips terminal control characters (ESC, OSC, BEL) from every gateway string before printing, so an agent cannot hide text or rewrite the screen.

```console
$ onemind actions list --pending
ID          TYPE         TARGET         REQUESTED BY        AGE   EXPIRES
01JC9A…     app.install  uptime-kuma    agent:hermes-agent  3m    in 23h
01JC9B…     app.remove   home-assistant agent:hermes-agent  1m    in 23h

$ onemind actions approve 01JC9B…
app.remove home-assistant, requested by agent:hermes-agent
Agent's reason (untrusted, written by the agent):
  │ "Freeing memory for the new monitoring app."
What the box will do: delete namespace app-home-assistant (data volume kept: retain class)
Approve? Type the app id to confirm: home-assistant
approved · dispatched · succeeded in 6 s

$ onemind actions watch --json
{"event":"action.requested","action":{"id":"01JC9C…","state":"awaiting_approval",…}}
{"event":"action.succeeded","action":{"id":"01JC9A…","state":"succeeded",…}}
```

Removing an app or anything marked destructive asks you to type the target id rather than `y`.

### 6.5 Audit

| Command | Source | Does |
|---|---|---|
| `onemind audit verify` | `GET /v1/audit?after_seq=N` (new, owner only, paged NDJSON) | Download the log, recompute every hash, compare the head with the latest signed checkpoint (plan E2) |
| `onemind audit verify --file PATH` | a local JSONL copy (on the box, or a backup) | Same check, offline; needs no credential |
| `onemind audit tail [-f] [-n 50] [--action ID] [--principal P]` | `GET /v1/audit` then `GET /v1/events?types=audit` (new) | Print entries; `-f` follows |

The Go implementation uses the exact rule in `core/onemind_core/audit.py`: `hash = sha256(prev_hash + canonical_json(line without prev_hash and hash))`, keys sorted, no whitespace, UTF-8, genesis `0`×64. A shared test-vector file (`sdk/testdata/audit/`, owned by the Go SDK epic) is checked by both the Python tests and the Go tests, so the two can never disagree.

```console
$ onemind audit verify
1532 entries · chain ok · head seq 1532 sha256:7d02…a1
Checkpoint: seq 1530 signed 2026-11-12T09:00Z by box key sha256:c3…; matches the chain ✓

$ onemind audit verify --file audit-copy.jsonl
FAIL at seq 812: hash mismatch (line changed after it was written)
exit 8
```

A local file can only prove the chain is self-consistent. A full rewrite of the log is caught only by the checkpoint held outside the box (plan E2). The output says which of the two checks ran.

### 6.6 Backup and restore

| Command | Gateway (all new; owned by the backups spec, plan E9) |
|---|---|
| `onemind backup status` | `GET /v1/backups/status`: schedule, destinations, last run, last verified restore (the badge) |
| `onemind backup list [--app ID]` | `GET /v1/backups/snapshots` |
| `onemind backup now [--app ID] [--wait]` | `POST /v1/actions {type: backup.run}`; low risk, so the owner policy may auto-approve it |
| `onemind backup verify <snap>` | `POST /v1/actions {type: backup.verify}`: a test restore into a scratch place |
| `onemind restore <snap> [--app ID] [--wait]` | `POST /v1/actions {type: backup.restore}`: destructive, always needs an owner approval with typed confirmation |

```console
$ onemind restore 2026-11-12T03:00Z --app uptime-kuma
Restore uptime-kuma to the snapshot from 2026-11-12 03:00 (9 h ago).
This replaces the app's current data. A safety snapshot is taken first.
Type the app id to confirm: uptime-kuma
approved · dispatched · succeeded in 41 s (safety snapshot 2026-11-12T12:04Z kept)
```

### 6.7 Updates

Two paths, one command set:

| Where you run it | Path | Who may apply |
|---|---|---|
| On the box, as root, k3s or gateway down allowed | `onemindd` local socket `/run/onemind/onemindd.sock` (B4.2 "API on a local Unix socket") | root on the box (the rescue path), audited by `onemindd` as `local:root` |
| Anywhere else | Gateway `GET /v1/os/status`, `POST /v1/os/check`, `POST /v1/actions {type: os.update}` (new, B4.2) | owner, through approval |

| Command | Does |
|---|---|
| `onemind update status [--node ID]` | Current and available version, booted slot, state, policy and window, history (today's output in the `updater` worktree) |
| `onemind update check` | Fetch and verify the TUF channel; print the decision; never installs |
| `onemind update apply [--no-reboot] [--node ID]` | Install now (refused while the health gate is deciding). Remote: an `os.update` action the owner approves |

The `updater` worktree's `update.go` runs the engine inside the CLI process. DEV-CLI-6 changes it to call `onemindd` over the socket, so only one process ever drives RAUC and the state files. The output format stays the same.

```console
$ onemind update status
channel      security (https://updates.onemind.example/security)
policy       auto-security, window 02:00-05:00
current      0.3.0 (slot B, committed)
available    0.3.1
state        idle
last check   2026-11-12T08:00:00Z
last result  committed 0.2.9->0.3.0
```

### 6.8 Fabric (more machines)

| Command | Runs on | Does | Gateway / agent |
|---|---|---|---|
| `onemind fabric qr [--ttl 30m] [--role node]` | your Mac or the box (owner) | Create a join code (1 hour or less, FAB-P1) and print it as a terminal QR code and as text | `POST /v1/fabric/join-tickets` (new; owner only, audited; [API.md](API.md) §5.1) |
| `onemind fabric join <code> [--hub URL]` (alias `onemind node join <code>`) | the new machine, as root | File a join request with the code, show the match code, wait for the owner's approval, then write the `onemindd` config, start the agent and wait for its first heartbeat | `POST /v1/fabric/join-requests`, then poll `GET /v1/fabric/join-requests/{id}` (new; the code is the credential; the owner approves the `node.join` action) |
| `onemind fabric leave` | the leaving machine, as root | Drain, stop `onemindd`, forget the hub | `POST /v1/fabric/leave` (new) |
| `onemind fabric remove <node_id>` | owner | Remove a node that is gone: an action with typed confirmation | `POST /v1/actions {type: node.remove}` |

```console
$ onemind fabric qr
Scan with the OneMind app, or run on the new machine:
  sudo onemind fabric join OM1-7KQ4-XR2M-93TD
▄▄▄▄▄▄▄ ▄ ▄▄ ▄▄▄▄▄▄▄
█ ▄▄▄ █ ▀█▄█ █ ▄▄▄ █      (QR code)
…
Expires in 30 minutes · one use · role node
```

The join code holds no hub address that identifies a network beyond the box's local name, and the QR shows nothing identifying (plan E12).

### 6.9 Notifications, rules, tokens

The command tree in §3 is the one list of `onemind` commands for every leap spec. Groups whose behaviour another spec defines (`alerts`, `auto`, `policy`, `tls`, `deploy`, `secret`, `migrate`, `doctor`) follow that spec; `rules` is an alias of `auto`.

| Command | Gateway (new; owned by the notifications, automation and identity specs) |
|---|---|
| `onemind notify test [--channel ntfy\|push\|email]` | `POST /v1/notify/test`: sends "Test from OneMind" to the owner's channels; prints each delivery result |
| `onemind rules list` | `GET /v1/rules` |
| `onemind rules add -f rule.yaml` | `POST /v1/actions {type: automation.rule.create, params: {rule: …}}`: a new rule is a state change, so the owner approves it |
| `onemind tokens list` | `GET /v1/tokens` (ids, kind, role, created, last used; never the token) |
| `onemind tokens create --kind agent --name NAME [--expires 30d]` | `POST /v1/tokens` (owner only; printed once) |
| `onemind tokens create --kind person --role guest --name NAME` | same; a read-only person token for a script |
| `onemind tokens revoke <id>` | `DELETE /v1/tokens/{id}` |

A rule may only **request** actions. It can carry `approve: auto` only for effect classes the owner's risk policy already allows to auto-approve (reads and notifications; plan §5 decision 6). The gateway refuses `approve: auto` on `write` it was not told to remember, and always on `actuate` and `destructive`.

```yaml
# rule.yaml
schema: onemind.rule/v1
name: notify-on-node-offline
when: {event: node.status, status: offline, for: 5m}
then:
  - notify: {title: "Node {{node.hostname}} is offline", priority: high}
```

```console
$ onemind tokens create --kind agent --name laptop-claude --expires 30d
Token for agent:laptop-claude (kind agent, can request, cannot approve). Shown once:
omt_agent_…  (copy it now)
```

### 6.10 Developer: Market apps (`onemind app …`)

| Command | Does | Built from |
|---|---|---|
| `onemind app scaffold <upstream>` | Create `apps/<id>/` (manifest, manifests/, README) from a container image, a Compose file or a GitHub repo | `sdk/tools/app-scaffold` (pipeline) |
| `onemind app validate [dir]` | Schema + manifest rules; under 10 s (29 §7 target) | `sdk/schema/onemind.app.schema.json` + rules |
| `onemind app gate [dir] [--write-scan]` | Run the §9.4 gate locally (Trivy, ClamAV, secrets, cosign, licence class, smoke) in the pinned `app-gate` container; prints the would-be `scan.json` | `sdk/tools/app-gate` (pipeline) |
| `onemind app dev [dir] [--context devbox]` | Install the folder on a box in developer mode, through an action you approve, and stream its logs; re-install on change with `--watch` | `POST /v1/dev/apps` (new) |

**One validator.** 29 §7 and PLG-P2 require the CLI to refuse exactly what the box refuses. Phase 1: the Go command runs the JSON Schema plus a Go port of the rules and is tested against the same fixture folder (`sdk/tools/tests/fixtures/` plus new `sdk/testdata/manifests/{valid,invalid}/`) as the Python `validate-apps`; CI fails if the two disagree on any fixture. Phase 2 (after manifest v1, plan E6) decides whether the gateway calls the Go validator too.

**Developer mode on a box** is an owner setting (an action, audited, shown as a banner on the dashboard). It accepts `app dev` installs with tier `dev`. They still go through approval and the install sandbox (plan E0S). The scan rule (§10.3) still holds with the `kubernetes` executor: `app dev` uploads the scan record from `app gate`, and the gateway marks it "scanned on a developer machine", which is enough for a dev install and never for the Market.

```console
$ onemind app validate apps/mealie
apps/mealie/onemind.app.yaml ✓ schema · ✓ id · ✓ images pinned by digest · ✗ licence missing
1 problem. exit 1

$ onemind app gate apps/mealie
images   ghcr.io/mealie-recipes/mealie@sha256:…  amd64 arm64
trivy    0 critical fixable · 0 critical · 3 high
clamav   0 infected (daily-27812)
secrets  0
cosign   unsigned
licence  AGPL-3.0 → L2
smoke    pass
result   pass   (written to apps/mealie/scan.json with --write-scan)
```

### 6.11 Developer: plugins (`onemind plugin …`)

Follows 29 §7, cut to the four commands the founder focus needs first. `test`, `install`, `rollback`, `disable` and `remove` follow in a later epic. Third-party **host** plugins (E3, E4) stay disabled in v0 (BD-15), so `init` offers only kinds that run in k3s or the dashboard.

| Command | Does |
|---|---|
| `onemind plugin init --kind app\|widget\|mcp-tool\|automation [name]` | Scaffold manifest, chart or manifests, a UI stub for `widget` (per the design spec `PLUGIN-UI.md`), tests, and a CI workflow with trusted publishing |
| `onemind plugin dev [--context devbox] [--watch]` | Like `app dev`; for a widget it also serves the bundle so the dashboard hot-reloads it |
| `onemind plugin pack [--offline]` | Build the OCI artifact: chart, images by digest, SBOM, provenance; `--offline` writes a `.ompkg` |
| `onemind plugin publish` | Only from CI with an OIDC identity (trusted publishing); signs keyless with cosign and opens a review. On a laptop it refuses with exit 4 and explains why |

```console
$ onemind plugin init --kind widget weather-card
Created weather-card/ (onemind.app.yaml, ui/, manifests/, tests/, .github/workflows/publish.yml)
Next: cd weather-card && onemind plugin dev --context devbox
```

DX targets from 29 §7, measured in DEV-CLI-11: `init` to a working widget on a dev box in under 15 minutes; `validate` in under 10 seconds.

### 6.12 `onemind mcp` (stdio server)

Many agent clients start MCP servers as a local process over stdio. The gateway serves MCP over Streamable HTTP at `/mcp` (§11.3). `onemind mcp` is the bridge: it reads JSON-RPC from stdin, forwards each message to the box's `/mcp` with an **agent** token, and writes the reply to stdout.

- It adds no tools of its own. The agent sees exactly the gateway's tools: today `list_nodes`, `list_apps`, `request_action`. There is no approve or deny tool.
- It refuses to start with a person credential (exit 4): an owner token must never sit behind an agent. The gateway refuses it as well (403), so this check is a convenience, not the protection.
- The token comes from `ONEMIND_AGENT_TOKEN` or `--token-file`, never from the context's owner credential.
- Stdout carries only MCP messages; logs go to stderr.

```json
{
  "mcpServers": {
    "onemind": {
      "command": "onemind",
      "args": ["mcp", "--context", "home"],
      "env": { "ONEMIND_AGENT_TOKEN": "<agent token from `onemind tokens create --kind agent`>" }
    }
  }
}
```

### 6.13 Completion and version

`onemind completion bash|zsh|fish|powershell` prints a script generated from the command tree. Dynamic completion (context names, app ids, pending action ids) calls `onemind __complete …`, which reads the local config and makes at most one short read-only request to the current box.

`onemind version [--json]` prints the CLI version and commit, plus the box version when a context is set: `{"cli": "0.4.0", "commit": "…", "box": {"name": "home-hub", "version": "0.3.0"}}`.

---

## 7. Gateway and agent interfaces the CLI needs

The CLI adds none of these itself. Each is owned by the spec named, goes into the contract through its serialized PR, and gets a Go SDK method.

| Endpoint | For | Status | Owner |
|---|---|---|---|
| `GET /v1/instance` + `features: [...]`, `api: "v1"` | version and feature checks (section 9) | exists, fields new | API spec |
| `GET /v1/me` | login, `mcp` guard | new | API spec |
| `GET /v1/events` (SSE; `types=` filter) | `actions watch`, `audit tail -f` | new | API spec |
| `GET /v1/actions` query params `state`, `requested_by`, `limit`, `cursor` | `actions list` | new | API spec |
| Action `effects` field | approve screens | new | plan E3 |
| `GET /v1/audit`, checkpoint endpoint | `audit` | new | plan E2 |
| `/v1/os/*`, action type `os.update`; `onemindd` socket API | `update` | new | updater (B4.2) |
| `/v1/backups/*`, action types `backup.*` | `backup`, `restore` | new | backups spec (plan E9) |
| `/v1/fabric/*`, action `node.remove` | `fabric` | new | fabric spec (plan E12) |
| `/v1/notify/test`, `/v1/rules`, action `rule.create` | `notify`, `rules` | new | notifications, automation specs |
| `/v1/tokens` | `tokens` | new | identity (plan E8) |
| `/v1/dev/apps`, developer-mode setting | `app dev`, `plugin dev` | new | app pipeline (plan E5) |
| v1 device sign-in and step-up approval | `login`, `approve` | new | identity (plan E3, E8) |

Until an endpoint exists, the command is present, prints "not available on this box yet (needs feature `backups.v1`)" and exits 14. Commands are never hidden, so the help and the docs stay the same for every box.

---

## 8. Security model

### 8.1 Credentials and transport

| Risk | Rule |
|---|---|
| Token in shell history or `ps` | Read from the keychain, a `0600` file, stdin or the environment; `--token` still works for old scripts and prints a warning |
| Token in logs | `--verbose` redacts `Authorization` and any field named `token`; the CLI never prints a stored credential |
| Man in the middle on the LAN | `https` required for any hub that is not loopback. At `login` the CLI shows the box certificate's sha256 fingerprint (trust on first use, like SSH) and pins it; a later mismatch fails with exit 8 and the old and new fingerprints. `insecure-http: true` is a per-context v0 shortcut, warned on every call |
| A stolen laptop | Credentials live in the OS keychain; `onemind logout --all` and `tokens revoke` work from any other signed-in device |
| Terminal injection from gateway data (agent reasons, app names) | Strip control characters from every string before printing to a TTY; `--json` output is JSON-escaped |
| Supply chain of the CLI itself | Release binaries built in CI, signed keyless with cosign, with an SBOM and `SHA256SUMS`; the image ships the same binary at the same version; dependencies pinned in `go.mod` with a licence-matrix row each (brief 30 §licences) |

### 8.2 The approval rule in a terminal

The CLI cannot prove that a human is typing. A coding agent running in the founder's own terminal could run `onemind actions approve` with the owner's credential. So the protection sits in the gateway, and the CLI is honest about v0:

| Phase | What stops an agent from approving |
|---|---|
| v0 (static tokens) | Agents get **agent tokens** (`tokens create --kind agent`, §11.2 principals); the gateway answers 403 to any approve with them. `onemind mcp` refuses person credentials. `approve` requires a TTY and typed confirmation for destructive actions. **Remaining gap:** an agent that can read the owner's keychain entry or run commands in the owner's shell could approve. This is written in the threat model (secdoc `docs/security/THREAT-MODEL.md`) and in `onemind login`'s first-run notice |
| v1 (passkey step-up, plan E3/E8) | `POST …/approve` needs a fresh step-up assertion. The CLI cannot create one; it prints a link and QR code and waits while the owner approves with a passkey on the phone or in the browser. There is no flag to skip this. Owner login sessions from the CLI have no standing approve right |

`--no-approve`, `--wait` and `--json` never weaken this: a script can request and wait, and a person approves.

### 8.3 Headless use on the box

- The OneMind image ships `onemind` on the read-only root, updated with the OS.
- Root on the box gets a built-in context `local` without a login. It talks to `onemindd` over `/run/onemind/onemindd.sock`, which checks the caller's uid with `SO_PEERCRED`. That path covers `node info`, `update`, `fabric join/leave`, `audit verify --file` and a read-only `status`. It works with k3s and the gateway down (rescue, plan E13).
- Owner operations that go through the gateway (apps, actions, backups) still need an owner credential on the box, as on a laptop. Root on the box is not silently an owner of the gateway, so a compromised app container that escapes to a root shell still leaves an audit trail under `local:root` and cannot pose as the owner in the ledger.
- On stock Debian (installer mode, `deploy/install.sh`) the same binary is installed from the release with its checksum checked; `update` then reports "installer mode: OS updates come from Debian unattended-upgrades" (§10.1).

---

## 9. Versioning and compatibility

| Topic | Rule |
|---|---|
| CLI version | Same version line as the OS release; the CLI in an image matches its gateway exactly |
| Box compatibility | A CLI supports boxes from the same minor and the previous one. It reads `GET /v1/instance` (`version`, `api`, `features`) once per run (cached for 60 s per context) and turns a missing feature into exit 14 with the version needed |
| Older boxes without `features` | Treated as the v0 feature set: `nodes`, `apps`, `actions` |
| Command names and flags | Stable from 1.0. Before 1.0 a rename keeps the old name as a hidden alias for one minor and prints a deprecation line to stderr |
| Today's commands | `onemind nodes --hub URL [--token T] [--json]`, `onemind node info …` and `onemind version` keep working unchanged, tested by today's `main_test.go` |
| `--json` | Gateway objects follow the contract's versioning; CLI objects carry `schema: onemind.cli.<name>/v<N>`; fields are only added within a version |
| Exit codes | Never reused (section 4.2) |
| Config file | `schema: onemind.cli.config/v1`; a newer CLI migrates an older file in place after writing a `.bak` |
| Go SDK | The CLI pins the SDK by version in `go.mod` (same repo, separate Go module `sdk/go`, so third parties can import the SDK without the hub's server dependencies) |

---

## 10. Same call, every surface

Every CLI command is one SDK call. The Go SDK is the base; the Python and TypeScript SDKs mirror its names. Final names are owned by the SDK specs; these are the proposed shapes.

`onemind apps install ntfy --no-approve --json`:

```go
c, _ := onemind.NewFromContext("")            // reads the same config and keychain as the CLI
a, err := c.Actions.Request(ctx, onemind.ActionRequest{
    Type: "app.install", Params: map[string]any{"app_id": "ntfy"},
})
var apiErr *onemind.APIError
if errors.As(err, &apiErr) && apiErr.Code == "stale_precondition" { /* exit 6 */ }
fmt.Println(a.ID, a.State)                    // 01JC8Q… awaiting_approval
```

```python
from onemind import Client
c = Client.from_context()
a = c.actions.request(type="app.install", params={"app_id": "ntfy"})
print(a.id, a.state)
```

```ts
import { Client } from "@onemind/sdk";
const c = await Client.fromContext();
const a = await c.actions.request({ type: "app.install", params: { app_id: "ntfy" } });
console.log(a.id, a.state);
```

```console
$ curl -sS -X POST https://hub.local:8443/v1/actions \
    -H "Authorization: Bearer $ONEMIND_TOKEN" -H "Content-Type: application/json" \
    -d '{"type":"app.install","params":{"app_id":"ntfy"},"idempotency_key":"cli-01JC8Q…","expires_at":"2026-11-13T10:00:00Z"}'
```

The CLI sets `idempotency_key` to `cli-<ulid>` and keeps it across its own retries, so a lost reply never creates a second action. `expires_at` defaults to 24 h (same as `/mcp`), set with `--expires`.

---

## 11. Code layout and ownership

| Path | What | Owner (epic) | Hotspot? |
|---|---|---|---|
| `cmd/onemind/main.go` | `main()` → `cli.Execute()` only | DEV-CLI-1 | **Yes**: serialized |
| `cmd/onemind/cli/root.go` | Root command, global flags, the list of command groups (one line each) | DEV-CLI-1 | **Yes**: serialized; each later epic adds one line |
| `cmd/onemind/cli/{output,exit,config,credentials,tty,features}.go` | Shared layers | DEV-CLI-1, -2 | no |
| `cmd/onemind/cli/<group>.go` + `<group>_test.go` | One file per group: `login`, `context`, `status`, `nodes`, `apps`, `actions`, `audit`, `backup`, `update`, `fabric`, `notify`, `rules`, `tokens`, `appdev`, `plugin`, `mcp`, `completion`, plus `alerts`, `auto`, `policy`, `tls`, `deploy`, `secret`, `migrate`, `doctor`, written by the core branch that owns the feature | the matching epic | no |
| `cmd/onemind/update.go` | today's update command (updater worktree) | moves to `cli/update.go` in DEV-CLI-6 after `updater` merges | coordinate |
| `sdk/go/` (own `go.mod`) | Go SDK: client, config/context loader, typed errors, events, audit verify | Go SDK spec | no |
| `sdk/testdata/{audit,manifests}/` | Cross-language test vectors | Go SDK spec, DEV-CLI-5, -10 | no |
| `cmd/onemind/README.md`, `docs/cli/` (generated reference) | Docs | DEV-CLI-13 | no |
| `os/versions.lock.yaml` | CLI release pin for the image | DEV-CLI-13 | **Yes**: serialized |
| `sdk/contracts/poc-v0.md` | Endpoint additions in section 7 | the owning specs, never this one | **Yes**: serialized |

Command library: **cobra** (Apache-2.0), because it gives subcommands, help, aliases, `__complete` and all four completion shells in one tested package. It needs a licence-matrix row and an exact pin before DEV-CLI-1 lands. The fallback, if the founder rejects a new dependency, is a small in-house tree over `flag` with bash and zsh completion only (adds about one S of effort to DEV-CLI-1 and -13).

---

## 12. Build plan (epics)

| Epic | Title | Size | Depends on | Acceptance |
|---|---|---|---|---|
| DEV-CLI-1 | Skeleton: command tree, global flags, `--json`, exit codes, config file, existing commands ported | M | Go SDK core client (or a stub in `sdk/go` landed in the same PR) | Today's `main_test.go` passes unchanged; every command in section 3 exists and `--help` works; `--json` on an error writes nothing to stdout and one JSON line to stderr; exit code table test covers 0–14 |
| DEV-CLI-2 | `login`, `logout`, `context`, keychain + file store, TLS pin | M | 1; `GET /v1/me` | Login against a test gateway saves a context with no secret in `config.yaml`; changed certificate → exit 8; `insecure-http` warns on every call; file store is created `0600` |
| DEV-CLI-3 | Read commands: `status`, `nodes`, `apps list/info`, `actions list/info`, `version` | S | 2 | Golden-file tests for table and JSON output against the fake gateway; `status` shows `null` sections on a v0 box |
| DEV-CLI-4 | Action flow: `apps install/remove`, `actions approve/deny/watch`, `--wait`, effects display | M | 3; `/v1/events` optional (polling fallback) | Owner install = 2 audit lines; agent token approve → exit 4; no TTY + approve → exit 2; `--wait` maps every end state to exit 0/9/10/11/12; ESC sequences in a reason are stripped |
| DEV-CLI-5 | `audit verify` (file and gateway) and `audit tail` | M | 1; plan E2 audit endpoint and checkpoint | Shared vectors pass in Go and Python; one changed byte fails at that seq with exit 8; rewritten chain caught by the checkpoint |
| DEV-CLI-6 | `update` on the box (socket) and remote (gateway action) | M | `updater` merged; B4.2 socket and `/v1/os` | Same output as today's updater tests; CLI no longer drives RAUC in-process; remote apply creates an `os.update` action |
| DEV-CLI-7 | `backup` and `restore` | M | plan E9 endpoints | `restore` needs typed confirmation and an owner approval; a safety snapshot id is printed; restore to a fresh VM passes in CI |
| DEV-CLI-8 | `fabric qr/join/leave/remove`, `node join` alias | M | plan E12, `deploy-v0` merged | Join a VM in under 2 minutes from `fabric qr`; expired or reused code refused; QR contains no network details |
| DEV-CLI-9 | `notify test`, `rules list/add`, `tokens` | M | notifications, automation, identity endpoints | `notify test` reports per-channel delivery; `rules add` with `approve: auto` on a destructive effect is refused; a new token is printed once and never listed |
| DEV-CLI-10 | `app scaffold/validate/gate/dev` | L | `pipeline` merged; plan E5, E6 | Go and Python validators agree on every fixture; `validate` under 10 s; `gate` writes a `scan.json` that the gateway accepts for a dev install only |
| DEV-CLI-11 | `plugin init/dev/pack/publish` (built by the plugin stream as DEV-PLG-7, -8 and -14 in [PLUGIN-SDK.md](PLUGIN-SDK.md); this row keeps the CLI acceptance) | L | 10; design `PLUGIN-UI.md`; trust root (29 E9) signing | `init` to a working widget on a dev box under 15 min (timed, recorded); `publish` outside CI → exit 4; `pack` output verifies with cosign |
| DEV-CLI-12 | `onemind mcp` stdio bridge (built as DEV-MCP-7 in [MCP.md](MCP.md); this row keeps the CLI acceptance) | S | `gwmcp` merged | Official MCP SDK client over stdio lists the same tools `/mcp` gives that principal (3 on the gwmcp baseline); `request_action` creates a pending action; person credential → exit 4 |
| DEV-CLI-13 | Completion, generated reference docs and man pages, signed releases, image pin | M | 1 | Completion scripts load in bash, zsh, fish, PowerShell; `docs/cli/` regenerates with no diff in CI; release has cosign signature, SBOM and checksums |
| DEV-CLI-14 | Headless on the box: `local` context over the `onemindd` socket with peer-uid check | M | 6; `onemindd` socket API | As root with k3s stopped, `status`, `update status` and `audit verify --file` work; a non-root user gets exit 4; local calls are audited as `local:<uid>` |

**Order:** 1 → 2 → 3 → 4 and 12 (L1 launch needs approvals and the MCP bridge) → 5 → 6 and 14 → 10 → 7, 8, 9 as their backends land → 11 → 13 runs alongside from 1.

---

## 13. Test plan

| Layer | How | Pass when |
|---|---|---|
| Unit | Table tests per command against an `httptest` fake gateway (today's pattern in `main_test.go`) | Every command: human output, `--json`, each error code → exit code |
| Golden output | `testdata/golden/<cmd>.{txt,json}`, updated only with `-update` | No unreviewed change to output a script may parse |
| Contract | Run the CLI against the real Python gateway (`ONEMIND_EXECUTOR=noop`) in CI | Install, approve, deny, expire, stale scan and agent-403 flows give the documented exit codes |
| Cross-language | Shared vectors for the audit hash and the manifest validator | Go and Python agree on every vector |
| Security | Fixtures with ESC/OSC in agent reasons; person token into `mcp`; approve without a TTY; changed TLS fingerprint; `--verbose` output grepped for the token | Stripped, exit 4, exit 2, exit 8, token never appears |
| Headless | Lima VM with the image: k3s stopped, gateway stopped | DEV-CLI-14 acceptance |
| DX timing | Founder-run script for `plugin init` → widget, `app validate` timing | Under 15 min and under 10 s, recorded in the PR |
| Packaging | CI builds all four targets, verifies signatures, installs completion in each shell container | All green |

---

## 14. Open questions for the founder

1. Accept **cobra** as a new dependency (section 11), or keep stdlib `flag` with fewer completion shells?
2. Should root on the box be allowed to approve gateway actions in rescue mode (with a loud audit entry), or never? This spec says never.
3. v0 approval from the CLI with a static owner token: accept the documented gap until passkey step-up (plan E3), or require approvals from the phone only from day one?
4. Distribution on the Mac: a Homebrew tap, a plain signed download, or both?
