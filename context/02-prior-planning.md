# Prior Planning (Nov 3–4, 2026)

Dense reference summary of the four planning documents written Nov 3–4, 2026 (held on Zeus's external drive, not in this repo). **Context for the research agent, not conclusions.** The research mission may overturn any of it with better evidence.

| Source doc | Date | Status |
|---|---|---|
| OneMind OS: Architecture and Implementation Blueprint (v1.0) | Nov 4 | **Canonical.** Engineering blueprint, reconciled with the `omos` repository's ADRs. Sections referenced below as §N. |
| OneMind OS: Unified Vision and Strategy | Nov 3 | Cross-chat synthesis (4 conversations). Companion to the Blueprint. |
| OneMindOS: Linux Desktop and Sovereign ATAK Devices, Detailed Handoff | Nov 4 | Desktop (Omarchy/Dell) and phone/ATAK research. Research dates from Oct 19, 2026. |
| ONEMIND_OS_Architecture_and_Build_Handoff | Nov 4 | **Outdated.** Uses old pillars HP/LE/GE/IT (IT = "Innovative Technology", GE = "Generational Entrepreneurship"). Says Kubernetes adds little value ("no k8s"). Treats NATS as "later". Makes Letta the primary agent engine with LiveKit voice. Mentions ClickUp/task-provider sync. Puts a CasaOS-style dashboard and a Postgres job queue in a TypeScript Core. The repo has superseded all of this. Its MVP list and license notes are still useful (see the end of this file). |

Current pillars: **SO Sovereign Operations, LE Legacy Evolution, HP Holistic Performance, GE Generational Empire.** Pillars organize purpose and never grant access. A service has one identity and may serve several pillars.

Critique recorded on Nov 10: too much hedging, too many deliverables at once, and the 90-day plan is too large for one engineer.

---

## 1. Thesis and ownership test

> Build a portable operating platform first. Extend the existing Core, deliver a useful client and SDK, prove local operation and recovery, then package a supported Linux appliance. The owner controls identity, policy, data, extensions and updates. Legacy AI is a replaceable intelligence layer. Each household or site can own its instance.

"OS" names the integrated experience. Linux, Windows, macOS and Android still supply drivers and process isolation. OneMind owns the product layer above them. A dedicated Linux image is one distribution of that layer.

**What an owner must be able to do (10):**
1. Install with no OneMind-hosted account or subscription.
2. Connect apps, discover their real capabilities and grant narrow access.
3. Use browser, workstation and phone against one environment.
4. Read prepared knowledge and capture work while offline.
5. Keep household functions running through WAN or cloud loss.
6. Replace an AI provider, app, hardware vendor or host through documented interfaces.
7. Export records, attachments, configuration, plugin inventory and authorization relationships.
8. Recover lost hardware from independent backups and recovery keys.
9. Build extensions without patching Core.
10. Share selected data with another owner without surrendering the instance.

**First-product boundary:** one owner or household, one primary site, a few enrolled devices and four reference integrations. Deferred: multi-owner hosting, a public marketplace, full federation, a custom Android ROM, arbitrary desktop code injection and a new kernel. Physical controllers keep their own interlocks and manual controls.

**Ownership acceptance:** a second operator installs from release artifacts, enrolls a device, connects an app, performs a permitted action, exports, and restores onto clean hardware. They do this without Zeus's credentials or a OneMind cloud.

**Mission scope (repo MISSION.md):** knowledge, family, founder work, homestead (greenhouse, water, energy, security, cameras, land), distributed agents, TAK/field, communities, multiple locations, small smart cities, **robotics, physical AI, drones, autonomy**. These are durable directions, not blanket authority to operate equipment.

## 2. Existing work the Blueprint keeps

The repo-evidence labels are Requirement, Recorded decision, Source evidence, Proposed and Open.
- **Operational Core** (`services/onemind-core`): Python/FastAPI, a PostgreSQL mission-request ledger with idempotency, and Dapr workflows. It is the first implementation asset, not a name to reuse.
- **onemind-mcp:** Python MCP SDK, bounded app adapters, Streamable HTTP and audited per-client caller tokens. It has no per-tool resource authorization yet, so it stays limited to its trusted read surface.
- **Hermes** is the current Legacy agent. Letta is only an optional future adapter.
- **NATS doctrine:** subject and account contracts, agent discovery and harness-owned configuration.
- **ADR 0001:** plugin-first. Reuse maintained Backstage plugins and keep Authentik, Tailscale and GitOps.
- **ADR 0002:** Backstage → reviewed Git → Argo CD → KubeVela/Crossplane. Terraform keeps clusters and networking. This is a selected target with implementation pending. The OpenChoreo retirement is approved but not proven complete.
- **ADR 0003:** native TAK clients (ATAK/iTAK, TAKX desktop if a civilian build exists, CloudTAK in the browser, an XR strategy) and a mesh strategy.
- **Roadmap (as of Nov 4):** Phase 6 in progress, Phases 7 and 8 not started. The tracker governs execution order.

**Resolved tensions:**
- TS/Fastify is for SDKs, clients and an optional new edge API. Do not rewrite the Python Core without an ADR and a measured benefit.
- Tauri is a candidate general shell. Native TAK clients remain the field experience.
- Fedora bootc is for a controlled appliance evaluation, not a workstation mandate.
- Debian/Compose is the independent-owner and dev profile. It does not replace Kubernetes for Zeus's own infrastructure.
- Letta is optional.
- NATS is the coordination fabric. Domain apps keep authoritative data.
- Old OpenChoreo references do not revive it.

## 3. Product surfaces

| Product | Owns | Does not own |
|---|---|---|
| **Core** | Instance metadata, identity bindings, policy, enrolled devices, plugin lifecycle, routing, coordination, audit, sync protocol | Every app's database, all agent config, kernel and drivers |
| **Client** | Workspace UI, local cache, capture queue, device enrollment, selected device integrations, freshness and conflict displays | Unrestricted host access, global authority while offline |
| **SDK** | Versioned schemas, generated clients, permission vocabulary, adapter interfaces, packaging/signing tools, conformance fixtures | A universal app rewrite or a privilege bypass |
| **Desktop layer** | Optional Omarchy/workstation menus, panels and local workflows | Backend authorization or a sandbox for shell plugins |
| **OS appliance / Image** | Supported host image, bootstrap, update/recovery UX, tested hardware profile | Portability to every ARM board or phone |
| **Federation** (M6) | Scoped owner-to-owner and site-to-site sharing | Transitive grants or recall of shared data |

The Vision doc adds a **Dashboard/Home**, a CasaOS-like personal-cloud experience for connecting apps, browsing capabilities and managing the environment. Whether to reuse CasaOS/ZimaOS code or only copy its interaction model is open. Installing an app, connecting an adapter and granting permissions are **three separate user actions**. Deploying Home Assistant does not grant Legacy permission to operate the house.

**First vertical slice:**
1. Local sign-in.
2. Fresh site status.
3. Legacy summarizes an authorized note.
4. A reviewed action toggles an allowlisted HA test light, and the observed real state is shown.
5. A timestamped TAK observation is displayed.
6. An offline capture syncs on reconnect without duplication.
7. The instance restores from backup.

Core must keep working with the agent and model stopped.

## 4. Authority boundaries

**Authority rule:** a UI, LLM, MCP descriptor or bus message only *requests* an operation. A trusted execution boundary does the rest:
- authenticates the principal;
- validates the resource and policy;
- checks current conditions;
- records the outcome.

Only that executor holds the upstream credential.

| Plane | Authoritative owner | OneMind role |
|---|---|---|
| Infra desired state | Reviewed Git and the designated reconciler | Propose changes, show evidence |
| App records | The owning service, DB or files | Query and update through the supported API |
| Capability policy | Core policy store and enforcement points | Decide subject/action/resource/context |
| Device/site actuation | Site-local executor and physical controller | Bounded request, verify state, keep manual control |
| Observations | Source system (timestamp and provenance) | Cache with freshness and coverage |
| Agent settings | Each harness's native config | Edit through harness endpoints only |

Never keep a competing editable copy of harness config or a second infra desired-state DB. Assign one controller owner per resource field. NATS is not a reconciler. A Compose install never manages a workload that Argo owns. Tailscale is transport, not authorization. Local LAN DNS/TLS and recovery access must work without an internet-dependent login.

**Proposed Core modules:**
- instance/device registry;
- identity/policy;
- capability registry;
- action executor (ledger and outbox);
- plugin supervisor;
- sync service;
- audit/evidence;
- domain adapters.

Start them as modules and split them only when isolation or load justifies it.

**Proposed API:**

| Route | Purpose and rule |
|---|---|
| `GET /v1/instance` | Instance info, no topology dump |
| `/v1/devices` | One-time expiring enrollment, revocation |
| `/v1/plugins` | Desired, running and healthy are separate states |
| `/v1/capabilities` | List is filtered, and execution rechecks |
| `POST /v1/actions` | Requires idempotency key, expiry and expected version |
| `GET /v1/actions/{id}` | "Accepted" never means "executed" |
| `/v1/sync` | Sync cursors |
| `/v1/exports` | Owner exports |

Errors: `permission_denied`, `stale_precondition`, `expired`, `offline_not_supported`, `conflict`, `outcome_unknown`, each with a correlation ID.

Fastify compiles schemas to code, so never compile plugin-supplied schemas in the privileged process.

**Client:** React/TS. The web client uses IndexedDB and native clients use SQLite through a narrow native interface. Areas are Home, Applications, Operations, Knowledge, Agents and Owner settings. Tauri capabilities do not replace Core policy. Bundle trusted UI with a strict CSP and give remote or extension content no native bridge, because Tauri cannot reliably separate iframe requests on Linux/Android.

| Platform | Prove before claiming support |
|---|---|
| Browser | Storage eviction, offline reload, accessibility, session expiry |
| Linux desktop | WebView/distro cohort, signed packaging, file scope |
| macOS/Windows | Signing and updates, keychain, sleep/resume |
| Android | Background limits, battery, storage, location consent |
| iOS | Companion app only |

## 5. Action lifecycle and approvals

`requested → awaiting_approval → accepted → dispatched → succeeded | failed | outcome_unknown | expired | cancelled`

Every path follows the same lifecycle: dashboard, agent, CLI, MCP or automation.
- **Approval** is policy-dependent. It binds the exact normalized parameters, resource, expiry and grant revision. It never approves an agent's whole plan.
- **Ledger:** persist the accepted action before dispatch, and write the outbox in the same transaction. Consumers commit an inbox/idempotency record together with their state change.
- **Timeouts:** a timeout after the upstream call is `outcome_unknown`. Reconcile by upstream request ID or observed state before any retry. If the upstream cannot deduplicate, do not auto-retry non-idempotent operations.
- **Physical commands:** short TTLs and current-state checks. A queued "unlock" or "start irrigation" must never replay hours later. Safety and stop functions live in dedicated controllers and never depend on cloud inference, a browser or a remote approval.

## 6. SDK, plugin manifest and signing

**Extension classes:**

| Class | Runtime boundary | Initial policy |
|---|---|---|
| Remote MCP/API connector | Filtered gateway | Trusted registration |
| Managed connector (HA/TAK) | Separate container with scoped secrets | Curated first-party |
| Pure computation | Extism/WASM worker with limited host functions, no ambient WASI fs/net, memory/fuel/output caps | Experimental |
| UI extension | Sandboxed browser surface | Optional MCP Apps, with declared origins and no inherited credentials |
| Native client integration | Signed with the client | Reviewed release-time code only |
| Deployment package | Compose or GitOps | Separate from tool permission |

MCP standardizes tools and resources. It does not install, certify publishers or enforce OneMind permissions (OS-D06).

**Manifest (illustrative):**
- `apiVersion: plugins.onemind.local/v1alpha1`, `kind: Plugin`.
- `metadata`: id, name, version, publisher.
- `compatibility`: coreApi range, manifest version.
- `runtime`: type container, artifact plus sha256 digest, architectures, transport `mcp-streamable-http`, endpoint.
- `capabilities[]`: id, inputSchema, effect (read/write), idempotency (e.g. desired-state), offline (e.g. site-local-only), approvalClass.
- `permissions.request[]`: action and resourceType.
- `network.requiredBindings`, `secrets.requiredBindings`.
- `events.contractRefs`.
- `storage`: namespace, maxMiB, dataClass.
- `lifecycle`: health, migration, uninstallData `retain-until-owner-export-or-delete`.
- `release`: license, SBOM (SPDX), provenance.

The manifest *requests* permissions. Installation creates instance-specific bindings (for example site/home + light.workbench) that the owner approves. Users and agents then receive separate invoke grants.

**Signing design:**
1. Build an immutable artifact with a digest inventory of every file, schema, UI asset and migration, bound to the image or module digest.
2. Sign canonical JSON bytes (reject duplicate keys and ambiguous YAML) with a detached signature or DSSE envelope that names the algorithm, payload type and key ID.
3. Use Cosign or Sigstore, not custom crypto. Verify the expected publisher identity or issuer plus the digest, not "any valid signature".
4. Keep an owner-managed local trust store, revocation metadata and a rollback-protection release index. Separate official, owner-trusted third-party and dev tiers.
5. Allow offline verification from cached roots and bundles, with metadata expiry and a maximum offline age. Never trust new releases when metadata is stale.
6. Rotate keys with a signed transition. Keep the root offline and use constrained CI release keys. Have a compromised-key quarantine procedure.

A signature proves integrity, not safety. Also scan, generate an SBOM, review grants and enforce at runtime.

**Plugin state machine:** `discovered → verified → reviewed → staged → healthy → active → disabled | quarantined | removed`.
- Review shows the permission diff.
- An update that asks for new permissions needs renewed consent, and grants never auto-expand.
- Disable rejects new calls immediately and revokes tokens.
- Uninstall keeps data by default, with an explicit and audited export/delete choice.

**Containers:**
- run non-root with a read-only root filesystem;
- no Docker socket, no host PID or network namespace;
- dropped capabilities and resource limits;
- a dedicated service account in Kubernetes with deny-by-default network policies.

Hostile native code may need a VM.

## 7. Identity and permission model

Principals: Person (Authentik/OIDC subject), Device (enrolled key pair), Workload/plugin, Agent, Automation (named identity plus owner) and Remote instance (pinned key plus agreement). Use opaque stable IDs and carry the actor and the executing workload separately. **An agent acting for Zeus is not Zeus.**

`allow = authenticated ∧ active principal ∧ active device/workload ∧ action grant ∧ resource scope ∧ context constraints ∧ current approval when required`

| Action family | Default |
|---|---|
| Read knowledge | Selected collections, private fields redacted |
| Capture/draft | Within a granted namespace, provenance audited |
| Modify record | Expected version or hash |
| Physical control | Explicit entity scope, TTL, site executor, safety policy |
| Infra change | Existing repo review path |
| Identity, secrets, backup keys | Owner ceremony |
| Cross-owner sharing | Explicit agreement, no transitive grants |

**Rules:**
- **Identity claims:** strip caller identity headers at ingress. Use OIDC auth-code + PKCE for native clients and a same-origin cookie session with CSRF protection for web. Never put a service credential in a web bundle. Email is not an identity key.
- **Delegated grants** bind subject, agent, action, resources, expiry, maximum uses or budget, and the approval reference. Downstream services recheck.
- **Audit** records request ID, actor, delegated actor, workload, device, policy revision, resource, approval hash, outcome and timestamps.
- **Offline devices** cannot learn of a remote revocation. Minimize cached data and offline grant lifetime.
- **Backstage** currently gives broad signed-in read access and has no per-entity family isolation. Do not call it multi-user ready.

## 8. NATS event contracts

Keep the doctrine subjects: `evt.{domain}.{entity}.{event}`, `cmd.{domain}.{entity}.{action}`, `tel.{node}.{class}.{metric}`, `svc.{service}.{endpoint}`, with domains so/le/hp/ge/sys plus specialized geo and agent contracts. Agent discovery uses `$SRV.PING.agents` / `$SRV.INFO.agents`; never hardcode a roster. An actor name in a payload proves nothing; account import/export rules authorize.

Known drift: TAK raw `tak.cot.out` / `tak.cot.inject` versus geo projections, and the HA bridge's older `omos.home.*` subjects. Do not mass-rename. Inventory producers and consumers and migrate one contract at a time with replay and rollback evidence.

**Proposed envelope `onemind.event.v1`:**
- `id`, `type`;
- `instance_id`, `site_id`, `source_id`, `actor_id`;
- `occurred_at`, `observed_at`;
- `correlation_id`, `causation_id`;
- `resource{id, version}`;
- `data` (content by reference only).

Geo hot paths keep epoch-ms envelopes.

**Delivery:** at-least-once, with database-level deduplication. The JetStream dedup window is not exactly-once physical effect.

| Stream | Policy |
|---|---|
| Action/audit | No silent discard: durable outbox, explicit ack, bounded retries, dead-letter process |
| Sensor telemetry | Summarize or drop, short retention, latest-state projection |
| TAK positions | TTL/freshness, never stale actuation |
| Knowledge changes | Durable, with cursors and snapshots |

Set limits by bytes, age and message size, and monitor lag and disk. A full disk gives an explicit degraded state. Do not create a durable consumer per browser tab. **Leaf nodes do not store-and-forward by themselves.** Offline sites need local JetStream with sources/mirrors or an app outbox, plus a tested reconnect procedure. Currently in-cluster NATS is the authority bus and edge/Mac nodes are leaf nodes.

## 9. Data ownership and storage

| Data | Authority | Export |
|---|---|---|
| Grants, devices, lifecycle, action ledger | Core PostgreSQL | JSON/JSONL plus schema |
| App records | The app's DB | App export plus adapter mapping |
| Knowledge | Owner Markdown/files (indexes and embeddings are derived) | Markdown with attachments |
| Agent memory/config | Harness | Native export plus neutral summaries |
| Positions/telemetry | Source events | Bounded JSONL/geo formats |
| Secrets/keys | Secret manager or OS keystore | Separate encrypted recovery package |
| Client captures | Device until acknowledged | Local export even if Core is down |

**Proposed Core tables** (map existing equivalents first): instances, sites, devices, principal_bindings, grants, plugin_releases, plugin_installations, capability_bindings, actions, approvals, audit_entries, outbox, inbox_dedup, sync_changes, tombstones. Every scoped table has an instance key. Hosted multi-tenancy later needs explicit isolation, row-level security and adversarial tests. PITR needs a base backup plus WAL archive; replication is not backup.

**Device store (SQLite):**
- Separate cache, drafts, queued operations and sync metadata.
- Record `resource_version`, `origin`, `observed_at`, `fresh_until`, the operation ID and the acknowledged cursor.
- Encrypt with a maintained solution; stock SQLite is not encrypted.
- Never put WAL databases on a network filesystem.

**Export:** a versioned archive with:
- a manifest, checksums and JSONL;
- Markdown and attachments;
- plugin digests and policy relationships;
- restore instructions.

Tokens are excluded by default, with a separate encrypted secrets package. The export must be understandable without the UI, and it is restore-tested into a clean instance.

## 10. Offline-first sync

Four modes:
1. WAN down, LAN up: local Core, IdP and apps keep working.
2. Device isolated: cached reads, capture and local functions only.
3. Field peer network: local TAK and site services, with no path home.
4. Reconnect: bounded replay, deduplication and explicit conflicts, with no global total order.

**One writer authority per resource or site.** Phones are not PostgreSQL replicas. Do not stretch consensus across WAN links. Moving authority requires fencing the old writer, checkpoint, restore, cutover and reconciliation.

**Algorithm:**
1. Enroll the device, then fetch an authorized snapshot and an opaque cursor.
2. Make local operations with a UUID, base version, device sequence and dependencies. Do not rely on clock order.
3. On reconnect, re-authenticate, pull policy and state, then push bounded batches.
4. The server authorizes each operation, checks expiry and preconditions, and records dedup transactionally. It returns accepted, rejected or conflict for each operation.
5. Pull changes after the cursor, apply them atomically and advance the cursor. A permission change rebuilds the affected cache scopes.
6. If the cursor has expired, take a new snapshot and keep unacknowledged local work for reconciliation.

**Conflict policy:**

| Record type | Policy |
|---|---|
| Captures | Append-only |
| Task fields | Optimistic version check, conflicting fields shown |
| Markdown | Hash-based three-way merge, both versions kept on overlap |
| Position/sensor | Source sequence and freshness |
| Device control | Never blind replay |
| Permissions/config | Online only |
| Collaborative text | CRDT only if a real need appears |

Cache budgets: 7 days of knowledge and tasks plus a field pack, and 72 h of queued captures. The UI shows connectivity, last sync, observed time, queue count and conflicts. A cached sensor value is never shown as "live".

## 11. Reference integrations

**Hermes and Legacy AI:**
- Discover agents through the existing protocol. Each agent gets an identity, scoped tools, a deadline, a tool budget and a cancellation path.
- Record evidence links; model narration is not completion.
- Settings stay native to the harness.
- With all agents stopped, human Core use, local operations and recovery still work.
- Inference sits behind a provider interface with a local/remote classification and a data-handling policy. A local server that calls a remote model is not offline AI.

**Letta:**
- Optional, behind a version-pinned adapter. Pick the SDK or server generation explicitly.
- Keep procedural memory, summaries and human knowledge distinct.
- Acceptance: swap the backend in a fixture, keep knowledge and permissions, reject an over-scoped call, and keep working with Letta stopped.

**Obsidian / knowledge:**
- Markdown is the foundation and Obsidian is an optional client.
- The scoped adapter blocks traversal and symlink escapes and excludes secrets.
- Writes use an expected hash, atomic replace, provenance and versions.
- Run one sync authority per vault.
- Do not redistribute Obsidian without a license review.
- Acceptance: external edit, offline conflict without loss, export opens in another editor.

**Home Assistant:**
- REST for bounded calls and WebSocket for subscriptions. Credentials stay server-side under a dedicated identity, with entity and service allowlists enforced in the adapter.
- Start read-only, then one test light with desired-state actions, TTL and observed confirmation.
- Locks, heaters, pumps and irrigation need separate policies, interlocks and a manual path. `call_service` success is not physical completion.
- The existing HA bridge forwards commands broadly and has unfinished persistence and TLS. Audit it before reuse.
- Acceptance: WAN-down operation, reconnect, denied entity, unknown outcome, no late replay.

**TAK:**
- Native clients stay primary. The OneMind client gives context and links, not ATAK replacement or plugin parity.
- The TAK mesh gateway exists as source only, not a verified deployment. Multicast needs a real LAN/edge presence and does not reach cloud pods.
- Use per-device certificates. Parse CoT with bounded XML and external entities disabled.
- Preserve UID, source time, stale time, CRS and provenance.
- Normalize through a reviewed bridge with origin and bridge IDs and hop limits, so nothing loops.
- Observation and injection are separate permissions. Radio and mesh bandwidth must be measured.
- Acceptance: permitted observation, denied injection, stale rendering, restart without loop, isolated field workflow, no duplicate tracks on reconnect.

**n8n:**
- Optional workflow app with its own identity. It is never a route around Core policy.
- Embedding or offering customer-facing workflow building needs a commercial license; check the OEM terms.

## 12. Security threat model

| Threat | Controls | Residual risk |
|---|---|---|
| Malicious plugin or update | Signing, digest pinning, isolation, egress and secret grants, staged rollout | Signed code can still be malicious |
| Prompt injection | Untrusted-content boundaries, schema validation, independent policy, narrow tools | A model can propose bad actions; the executor rejects them |
| Stolen device | Encryption, keychain, scoped cache, revocation | Already-decrypted data is exposed |
| Compromised agent | Unique identity, delegated scope, no admin credentials | Executed actions may be irreversible |
| LAN or mesh compromise | TLS, app authentication, segmentation | Network membership is not trust |
| SaaS loss | Local essentials, exports, adapters | SaaS-only features die |
| Ransomware | Offline or immutable independent backup and drills | Connected snapshots can be destroyed |
| Cross-owner leak | Separate instances, export filters, tenant tests | Shared data cannot be recalled |

**Required before an external alpha:**
- TLS everywhere, with local trust bootstrap that survives WAN loss.
- Secrets kept in the established secret path, Kubernetes secrets encrypted at rest and RBAC tightened. Recovering the SealedSecrets controller key is a separate requirement.
- Plugin egress restricted: block metadata services and unintended private ranges, and validate DNS and redirects.
- MCP OAuth audience validation; never forward incoming tokens.
- Data separated into family/private, operational and public.
- Opt-in telemetry, and a visible indication when inference leaves the site.
- No body logging, and redacted support bundles.
- No end-to-end-encryption claim while a server-side agent can read the data.
- Dependency locks, secret scanning, SBOMs and a vulnerability response process.
- A license choice before community distribution. Apache-2.0 is a candidate for Core and SDK. Omarchy is MIT and CasaOS is Apache-2.0.

## 13. Deployment profiles

Target topology (not current reality): the home site holds local identity and DNS, Core, policy and PostgreSQL, local NATS/JetStream, HA/TAK/knowledge and encrypted backup. Dell, Mac and phone are clients. Barn and field nodes do scoped store-and-forward. The cloud is an optional relay and secondary backup. An offsite encrypted copy is kept independently.

| Profile | Composition | Use |
|---|---|---|
| Development | Core, PG, NATS and fixtures | Contract work |
| Single-host owner | Compose, volumes, TLS, local IdP, scheduled backup | Independent-owner alpha; single machine, not HA |
| Home production | K8s/K3s with GitOps, local identity and data | Zeus's long-term substrate |
| Remote/field node | Minimum site-local authority plus durable buffer | Intermittent links |
| Cloud extension | Public endpoints, relay, secondary backup, compute | Optional, never an essential dependency |

K3s embedded-etcd HA needs at least 3 servers (an odd number) on a reliable low-latency site. Control-plane HA does not make PG or storage highly available. Capacity hypotheses: 4 cores, 8 GB and SSD for a Core-only lab, or 16 GB with IdP, monitoring and adapters. These are unmeasured. HA, TAK, cameras and inference need their own budgets, and the Dell's 16 GB is not a model-hosting budget. Add UPS and power-loss tests.

**Linux host foundation:**

| Option | Role | Main benefit | Main cost | Rollback limit | Stage |
|---|---|---|---|---|---|
| Debian stable + containers | Reference server install | Familiar, low packaging effort | Host drift | Must design snapshots and data restore | Independent-owner alpha and lab |
| Fedora bootc | Branded managed appliance | OCI-delivered host updates, repeatable image | Image pipeline, hardware qualification, release operations | Rollback does not reverse app data migrations | Post-alpha evaluation |
| NixOS | Declarative fleet/host profile | Reproducible generations | Specialist skills | Generation rollback does not restore mutable data | Optional contributor edition |

**Delivery decision:**
1. Containers on existing infrastructure plus a clean local VM.
2. A Debian + Compose single-host profile.
3. Validate the Omarchy Dell layer separately.
4. Run a bootc appliance on one specific x86-64 machine only after install, update and restore work.
5. Add ARM64 only after a named board passes firmware, storage, network, boot and recovery tests. An ARM64 binary alone proves nothing.

Use osbuild/image-builder; image-builder-cli is archived.

**Appliance checklist:**
- no owner secrets in the image;
- offline first boot and unique host keys;
- encrypted data with recovery-key export;
- verified update provenance and local recovery;
- tested: interrupted update, boot failure, failed app health, full disk, OS rollback and independent data restore.

## 14. Release and update procedure

The release BOM covers:
- versions, commits and image digests;
- schema and protocol versions, migrations;
- the host/CPU matrix;
- signatures, SBOM and known limitations.

Never ship `latest`. Channels are dev, pilot and stable. Zeus's lab is the canary. Owners control maintenance windows and can pause.

**Update steps:**
1. Verify the artifact, publisher, compatibility and free disk space.
2. Check that a recent backup exists and run preflight/export.
3. Stage without switching traffic.
4. Apply additive schema expansion, then update services in a tested order.
5. Probe real capabilities and permissions, not just `/health`.
6. Switch traffic and keep the rollback artifacts.
7. Contract the schema only after the compatibility window closes.

Support current and previous minor client/SDK versions. Mobile updates lag. OS image, native client, container, plugin and DB migration updates are **separate transactions**. Host rollback does not roll back data.

## 15. Backup, RPO/RTO and recovery drill

| Class | RPO | RTO |
|---|---|---|
| Core, identity, accepted records | ≤1 h | ≤4 h on a prepared spare host |
| Knowledge and attachments | ≤24 h, plus local unacknowledged capture export | ≤4 h for the working set |
| Telemetry history | ≤24 h or documented discard | ≤24 h |
| Physical local operation | Controller continuity | Manual path available immediately |

**Backup set:**
- app databases and migration versions;
- IdP database and config;
- secrets and recovery keys;
- NATS config and durable state;
- knowledge and attachments;
- agent memory and settings;
- Dapr/workflow state;
- artifact digests;
- GitOps/bootstrap files;
- DNS/TLS recovery notes.

Keep a fast local copy plus an encrypted offsite/offline copy, with keys held outside the cluster and reachable without the primary IdP.

**Drill:**
1. Start a clean isolated machine with no access to the original cluster or cloud.
2. Verify checksums and decrypt with independently held keys.
3. Restore identity, secrets and bootstrap, then databases and files.
4. Restore Core and adapters by digest, with actuators disconnected.
5. Verify users, grants, record counts, attachments, plugins and action history.
6. Reconcile pending and unknown operations, and fence old writers.
7. Test a read, offline sync, a bounded action and an export, and record the actual RPO/RTO.

A backup counts as "verified" only after a restore drill. Observability reuses Prometheus/Grafana. Status always shows source, observation time and coverage, and separates configured, connected, authenticated, operational and recoverable.

## 16. Milestones M0–M6

| Stage | Deliverable | Exit gate |
|---|---|---|
| M0 Reconcile | Evidence map, contract inventory, decisions, backlog | Existing and proposed mapped, one authority per concern |
| M1 Secure vertical slice | Existing Core, identity, one read connector, action ledger | Denial tests, audit, clean restore |
| M2 Repeatable extensions | Signed curated packages, lifecycle, scoped executor, 4 reference interfaces | Install, disable and update without Core edits; bad package denied |
| M3 Disconnected client | Web plus one desktop target, capture/cache/conflict UX | Process kill, reconnect and WAN-loss tests lose no accepted capture |
| M4 Independent owner alpha | Compose install, onboarding, backup, export, update | Second operator succeeds on a clean host |
| M5 Managed appliance | Pinned image pipeline, one hardware profile | Offline first boot, signed update, failed-boot recovery, data restore |
| M6 Multi-site / federation | Scoped sharing, local authority | Partition, rejoin and revocation with no leakage |

The 90-day aim is a credible M4 or an evidenced subset. M5 and M6 are gated follow-ons. If M1 or recovery fails, cut breadth.

## 17. 30/60/90 plan

The plan assumes one engineer, kickoff Nov 4, 2026, checkpoints Dec 4, Jan 3 and Feb 2.

**Days 1–30:**

| Days | Work |
|---|---|
| 1–5 | Inventory of tracker, ADRs and contracts; choose a lab |
| 6–10 | Actor/resource/action schema, permission checks, threat model, versioning |
| 11–20 | One scoped read and one bounded action through the existing Core |
| 21–30 | Install fixture, backup/export, isolated restore, WAN-down dependency map |

Gate: human authentication, separate agent identity, one permitted and one denied capability, a durable request record, Core usable with AI stopped, a clean restore.

**Days 31–60:**

| Days | Work |
|---|---|
| 31–40 | Signed manifest, supervisor, bindings; tampered package denied |
| 41–50 | Knowledge, HA, TAK and Legacy adapters, with a capability matrix |
| 51–60 | Local store, queue, cursors, conflict UI, Tauri only if useful |

Gate: four interfaces at read scope, offline capture works, and an expired physical command never executes.

**Days 61–90:**

| Days | Work |
|---|---|
| 61–70 | Single-host installer, local IdP, enrollment, exports |
| 71–80 | Outage, disk-full, revocation, interrupted-update and recovery drills, with measured RPO/RTO |
| 81–90 | Second-operator alpha, signed bundle, bootc evaluation only if gates passed |

Gate: an independent owner can install, operate, export and restore. Do not weaken safety to hit a date.

**First 10 tickets:**
1. Map services to the blueprint.
2. Approve the schema.
3. Per-resource enforcement with denial fixtures.
4. Ledger idempotency and unknown-outcome handling.
5. Clean restore with independent keys.
6. Signed manifest and trust store.
7. Knowledge adapter with hash-checked writes.
8. HA test-light control and TAK read fixtures.
9. Offline queue and conflicts.
10. Clean-owner install rehearsal and alpha matrix.

## 18. Acceptance tests A01–A24 (all unexecuted)

| ID | Test | Pass condition |
|---|---|---|
| A01 | Independent install | Clean host, published bundle only, no Zeus credentials or vendor login |
| A02 | Human/agent isolation | Forged actor header and over-scoped request are denied |
| A03 | AI independence | With model and harness stopped, Core, grants, knowledge and human operation still work |
| A04 | Signed extension | Tampered bytes, wrong digest, unknown signer, incompatible schema and stale trust are all handled |
| A05 | Permission escalation | A plugin update does not auto-expand grants |
| A06 | Revocation | Online calls rejected within ≤60 s, queued work rechecked, offline window documented |
| A07 | Idempotency | Repeating an operation gives the same result with no duplicate effect |
| A08 | Ambiguous timeout | Result stays `outcome_unknown` with no unsafe redispatch |
| A09 | Offline capture | 72 h (or equivalent fixture) with restart and replay, nothing lost or duplicated |
| A10 | Conflicts | Two devices editing the same version: overlap preserved, no silent overwrite |
| A11 | WAN-down home | 24 h outage: local identity, DNS, Core, HA and TAK still work after restart |
| A12 | Expired control | Stale queued physical command is rejected |
| A13 | Site partition | Local authority continues, old writer is fenced, no dual control |
| A14 | Durable bus | Local buffer catches up within bounds, drop policy is visible |
| A15 | TAK correctness | Stable UID, stale-time rendering, no loop, denied injection, native workflow works |
| A16 | Knowledge portability | Export opens in a plain editor; traversal and symlink escape denied |
| A17 | Restore | Clean isolated host recovers keys, identity, data and config within targets |
| A18 | Upgrade failure | Interrupted update recovers, incompatible DB rollback is blocked |
| A19 | Secret handling | No credentials in bundle, logs or export; plugins cannot read each other's secrets |
| A20 | Owner isolation | Two instances cannot read or invoke each other |
| A21 | Degraded upstream | One app outage is isolated and freshness is reported accurately |
| A22 | Resource limits | Oversized payload, untrusted schema, XML attack, CPU/memory and disk-full are all bounded |
| A23 | Device lifecycle | Lost device revoked, deliberate re-enrollment, local recovery without cloud |
| A24 | Second operator | Install, use, export and restore done unaided |

Performance fixture: 10 devices, 20 capabilities, 10 concurrent users, 50 events/s, p95 ≤300 ms for local metadata reads. Each acceptance record has a date, commit, digest, versions, topology, negative cases, artifacts and reviewer. Results are pass, fail, blocked or not-tested.

## 19. Decision records OS-D01 to OS-D14 (all proposed)

| ID | Decision | Revisit when |
|---|---|---|
| D01 | Platform first, appliance later | Owner alpha passes |
| D02 | Keep the Python Core and MCP; TS for SDK and UI | Measured backend limit |
| D03 | Debian/Compose reference, bootc evaluation | Support evidence |
| D04 | Omarchy desktop pilot stays separate | Dell results |
| D05 | Tauri workspace complements TAK clients | Platform gaps |
| D06 | MCP is an interface, not trust | Protocol change |
| D07 | Curated signed packages first | Strong isolation exists |
| D08 | Domain apps own their records | New domain |
| D09 | PostgreSQL Core plus device store | Sync limits |
| D10 | Keep NATS contracts, add adapters | Reviewed migration |
| D11 | One local writer per resource | Proven multi-writer need |
| D12 | Letta optional behind an adapter | Memory need |
| D13 | Owner-controlled keys and recovery | Hosted or federation product |
| D14 | Federation deferred | M4–M5 evidence |

## 20. Risk register (priority)

**High:**
- Rewriting the platform in a new language.
- Too many products at once.
- Hidden cloud dependencies for identity, DNS or inference (needs a cold-start WAN-down drill).
- Plugin or agent overreach.
- Sync or dual-authority data loss.
- Backups that exist without recovery keys.
- Late physical replay.
- TAK, HA and event contract drift.
- Controller ownership overlap.
- Signing-infrastructure compromise.
- Multi-owner privacy leaks.

**Medium:**
- Mobile and desktop native variance.
- Maintenance and licensing burden.
- Unbounded telemetry and video growth.

## 21. Open choices (before external alpha)

- Local hardware, storage, UPS and network, and which functions survive which outage durations.
- Owner, family and worker roles; private collections; allowed physical actions.
- The first native target, and whether Tauri adds value.
- The smallest policy gap in Core/MCP, and whether a gateway is needed.
- Which data needs 1 h recovery and which daily export, and who holds the keys.
- License, support window and redistribution.
- The Letta generation, local inference benchmarks and permitted model egress.
- The owner deployment cohort and the bootc hardware.

Plus the Vision doc's list:
- Desktop base for family and community machines.
- CasaOS: reuse its code or only its UX.
- Core boundary.
- First release hardware and clients.
- Phone and Google hardware.
- Federation authority.

Repeated across docs: is Google hardware acceptable, what state is the Dell in, what is the first slice, which task system.

---

## 22. Linux desktop and ATAK handoff (research of Oct 19)

**Position reached:**
- Omarchy on the Dell is a *preferred pilot candidate*, not a proven "best".
- Build an upstream-compatible OneMind extension layer before any fork.
- Community distribution is more than a plugin.
- Essential site operation must not depend on the laptop or WAN.
- Pick phone and OS together, with GrapheneOS as the security baseline.
- OUKITEL only for a dedicated endurance role.
- Test the exact ATAK loadout.

Nothing was installed, bought or implemented.

**Dell Latitude 5540** (user-reported specs, used as the Omarchy pilot machine):

| Item | Value |
|---|---|
| Model | P127F, built 2023 |
| CPU | i5-1345U (13th gen, vPro) |
| RAM | 16 GB |
| Graphics | Intel UHD |
| OS at the time | Windows |
| Unknown | Wi-Fi/BT adapter, SSD size, BIOS, dock, peripherals, fingerprint |

Dell lists Ubuntu 22.04 support. A known issue on this model: with Omarchy 4.0.1-1 and BIOS 1.26.0, disabling Bluetooth could remove the adapter (upstream issue #7936, fix PR open as of Oct). The sampled Omarchy v4.0.5 is Arch-based with Hyprland and a Quickshell shell. Its plugin manifests use QML and IPC, with kinds widget, panel, menu, overlay, service and bar. Plugins run with full user authority and are **not a sandbox**. The AI launchers can auto-approve agent actions, so review them. Root snapshot rollback **does not restore /home**.

**Desktop alternatives:** Aurora (KDE image, for family/community machines), Bluefin DX (container dev, GNOME), NixOS, Ubuntu LTS, Fedora KDE or a custom Universal Blue image. Fedora KDE was the laptop chat's fallback after Zeus rejected Ubuntu. The Mac stays home for persistent jobs and heavy compute. Tailscale, SSH, Nextcloud selective sync and 32 GB/1 TB were floated as targets, not purchases.

**14 proposed desktop plugins:**
1. OneMind Hub (site selector, alerts, observation age)
2. Hermes Roster
3. Homestead Panel
4. TAK Desk
5. Global Fleet
6. Field Pack
7. Camera Desk
8. Knowledge Capture
9. Daily Brief
10. Model Status (does data leave the site?)
11. GitOps Desk
12. NATS Observer
13. Recovery Readiness
14. Access Panel

First slice: Hub, a read-only Roster and a small TAK Desk. The alternative first slice is an assistant panel, Codex access, tasks and one HA connector.

**Distribution units:**
- desktop layer;
- workstation setup and enrollment;
- infrastructure profile;
- release and recovery material.

Each user gets their own identities and credentials, never Zeus's. A managed image is later: compare Omarchy-derived, Aurora/Universal Blue and NixOS on measured build, update, recovery and support effort.

**Four extension types stay distinct:** Omarchy plugin (QML), OneMind connector or MCP server, application package, and ATAK plugin (ATAK SDK with tak.gov signing). A normal OneMind Android app is a third mobile deliverable. Omarchy does not add WinTAK support.

**Hermes on the workstation:**
- decide whether it attaches to an existing agent or runs a local one;
- give it an explicit identity and tools;
- know where its state lives;
- never share a copied state DB between instances;
- offline AI needs a real local model.

**Historical cluster snapshot** (Oct 19, ~02:48 EDT): 65 Argo apps. Backstage, NATS, TAK, Hermes and OpenChoreo were all Synced/Healthy, and Hermes was 2/2 Ready. This is not current health and proves no end-to-end function. TAK access is now private over the mesh; an old public endpoint is retired.

**Phone unknowns:**
- what "not tied to Google" means (no account, no Play services, no Google traffic, no Google hardware, or broader);
- country, carrier and budget;
- required ATAK plugins and radios;
- daily driver or dedicated field EUD.

**Phone candidates (October specs, unverified):**

| Candidate | Battery | Appeal | Caveat |
|---|---|---|---|
| Pixel 10 Pro XL + GrapheneOS | 5,200 mAh, sealed | Security-first, sandboxed optional Google services | Google hardware; US models reportedly eSIM-only; needs an OEM-unlockable SKU |
| Murena Fairphone Gen 6+ + /e/OS | 4,415 mAh, removable | Non-Google, repairable, preinstalled | US: T-Mobile/MVNO, Verizon excluded; ATAK unverified |
| Fairphone Gen 6 + CalyxOS / iodéOS | — | Repairable non-Google hardware | Gen 6 support does not imply Gen 6+; CalyxOS returned July 2026 with Android 17 in October; vendor firmware lag |
| Volla Plinius/Plus + Volla OS | 5,300 mAh, replaceable, IP68, microSD | Field chassis, microG optional | Carrier, update lifetime, ATAK |
| OUKITEL WP500 | 10,000 mAh, 407 g, Dimensity 8300, 12 GB, 1 TB, Android 16 | Endurance field node | First OTA "within 3 months", no multi-year update commitment; ships Gemini; no maintained de-Googled build or relock path |
| OUKITEL WP100 Titan | 33,000 mAh, 877 g | Vehicle or equipment-bag node | Heavy; software lifecycle unknown |

GrapheneOS also supports the Pixel Tablet, correcting an older note that said phones only. An ATAK crash report exists on a GrapheneOS Pixel Tablet. microG and push may still contact Google. Battery capacity is not ATAK runtime.

**Off-grid tiers:**
1. Phone alone: cached maps, GNSS, captures.
2. Site LAN: local TAK and services.
3. External radio: the **official Meshtastic ATAK plugin** for positions, chat and selected CoT. It is low bandwidth, not worldwide, and does not carry video or voice.

**Phone/ATAK checklist:**
- Settle the Google meaning, carrier, budget and role.
- Confirm SKU, bootloader, OS build, firmware lifecycle and recovery.
- Confirm a return path before purchase.
- Install trusted ATAK and every plugin.
- Test offline maps and a cold GNSS fix.
- Test screen-off background positioning.
- Test certificates and the private enrollment flow.
- Test radio, USB, video and PTT.
- Measure a real day's runtime.
- Test a reboot with no WAN or cellular.
- Test export, encrypted backup, update and recovery, and replacement-device enrollment.

**Other checklists:**
- Dell pilot (11 items): recovery path, radios and BT toggle, sleep, dock, displays, dev tools, scoped OneMind access, one read-only plugin, shell restart independence, /home restore separate from OS rollback, rebuild a second install.
- Homestead continuity: local login without a remote IdP, alarms without LLM or laptop, local maps, disconnected telemetry catch-up, expired-command rejection, revocation.
- Community install: second machine, new owner, update/uninstall, export/restore, published hardware matrix.

## 23. Still-useful bits from the outdated Build Handoff

- **16-point MVP:**
  1. Fresh-host install.
  2. Phone pairing and revocation.
  3. Separate health for Core, worker, DB and connector.
  4. Synthetic vault search with sources.
  5. Legacy cites the source note.
  6. Task capture without retry duplicates.
  7. HA reads approved entities only.
  8. One reversible approved action.
  9. Denial and expiry hold after a worker restart.
  10. Unauthorized user and revoked device are blocked.
  11. Connector timeout is reconciled.
  12. Restart resumes without repeated effects.
  13. Disable, revoke and export a package.
  14. Browser and Omarchy share action records.
  15. Clean-host restore.
  16. Export without a central service.
- **Node agent:** the only component that manages local container lifecycle. Never hand a Docker socket to a browser or plugin. Decide which tool owns each stack (OneMind, CasaOS or Portainer) and handle drift explicitly.
- **Voice:** text first, then LiveKit push-to-talk with a visible mic indicator; always-on listening is opt-in. Measure latency before promising numbers.
- **Data:** store UTC with the owner's timezone and define DST behavior for schedules. Derived indexes obey source ACLs and deletion.
- **Historical hardware:** cloud hosting, a mini PC and an R530 server. This is not a current inventory.
- **Licensing:** Omarchy MIT, CasaOS Apache-2.0, n8n embedding needs an OEM/commercial agreement, Obsidian redistribution needs review. Keep a component inventory of version, license, notices and update owner.

[redacted: sensitive] Local filesystem paths, conversation links and IDs, and personal identifiers from the source docs are omitted. The source docs contained no credentials, IPs or endpoints beyond what is described generically above.
