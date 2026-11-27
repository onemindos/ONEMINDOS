<!-- SPDX-License-Identifier: Apache-2.0 -->
# Box export and import

**Status:** draft design with founder decisions recorded in §12. The manifest and box-config layer are implemented. Section 5.3 defines the first config-as-code slice. Phased plan: [#1285](https://github.com/onemindos/ONEMINDOS/issues/1285). Refs [#234](https://github.com/onemindos/ONEMINDOS/issues/234) (M-LIVE).

> **In plain words.** A *box bundle* is one file that says how your OneMind box is set up: its name and time zone, the people on it and their roles, the rules for what agents may do, which apps are installed with their settings and secrets, which machines have joined it, and the box's own keys. Your printed emergency kit can unlock it. You can also choose a passphrase recipient for a manual download. It is also signed, so a new box can tell the bundle really came from your box. It does not hold your photos or app files: those stay in your backups, and the bundle says exactly which backup to pull them from.
>
> You can download it, put it on a USB stick, or let the box store it with the data backups on each destination, on a schedule you choose. If the box dies, you set up a new machine, choose **Restore a OneMind box**, plug in the USB stick or point at the backup, and type your kit. The box shows what it will put back, layer by layer. You approve it, and the box rebuilds itself: settings first, then people and rules, then apps, then each app's data from the backup.

The founder's request (2026-11-26): an export and import of the whole box config, for a box that fails, a move to another machine, or a saved config; backed up off-site too, "plug in and go", as deep as possible, with an import button.

This design builds on, and does not replace:
- [BACKUPS.md](BACKUPS.md): restic units, the three keys, the emergency kit (§5), whole-box restore onto new hardware (§7.3, BAK-P4 / ONB-P3) and fencing;
- [DEPLOYMENTS.md](DEPLOYMENTS.md) §4: app revisions as the declared desired state ("GitOps-lite");
- D-019 (owner Secure Boot keys), D-020 (disk encryption and the kit), D-027 / D-028 (approvals, verification levels, recovery puts data first), D-029 (the per-box fabric root key), D-031 (release root on YubiKeys), in [DECISIONS.md](../DECISIONS.md).

## 1. Why a bundle when restic backups already exist

BACKUPS.md §7.3 already plans a whole-box restore from the restic `system` unit: the gateway database, PKI and secrets come back as files. That is the right tool for **putting the same box back exactly**. It is the wrong tool for the other three things the founder asked for:

| Need | restic `system` unit | Box bundle |
|---|---|---|
| Put the same box back after a disk dies | yes (exact copy) | yes (by layer) |
| Move to new hardware, maybe another CPU type or OneMind version | partly: the database file is tied to the schema version; `units.py` already says dropping an old database over a new box is unsafe | yes: plain JSON per layer, checked and replayed |
| Pick what comes back (settings and rules, but not people) | no: all or nothing | yes: per layer, with a preview |
| Clone a known-good setup onto a second box | no: it would copy the identity too | yes: clone mode re-makes every identity key |
| Read what is in it without OneMind | no (a database file) | yes: the manifest and layers are JSON |
| Size | the whole database, plus volumes | small (§4.5), data by reference |

So the bundle is the **portable, readable, selectable** form of the box's setup. App data stays in restic. The bundle points at the right snapshots, and restic does the heavy copying, as it does today.

## 2. What exists today (release/next, 2026-11-26)

| Area | Where | What it gives the bundle | Gap |
|---|---|---|---|
| Backups | `core/onemind_core/backups/` (gateway coordinator), `internal/backup/` (Go agent, restic), `routers/backups.py` | Destinations (`backups_destinations`, location only, never credentials), runs, snapshots, units `system` / `k3s` / `app:<id>` / `node:<id>`, content tier (`backups_content_tier`, BAK-03), hourly schedule | No single-file export; destination credentials live only in the agent's files |
| Built-in apps' tables | `backups/units.py` (#616): `onemind.builtin-units/v1`, JSON lines per table with checksums, strict restore in one transaction | The pattern this design copies: plain rows, checksums, refuse on schema mismatch, all or nothing | Tables of built-ins only; written into the restic `system` unit |
| Emergency kit | `backups/kit.py`, `BackupService._act_kit_issue`, `GET/POST /v1/backups/kit`, `/confirm` | The owner key (256 random bits, 13 base32 groups): the bundle is encrypted to a key derived from it (§4.2) | The box keeps only a fingerprint, so scheduled exports need a public key stored at kit time (§4.2). **Issuing the kit is broken once a passkey exists:** the `POST /v1/backups/kit` shortcut answers 401 `step_up_required` and a kit approved in Approvals has no route that returns its one-time answer (flagged in #1191, seen in the live audit on #1232) |
| Kit and recovery PRs (open) | #1191 (kit for every owner, disk key in the kit), #1193 (data access never needs a strong key), #1194 (kit at the box), #1196 / #1197 (recovery contacts), #1208 (legacy contacts), #1198 (Advanced protection vault spike) | Kit attach (`POST /v1/backups/kit/attach`) is where the recipient public key can be stored; contacts become part of layer b | Open; the bundle design waits on #1191's kit shape |
| First-run restore | `routers/onboarding.py`: `POST /v1/onboarding/restore/candidates`, `POST /v1/onboarding/restore/apps` (files `backup.restore` in `portable` mode) | Layer e reuses this path to pull each app's data after the config | One app at a time; the app must be installed first; nothing restores settings, people or destinations |
| Migrate kit | `core/onemind_core/migrate/` | A hashed bundle that refuses changed files (`bundle.py`); a restic REST repo hosted by the gateway (`repo.py`) | Moves a namespace from another Kubernetes cluster; not box-to-box |
| Box settings | `onboarding_settings` (box name, time zone), `update_policy`, `byo_domains` / `byo_hosts`, `notify_*`, `/data/onemind/etc/gateway.env` | Layer a | Time zone and box name are never applied to the OS (`onboarding.py` says "no host execution"); hostname, time, firewall allow rules, SSH keys and keyboard come with #1190 (OS integration) |
| People | `identity_users` (scrypt hashes, TOTP secret in clear), `identity_passkeys`, `identity_approver_keys`, `family_*` | Layer b | Passkeys are bound to the box's web name (`ONEMIND_IDENTITY_RP_ID` or the request host) |
| Rules | `automation_policies`, `_policy_uses`, `_windows`, `_rules`, `agent_stop_state`, `agents_principals`, `datagrants_*`, `hostgrants_grants` | Layer c | Permission modes and deny rules are in open PRs #1200 to #1205 |
| Apps | `app_states`, `app_runtime` (`ledger.py`), `appstore_*`, custom apps and revisions, `secrets_values` (AES-GCM, key `custodian/secrets.key`), `app_credentials` (`credentials.key`) | Layer d | DEPLOYMENTS.md §4 promises revisions under `/data/onemind/deploy/revisions/`; no code writes that folder yet |
| Fabric | `fabric_nodes` (NATS public keys), `fabric_requests` (node certificates), `machines_*`, `mesh_state`, Headscale state | Layer f | Workers pin the hub; a new hub identity means re-joining |
| Box keys | box CA `gateway/tls/ca.key`, NATS seeds `/data/onemind/nats/keys/*.nk`, `custodian/` (`secrets.key`, `job.key`), backup device key, `credentials.key`, notify VAPID keys, ACME account key | Layer g | See the flag below |
| GitOps | none on the box. DEPLOYMENTS.md §4 chooses "GitOps-lite" (approval-gated revisions, drift shown, never auto-corrected). Argo CD runs only on the founder's old cloud cluster (REQUIREMENTS.md, DOKS), which `lab-kits/cluster-replacement` retires in phase P5 | §5.3 | — |

**Flag, an existing gap found while mapping (UNVERIFIED on a running box, from reading the code):** the restic `system` unit copies `/data/onemind/etc`, `gateway/tls`, `nats/keys`, `gateway/backup-export` and `files` plus the database and audit log (`backup_system_paths()` in `os/rootfs/layers/onemind/usr/lib/onemind/onemind_firstboot.py`). It does not copy the secret-store key (`custodian/secrets.key` under the gateway's data directory), `credentials.key`, the notify keys or the job key. BACKUPS.md §6.4 assumes app secrets travel with their key. If that holds, today's whole-box restore onto new hardware would bring back app secrets it cannot decrypt. Phase 2 of this plan proves or disproves it with a test; the fix is a separate PR.

## 3. What a bundle holds, layer by layer

Each layer is one canonical JSON file (`layers/<id>.json`) with its own schema id and version. The owner picks layers on export and again on import.

### a. Box config (`box_config`) — built in phase 1
- **Now:** box name and time zone; the app update policy; the backup choice, each destination's **location** (path, node, endpoint, bucket) and the content-tier apps.
- **Next minor versions:** hostname, NTP servers, firewall allow rules, SSH public keys, keyboard, storage housekeeping (all from #1190); domains and hosts (`byo_*`); notification sources; mesh settings; built-in and plugin settings.
- **Never:** destination credentials (the gateway does not store them; the export drops any credential-looking key anyway and lists it under `excluded`). They are typed again on import.
- **Network** comes in as a preview only: interface names differ between machines, so static addresses are mapped by role (LAN, uplink), applied with the automatic revert rule (BUILDER-BRIEFING item 8), and Wi-Fi passwords travel only in the sensitive part of the layer.

### b. People and roles (`people`)
- Usernames, display names, roles (owner, adult, teen, child), disabled flags, family profiles and app classifications, notification preferences, recovery contacts and legacy contacts (#1196, #1208).
- **Passwords:** never in clear. The scrypt hash travels inside the encrypted bundle, so people keep their password on the new box.
- **TOTP secrets** are stored in clear on the box today; they travel only inside the sensitive part of the layer.
- **Passkeys cannot be exported, by design.** The private half of a passkey never leaves the person's phone or security key, and the browser binds it to the box's web name. The box only keeps the public half. So:
  - *restore or move with the same web name:* the public records can come back and the passkeys keep working. Each one is marked "check on first use", and a passkey whose sign-in counter goes backwards is refused;
  - *new web name, or clone:* the records do not come back. Each person signs in once with their password (or a recovery path) and enrols a passkey again. The owner is asked to do this first, because adding a strong key is what unlocks L2 actions (D-028).
  - Phone approver keys (`identity_approver_keys`) follow the same rule. Bringing one back counts as adding an approver, which is L2 (D-028).
- **Sessions, tokens and challenges never travel.** Everyone starts signed out. Agent and app tokens are made again.

### c. Rules (`policies`)
- Permission modes, deny rules, standing approvals ("approve and remember") with their counts and expiry, update windows, automations, the agent stop switch, agent principals, data grants and host grants.
- **Import never loosens security without the owner (§8):** for each rule the stricter of "this box" and "the bundle" wins. Standing approvals and Forever rules arrive **paused**, as D-028 already pauses a Forever rule when an agent's identity or token changes; the owner resumes each one. Bypass never arrives switched on.
- Physical-action rules never become standing approvals (D-027, #723), whatever the bundle says.

### d. Apps (`apps`)
- Every installed app: id, source (catalog version, custom app revision, community source), version and bundle hash, settings, exposure, placement, switched-off system apps, update back-off.
- **Secrets:** each app secret is decrypted with this box's store key and re-encrypted inside the bundle's sensitive part. On import it is encrypted again with the new box's key. Store keys themselves never need to travel for this.
- **Images** are not in the bundle. They come back by digest, as in BACKUPS.md §7.3. The preview lists any app whose image is not available for the new CPU type.
- **Per-app PostgreSQL passwords** live in Kubernetes Secrets. They are made again at install. The data comes back from the app's `pgdump` in restic.

### e. App data, by reference (`app_data_refs`)
- For each app: the destination id, the restic run id and snapshot ids of its last **verified** restore point (BACKUPS.md §8), size, content-tier flag and app version at the time.
- The bundle holds no data. On import, after layer d, each app's data is pulled through the existing `backup.restore` path (`portable` mode), one approval for the batch.
- A combined config-and-data export may be offered separately. Each regular bundle points to verified backup snapshots.

### f. Machines and fabric (`fabric`)
- Joined machines (name, role, public NATS key, certificate serial), machine settings, mesh settings, Headscale's node list.
- **Same box back (restore or move):** the hub's identity keys (layer g) come back, so workers keep trusting the hub. The box takes `generation + 1` and writes the fence (BACKUPS.md §7.3 step 5) so the old box, if it wakes up, stops backing up.
- **Clone:** no fabric membership is copied. Machines join the new box with a new join code; a machine can belong to one hub.
- Node secret keys never leave the nodes, today or in a bundle.

### g. The box's own keys (`box_keys`)
| Key | Restore / move | Clone | Why |
|---|---|---|---|
| Box CA (`gateway/tls/ca.key`) | moves, if the web name is unchanged | re-made | phones and browsers trust it; its name constraints bind it to the box's names |
| NATS hub seeds (`nats/keys/*.nk`) | moves | re-made | workers and apps pin them |
| Per-box fabric root key (D-029) | comes back **from the kit**, where D-029 puts its backup, not from the bundle | re-made | it signs rotations and revocations; one owner-held copy is safer than two |
| Secret-store key, `credentials.key`, notify VAPID keys, job key, backup device key | re-made | re-made | everything they protect is re-encrypted on import (layer d); push subscriptions are renewed by the apps |
| ACME account key | moves | re-made | keeps rate limits and the account for the owner's own domains |
| OneMind release root (TUF, RAUC keyring) | **never** | **never** | OneMind's, on YubiKeys (D-031); in the image, not on `/data` |
| Owner Secure Boot keys (sovereign mode, D-019) | **never** | **never** | firmware state; needs physical presence by D-019 |
| Disk key and TPM binding (D-020) | **never** | **never** | belong to the old disk; the new box prints a new kit |

### h. What is deliberately not exported
Listed in every manifest's `excluded` array (`boxbundle/manifest.py ALWAYS_EXCLUDED`) and on the import preview: passkey private keys, OneMind's release keys, the disk key and TPM binding, the kit's owner key itself, sessions and one-time codes, app data volumes and images (by reference instead), logs and the audit log. The new box starts its own audit chain, and the import is its first entry. The old chain stays in the backups (D-029 names the backup as the audit witness of last resort).

## 4. The file

### 4.1 Layout
A bundle is one file, `onemind-<box>-<date>.omb`:

```
"ONEMIND-BOX-BUNDLE\n"                      magic line
header (one JSON line, in clear):          envelope version, created_at, source instance id and box name,
                                           suite, chunk size, recipients[] (each: kind, kid, wrapped key),
                                           payload sha256, signature (Ed25519, over everything above it)
payload (encrypted, chunked):              a deterministic tar of
                                             manifest.json            (schema: sdk/schema/onemind.box-bundle.schema.json)
                                             layers/box_config.json   (and the other chosen layers)
                                             layers/<id>.sensitive.json  (secrets, only for layers that have them)
```

The manifest (built in phase 1) lists each layer's path, schema id, size, item count, sha256 and whether it is sensitive. Every layer is canonical JSON, so the same settings give the same bytes and checksum on any machine. That also makes "nothing changed since the last export" a cheap check.

### 4.2 Encryption and recipients
- The payload is sealed with the ChaCha20-Poly1305 cipher under a fresh random 256-bit data key, in 64 KiB chunks with a counter and last-chunk flag in each nonce, so a cut or reordered file fails.
- HPKE wraps the data key for the kit recipient using hybrid ML-KEM-768 plus X25519. The [released cryptography 50.0.2 API](https://cryptography.io/en/50.0.2/hazmat/primitives/hpke/) documents both components as one KEM, covered by the [API stability policy](https://cryptography.io/en/50.0.2/api-stability/). A wrap/unwrap round trip passed with the pinned wheel on macOS. Availability on the shipping image is **UNVERIFIED**. Phase 2 must exercise the actual image backend, which must support ML-KEM. Fail closed if the hybrid suite is unavailable.
- **Kit recipient.** At issue or attach, derive both private key components from the kit's owner key with separate, versioned derivation labels. Store only the hybrid public key for scheduled encryption. On restore, derive the private halves again in memory. Phase 2 must specify the derivation and test it with fixed vectors.
- **Optional recipients.** The owner can add an escrow key (BACKUPS.md §5.1) or a passphrase for a manual download. A passphrase protects its own copy of the data key and can be guessed offline, so the design requires a salted, memory-hard derivation. The kit recipient is always present.
- Because the kit recipient key is public on the box, anyone who learns it could make a bundle the kit opens. **The signature is what stops a forged bundle**, so an import refuses any bundle whose signature does not check out.

### 4.3 Signature: it came from your box
- The header is signed with an Ed25519 key for one purpose, "export", under the box's fabric root key (D-029 already plans one key per purpose under that root: jobs, policy snapshot, audit head, callout issuer). The founder approved the "export" purpose key (§12).
- A new box checks the signature against the fabric root fingerprint printed in the kit. The kit already carries the box CA fingerprint (BACKUPS.md §5.2). Restore and move require a signer trusted by the kit. The 1.1 clone design must define how the owner establishes trust in the source before accepting settings.

### 4.4 Versions
- `format.major` must match the reader's. A higher `format.minor` is accepted: newer bundles only add optional fields and new layers. Unknown layers are set aside and named on the preview (`manifest.check_manifest`).
- Each layer has its own schema id (`onemind.io/box-bundle/box-config/v1`). Fields a newer OneMind added are set aside, named and never applied (`box_config.check`).
- An older bundle on a newer box is always readable. Each layer reader keeps the converters for its older versions.
- A bundle from a **newer** OneMind version than the box is accepted only when the format allows it. Otherwise the preview says "update this box first", as `units.py` already does for schema versions.

### 4.5 Size (estimates, UNVERIFIED until phase 2 measures real boxes)
| Layer | Typical size |
|---|---|
| a box config | 2 to 20 KB |
| b people | about 2 KB per person |
| c rules | about 1 KB per rule |
| d apps | 5 to 50 KB per app (custom app revisions are the large part) |
| e data references | under 1 KB per app |
| f, g | 10 to 50 KB |
| **Whole bundle, 5 people and 30 apps** | **about 0.5 to 3 MB** before compression |

A bundle is small enough to keep many copies: on the box, on a USB stick and off-site.

## 5. Where bundles go

### 5.1 Download and USB
- **Download:** Settings → Backups and recovery → Box bundle → **Export now**. The browser saves the `.omb` file. The file is already encrypted on the box; it never exists in clear outside it.
- **USB:** export straight to a USB destination already set up for backups (onemindd writes it), so it works with no laptop.

### 5.2 Sovereign copies on every backup destination

Each destination holds an independently restorable copy of the box. Use a per-box namespace on a NAS share or S3-compatible storage, with this layout:

| Path | What it holds |
|---|---|
| `boxes/<instance-id>/data/` | The encrypted restic repository with that destination's system and app snapshots |
| `boxes/<instance-id>/copies/<copy-id>/box.omb` | The signed, encrypted config bundle with snapshot references into that same repository |
| `boxes/<instance-id>/copies/<copy-id>/complete.json` | The signed completion record with format version, box and copy IDs, generation, creation time, bundle size and digest, repository identity and required snapshot IDs |

The owner sets a schedule for each destination: every backup run, hourly, daily, weekly or manual. For a scheduled or manual copy, the box pairs the config with that destination's latest verified backup and shows both times. It publishes the completion record last, after verifying the bundle and referenced snapshots are present. Use atomic publication on a NAS and create-only writes for the completion record on object storage. An interrupted copy leaves the previous complete copy available. Restic retention protects snapshots referenced by retained copies, including ones the owner marks known-good.

On first run, point the box to any available destination and unlock with the kit. List completion records for the kit's box. Check the export signature against the kit's fabric root and try records in descending signed generation and creation time, using copy ID to break ties. Verify the bundle's size, hash, signature, authenticated encryption and layer checksums. Match the signed repository and snapshot IDs to the bundle and check the required restic snapshots and data integrity before applying. Skip incomplete or invalid candidates and show which copy passed. Storage access credentials may still be needed to reach the destination. The kit supplies the recovery proof and keys. A destination can hide newer copies, so discovery finds the newest complete copy visible there. Keeping several destinations gives the owner duplicate copies under their control.

### 5.3 Config as code for private Git

`onemind config export --dir <path>` writes a fixed layout of plain YAML with a version identifier in each file. Sort map keys and unordered lists, preserve ordered lists, and omit timestamps so the same settings give the same bytes.

| File | Contents |
|---|---|
| `settings.yaml` | Box settings and update policy, plus the backup choice and content-tier apps in the first slice |
| `apps.yaml` | Installed apps, versions and schema-approved app settings |
| `users.yaml` | Users and roles |
| `schedules.yaml` | Backup and automation schedules, including the per-destination copy cadence |
| `network.yaml` | Portable network settings, with interfaces described by role |

The first slice writes `settings.yaml` with `schema: onemind.io/config-as-code/settings/v1`. Export only fields the bundle schema explicitly marks for cleartext export. A secret marker excludes the field and its contents. Keep passwords and hashes, tokens, passkey records, every key, and credential-bearing or free-form app and destination config out of Git. Later app exporters need explicit schemas for their safe fields. Keep the YAML in your own private repository since settings can identify people and devices.

Before apply, validate file versions and show a dry-run diff against the live box. Bind approval to the proposed changes and current revision so the owner sees a fresh diff if either changes. The owner applies through the approval queue under D-027 and D-028. Any network change uses the automatic revert rule. Git updates never trigger automatic apply.

## 6. Import

### 6.1 Where the button is
- **First run:** next to today's "Restore from a backup", a **Restore a OneMind box** choice (headless twin: `onemind init --restore-bundle`, as ONB-B1 wants for every wizard step).
- **Settings → Backups and recovery → Import a box bundle** on a running box.
- **CLI:** `onemind box inspect` and `onemind box import` (§9). The CLI only requests; the owner approves.

### 6.2 Steps
1. **Choose the source:** upload the file, pick a USB stick, or pick a destination and a bundle from its list.
2. **Unlock with the kit:** type or scan it. The private key lives in memory only, for this import, as the kit already works for `restore/candidates`.
3. **Check:** the signature, the manifest (`check_manifest`), every layer's size and checksum (`check_layer`), and the format and OneMind versions.
4. **Choose the mode:** *Restore* (same box back; the source instance id matches the kit), *Move* (new hardware, same identity), or *Clone* (new identity; §7.4). The mode sets what happens to layers f and g.
5. **Preview (dry run):** for each layer, every change, field by field (`box_config.plan`): `same`, `change`, `keep`, `needs_owner` (credentials to type or a separate approval) and `skipped` (not understood by this box). The owner ticks the layers to bring back.
6. **Approve:** one `box.import` action in the approval queue, with its plan on the card (§8 for the verification level).
7. **Apply, in order:** a → b → c → d (apps installed and left stopped) → g and f → e (each app's data through `backup.restore`, then started behind the fresh health gate).
8. **Fence** (restore and move): `generation + 1`, as BACKUPS.md §7.3 step 5.
9. **Finish:** the to-do list of what only a person can do: type destination credentials, enrol passkeys, resume paused rules, re-join machines.

### 6.3 Conflicts
- **Empty box (first run):** everything chosen is applied.
- **Box with data:** per field, the preview shows current against incoming; nothing is merged silently.
  - People are matched by username. A role is never lowered or raised automatically: each change is a line the owner ticks. The current owner stays owner.
  - Rules: stricter of the two wins (§8).
  - Apps: an app installed in both keeps its data; the incoming version is only offered as an update.

### 6.4 Rollback if it fails half-way
- Before step 7, the box takes a `pre-import` backup run (the same mechanism as `pre-restore`, BACKUPS.md §6.2).
- All gateway-table layers (a, b, c and most of d) are written in **one database transaction**, as `units.py` already does for built-in tables: all of them land, or none.
- Host and cluster steps (apps, keys, fabric) follow an **import journal**; each step records how to undo it.
- If anything fails, the box stops, leaves apps stopped and offers **Undo import**, which restores the `pre-import` run. An import is always reversible, like every restore today.

### 6.5 Same box or different hardware
- **CPU type:** apps whose image digest is not multi-arch are listed and left out (BACKUPS.md §7.3).
- **Disks:** volume sizes from layer e are checked against free space before anything is written.
- **Network:** interfaces are mapped by role, never by name, and applied with an automatic revert.
- **GPU and other devices:** apps whose `machineNeeds` the new box cannot meet are installed stopped, with the reason shown (`machine_needs.py`).

## 7. The four journeys end to end

### 7.1 The box died
New machine → install OneMind → first run → **Restore a OneMind box** → choose the off-site destination → type the kit → newest bundle, mode *Restore* → preview → approve → config, people and apps come back, then the data → everyone signs in once (the web name is the same, so passkeys keep working). Workers reconnect by themselves, because the hub keys came back.

### 7.2 Move to a new machine
On the old box: **Export now** to USB (or rely on the scheduled off-site copy) and keep it running. On the new box: first run → **Restore a OneMind box** → mode *Move*. When the import finishes, the fence stops the old box from backing up. Then the owner wipes the old box (factory reset).

### 7.3 Save a known-good setup
Settings → Box bundle → **Export now** → **Mark known-good**. Later, "Compare with known-good" shows what changed. **Put back** is an import of only the layers chosen, for example only rules.

### 7.4 Clone to a second box (1.1)
On the second box: import with mode *Clone*. Settings, rules and apps come over. **What must differ:** box name and web name (asked during the import), instance id, every key in layer g (re-made), no fabric membership, no people unless ticked (and then with no passkeys and no approver keys), no app data unless chosen. Both boxes keep their own audit chains and backups.

## 8. Security rules
1. **Export is an owner action.** It goes through the approval queue as `box.export`, with passkey step-up. D-028 says exporting and restoring never depend on a strong key. So export asks for **L1**, or the kit at the box; L2 is not needed. Every export is audited: who, which layers, size, digest, where it went. The key material is never recorded.
2. **The bundle never exists in clear outside the box:** it is encrypted on the box before it is written anywhere.
3. **Agents can never export or import.** The routes have no agent scope, `core/tests/sec_policy.py` and the route matrix assert it, and `box.export` / `box.import` join the never list for standing approvals and bypass (as restore and key rotation already are, D-027).
4. **Children and teens cannot**, and neither can adults: owner only.
5. **Import needs verification by what it does** (D-028):
   - first-run import onto an empty box: the kit typed in is the proof, as for today's first-run restore. This keeps "the owner's data first";
   - import onto a box that has data (destructive): **L2**. Before the first L2 key exists: L1 plus a confirmation at the box (D-028's stand-in rule);
   - bringing back approver keys or recovery contacts is "adding an approver or contact": **L2** (D-028). First-run restore can stage those records, with activation deferred until L2 is available.
   - L2 is not in code yet (verification levels are in open PR #1184). Until then the gateway's existing passkey step-up applies (BUILDER-BRIEFING item 6).
6. **Import cannot weaken security without the owner:** for every rule and mode the stricter of current and incoming wins. Standing approvals and Forever rules arrive paused, and bypass arrives off. Loosening anything is a separate line on the preview that needs L2 and an explicit tick.
7. **Physical actions keep a person:** no bundle can create a standing approval for a physical action (D-027).
8. **Forged or changed bundles are refused:** signature, manifest schema, layer sizes and checksums, AEAD tags per chunk.
9. **The kit key is held in memory only** during inspect and import, never logged, never in the audit or the events (the rule `restore/candidates` already follows).
10. **The size limit and parser are strict:** a capped upload, canonical JSON, the schema checked before any layer is used, and no file paths taken from the bundle (layer paths must match `^layers/[a-z_]+\.json$`).

## 9. API, screen and CLI (per BUILDER-BRIEFING item 6)

| Route (proposed) | Operation id | Who | What |
|---|---|---|---|
| `GET /v1/box/bundle/preview` | `box.bundle.preview` | owner | what an export would hold now: layers, items, sizes; nothing written |
| `POST /v1/box/exports` | `box.export` (action) | owner, L1 step-up | export the chosen layers to download, USB or a destination |
| `GET /v1/box/exports`, `GET /v1/box/exports/{id}` | `box.exports.list/get` | owner | status and history |
| `GET /v1/box/exports/{id}/file` | `box.exports.file` | owner | one short-lived download of the encrypted file |
| `GET/PUT /v1/box/exports/schedule` | `box.exports.schedule.*` | owner (PUT is an action) | off-site schedule and the known-good pin |
| `POST /v1/box/imports/inspect` | `box.imports.inspect` | owner | file or destination + kit (in memory) → manifest, checks, per-layer plan; writes nothing |
| `POST /v1/box/imports` | `box.import` (action) | owner, verification by §8.5 | apply the chosen layers in the chosen mode |
| `GET /v1/box/imports/{id}`, `POST …/undo` | `box.imports.get/undo` | owner | progress, the to-do list, undo |

- **Dashboard:** Settings → Backups and recovery → **Box bundle** card (Export now, schedule, saved bundles, known-good, compare); first run → **Restore a OneMind box**; the import preview as a per-layer checklist with the change lines. Through `@onemind/sdk` only.
- **CLI (Cobra, `--json` everywhere):** `onemind box export [--layers a,b,…] [--to download|usb|<destination>]`, `onemind box inspect FILE` (kit on stdin, never echoed), `onemind box import FILE --mode restore|move|clone [--layers …] [--dry-run]`. Import and export only file requests; the owner approves in the dashboard or on the phone.
- **Phone:** the approval card shows the plan; it approves at the level §8.5 requires.

## 10. Phases
1. **Phase 1:** bundle manifest schema `sdk/schema/onemind.box-bundle.schema.json`; `core/onemind_core/boxbundle/` with the manifest checks and layer a (collect, check, plan, safe apply); round-trip unit tests. No route.
2. **Phase 2:** the encrypted, signed envelope (HPKE to the kit recipient, chunked AEAD, Ed25519 export key); store the kit recipient public key at kit issue and attach (after #1191 and the kit-with-passkey fix); a test that proves or disproves the secret-store-key gap (§2 flag); size measurements on a real box.
3. **Phase 3:** export routes, CLI `onemind box export/inspect`, the dashboard card (download and USB); the `box.export` action with step-up; audit.
4. **Phase 4:** import of layer a, then b, c (stricter-of, paused rules) through `box.imports.inspect` and `box.import`, with the preview screen, the transaction and the undo.
5. **Phase 5:** layer d (apps, re-encrypted secrets) and layer e (data references, then `backup.restore` per app).
6. **Phase 6:** layers f and g, restore and move, fencing; first-run **Restore a OneMind box** and `onemind init --restore-bundle`.
7. **Phase 7:** sovereign copies, per-destination schedule, known-good pin and compare view.
8. **Phase 8:** QEMU round trip (§11) and the hardware drill on the daily hub after Step 5.

## 11. Testing
- **Unit (phase 1):** `core/tests/test_boxbundle.py`: round trip box A → bundle → empty box B → identical layer; canonical bytes; credentials never in the layer; a changed or cut layer refused; newer minor read, newer major refused; unknown fields and layers set aside and named; a time zone the box lacks set aside; malformed layers refused; `apply` refuses unsafe sections.
- **Each later phase:** unit tests per layer (round trip and conflicts), the route matrix and `sec_policy` (owner only; agents, adults, teens and children refused), envelope tests (wrong kit, tampered chunk, truncated file, wrong signer, replayed header), and a "stricter of" property test for rules (Hypothesis, as `tests/test_properties_*.py` do).
- **Round trip on the same box:** export → factory reset (`system.factory_reset`, `core/onemind_core/routers/system.py`) → first run → import → the box exports a bundle whose layer checksums match the first one (minus re-made keys) and every app passes the fresh health gate.
- **QEMU check (phase 8, pre-registered before its code):** `test/qemu/CRITERIA-BOXBUNDLE.md` with the new prefix **BX** (checked free on 2026-11-26 against every `test/qemu/CRITERIA-*.md`):
  - BX1: a bundle exported on disk A imports on a fresh disk B; the box name, time zone and rules match;
  - BX2: an app's data comes back from the restic reference;
  - BX3: a changed byte in the bundle is refused before anything is written;
  - BX4: a failure injected after layer c leaves box B as it was after Undo.
  Pre-register in its own commit and append its sha256 to `test/qemu/PREREGISTRATION.sha256` (BUILDER-BRIEFING item 4).

## 12. Founder decisions for #1287

1. Keep passwords by carrying their hashes inside the encrypted bundle.
2. Keep passkey records when the web name stays the same. Re-enrol for a new web name.
3. Sign bundles with an "export" purpose key under the per-box fabric root (D-029).
4. Prefer hybrid ML-KEM-768 plus X25519. The stable released library API and local round trip are verified (§4.2). Shipping image support remains **UNVERIFIED**.
5. Offer an optional passphrase recipient for manual downloads.
6. Let the owner choose every backup run, hourly, daily, weekly or manual per destination.
7. Reference the app backups. A combined export may be offered separately.
8. Export secret-free config as code for private Git (§5.3).
9. First-run restore onto an empty box uses the kit alone as recovery proof (§8.5).
10. Ship clone mode in 1.1.

## 13. Sources
- Code on release/next at the time of writing: `core/onemind_core/backups/` (`kit.py`, `service.py`, `store.py`, `units.py`), `core/onemind_core/routers/backups.py`, `core/onemind_core/routers/onboarding.py`, `core/onemind_core/onboarding.py`, `core/onemind_core/automation/updatepolicy.py`, `core/onemind_core/migrate/bundle.py`, `core/onemind_core/appsecrets/crypto.py`, `core/onemind_core/identity/`, `internal/backup/units.go`, `os/rootfs/layers/onemind/usr/lib/onemind/onemind_firstboot.py`, `os/rootfs/layers/base/etc/fstab`.
- Docs: BACKUPS.md §2, §5, §6, §7.3; DEPLOYMENTS.md §4; `lab-kits/cluster-replacement/RUNBOOK.md`; DECISIONS.md D-019, D-020, D-025, D-027, D-028, D-029, D-031.
- Open PRs and issues: #1190, #1191, #1193, #1194, #1196, #1197, #1198, #1208, #1184, #1200 to #1205, #1232.
- RFC 9180 (HPKE), <https://www.rfc-editor.org/rfc/rfc9180>. The hybrid library and backend evidence is in §4.2.
- WebAuthn binds a credential to its relying party id: W3C Web Authentication Level 2, §5.1 and §6.1, <https://www.w3.org/TR/webauthn-2/>.
