<!-- SPDX-License-Identifier: Apache-2.0 -->
# Lanes of the leap run

Each lane is a chain built **in order, top to bottom**: the early issues are foundations the later ones use. On GitHub every issue in a lane carries the label `leap:<lane>` (for example `leap:2-plugins`), so `gh issue list -R onemindos/ONEMINDOS -l leap:2-plugins` shows the lane.

A lane may touch only its own area (new modules and routers). Shared files take additive edits only (see [CODEX.md](CODEX.md) §4).

## Lane 1 — Run live (M-LIVE) · builder: **Claude** · label `leap:1-live`

The finish line is [#234](https://github.com/onemindos/ONEMINDOS/issues/234): OneMind running on a Mac VM, a Beelink and a cloud box, with the dashboard, phone app and real data.

1. Host executor: approved restart, shutdown, factory reset and OS install actually run on the box (rest of [#146](https://github.com/onemindos/ONEMINDOS/issues/146) and [#142](https://github.com/onemindos/ONEMINDOS/issues/142); founder decision 2026-11-18: a reset wipes the box and keeps off-box backups)
2. [#363](https://github.com/onemindos/ONEMINDOS/issues/363) tokens-file cache race · [#364](https://github.com/onemindos/ONEMINDOS/issues/364) audit-verify cache race
3. [#274](https://github.com/onemindos/ONEMINDOS/issues/274) per-node NATS accounts at first boot (PR #349)
4. [#239](https://github.com/onemindos/ONEMINDOS/issues/239) network settings screen
5. [#141](https://github.com/onemindos/ONEMINDOS/issues/141) Files and Automation pages · [#145](https://github.com/onemindos/ONEMINDOS/issues/145) restore at first run (wizard) · [#242](https://github.com/onemindos/ONEMINDOS/issues/242) local screen (PR #333)
6. [#165](https://github.com/onemindos/ONEMINDOS/issues/165) aiPolicy: schema field and model-call check · [#159](https://github.com/onemindos/ONEMINDOS/issues/159) signed audit checkpoints · [#273](https://github.com/onemindos/ONEMINDOS/issues/273) terminal on the image unit
7. [#147](https://github.com/onemindos/ONEMINDOS/issues/147) unblock the Market · [#117](https://github.com/onemindos/ONEMINDOS/issues/117) · [#173](https://github.com/onemindos/ONEMINDOS/issues/173) · [#366](https://github.com/onemindos/ONEMINDOS/issues/366) privatebin image
8. [#206](https://github.com/onemindos/ONEMINDOS/issues/206) part 2 · [#233](https://github.com/onemindos/ONEMINDOS/issues/233) one API client · [#232](https://github.com/onemindos/ONEMINDOS/issues/232) · [#284](https://github.com/onemindos/ONEMINDOS/issues/284) Tor · [#361](https://github.com/onemindos/ONEMINDOS/issues/361) benchmark · [#324](https://github.com/onemindos/ONEMINDOS/issues/324) and [#275](https://github.com/onemindos/ONEMINDOS/issues/275) CI flakes
9. [#234](https://github.com/onemindos/ONEMINDOS/issues/234) the "See OneMind" guide, written last against what really runs

## Lane 2 — Plugins · builder: **Codex** · label `leap:2-plugins` · area `plugins`

1. [#177](https://github.com/onemindos/ONEMINDOS/issues/177) plugin manifest and validator
2. [#178](https://github.com/onemindos/ONEMINDOS/issues/178) gateway plugin registry and the plugin principal
3. [#179](https://github.com/onemindos/ONEMINDOS/issues/179) widget host (sandboxed iframes, postMessage bridge)
4. [#180](https://github.com/onemindos/ONEMINDOS/issues/180) OCI pack, signing, install by digest
5. [#183](https://github.com/onemindos/ONEMINDOS/issues/183) scan gate for plugin artifacts
6. [#182](https://github.com/onemindos/ONEMINDOS/issues/182) revocation list (kill switch) and countersignature
7. [#181](https://github.com/onemindos/ONEMINDOS/issues/181) `onemind plugin init` / `dev` · [#184](https://github.com/onemindos/ONEMINDOS/issues/184) plugin test harness
8. [#185](https://github.com/onemindos/ONEMINDOS/issues/185) publish from CI, public plugin index

## Lane 3 — AI · builder: **Codex** · label `leap:3-ai` · area `ai`

All AI work sits under aiPolicy ([#165](https://github.com/onemindos/ONEMINDOS/issues/165), lane 1) and the founder rule: **AI never actuates without owner approval.**

1. [#168](https://github.com/onemindos/ONEMINDOS/issues/168) tainted input: content an agent read cannot trigger commands
2. [#166](https://github.com/onemindos/ONEMINDOS/issues/166) local model router with data-class rules
3. [#240](https://github.com/onemindos/ONEMINDOS/issues/240) model manager: catalogue, GPU-fit picks, downloads, disk budget
4. [#167](https://github.com/onemindos/ONEMINDOS/issues/167) Hermes as a gateway agent principal
5. [#169](https://github.com/onemindos/ONEMINDOS/issues/169) MCP revision 2026-07-28
6. [#128](https://github.com/onemindos/ONEMINDOS/issues/128) AI over your library (RAG), approval-gated
7. [#247](https://github.com/onemindos/ONEMINDOS/issues/247) on-box photo search · [#246](https://github.com/onemindos/ONEMINDOS/issues/246) local voice assistant (read-only intents)

## Lane 4 — Core features · builder: **Codex** · label `leap:4-core` · area `core`

1. [#204](https://github.com/onemindos/ONEMINDOS/issues/204) family roles and parental controls
2. [#237](https://github.com/onemindos/ONEMINDOS/issues/237) expiring share links
3. [#236](https://github.com/onemindos/ONEMINDOS/issues/236) single sign-on into apps (OIDC provider + forward auth)
4. [#132](https://github.com/onemindos/ONEMINDOS/issues/132) update policy knobs · [#133](https://github.com/onemindos/ONEMINDOS/issues/133) offline-aware cleanup and disk budget
5. [#171](https://github.com/onemindos/ONEMINDOS/issues/171) capability labels, "runs here / on another machine"
6. [#156](https://github.com/onemindos/ONEMINDOS/issues/156) fleet-staged updates and the release service on NATS
7. [#127](https://github.com/onemindos/ONEMINDOS/issues/127) content manager for offline libraries · [#164](https://github.com/onemindos/ONEMINDOS/issues/164) backups for offline content

## Lane 5 — OS, image and network · builder: **Claude helper (second account, another computer)** · label `leap:5-os-net` · areas `os`, `net`, `daemon`

Hardware-only parts get code and VM tests now; tests on real devices come later.

1. [#241](https://github.com/onemindos/ONEMINDOS/issues/241) scheduled snapshots and "restore a previous version"
2. [#235](https://github.com/onemindos/ONEMINDOS/issues/235) network shares: Samba per person, Time Machine
3. [#238](https://github.com/onemindos/ONEMINDOS/issues/238) bring your own domain: ACME and dynamic DNS
4. [#172](https://github.com/onemindos/ONEMINDOS/issues/172) public app exposure through the relay
5. [#205](https://github.com/onemindos/ONEMINDOS/issues/205) child internet filtering through the box's DNS
6. [#155](https://github.com/onemindos/ONEMINDOS/issues/155) offline grace and USB/LAN mirror installs
7. [#170](https://github.com/onemindos/ONEMINDOS/issues/170) leaf mode for small devices · [#200](https://github.com/onemindos/ONEMINDOS/issues/200) zero-touch onboarding (FDO)
8. [#163](https://github.com/onemindos/ONEMINDOS/issues/163) monthly restore drill · [#244](https://github.com/onemindos/ONEMINDOS/issues/244) UPS support · [#130](https://github.com/onemindos/ONEMINDOS/issues/130) GPU layer · [#283](https://github.com/onemindos/ONEMINDOS/issues/283) Ubuntu CI hedge

## Lane 6 — Apps and Market · builder: **Codex** · label `leap:6-apps` · area `apps`

1. [#126](https://github.com/onemindos/ONEMINDOS/issues/126) offline knowledge bundle (Kiwix, Kolibri, maps)
2. [#129](https://github.com/onemindos/ONEMINDOS/issues/129) Supply Depot gap apps (CyberChef, IT-Tools, …)
3. [#174](https://github.com/onemindos/ONEMINDOS/issues/174) quality tiers for apps and plugins
4. [#252](https://github.com/onemindos/ONEMINDOS/issues/252) deploy a custom app from a Git repo
5. [#245](https://github.com/onemindos/ONEMINDOS/issues/245) Frigate NVR · [#199](https://github.com/onemindos/ONEMINDOS/issues/199) MQTT 5 bridge · [#250](https://github.com/onemindos/ONEMINDOS/issues/250) Matter/Thread
6. [#176](https://github.com/onemindos/ONEMINDOS/issues/176) OneMind modules · [#201](https://github.com/onemindos/ONEMINDOS/issues/201) industrial adapters

## Founder (Zeus) — decisions and hardware that unblock lanes

| Item | Unblocks |
|---|---|
| D25 PrivateBin ([#139](https://github.com/onemindos/ONEMINDOS/issues/139)) | the dashboard "Open" button ([#286](https://github.com/onemindos/ONEMINDOS/issues/286)) |
| F-4 Apple account and APNs key ([#208](https://github.com/onemindos/ONEMINDOS/issues/208)) | iPhone push |
| Secure Boot key model ([#148](https://github.com/onemindos/ONEMINDOS/issues/148)), encrypted data ([#152](https://github.com/onemindos/ONEMINDOS/issues/152)), security updates on by default ([#154](https://github.com/onemindos/ONEMINDOS/issues/154)) | lane 5 image work; Codex can draft the design for a quick decision |
| TUF ceremony ([#153](https://github.com/onemindos/ONEMINDOS/issues/153), [#272](https://github.com/onemindos/ONEMINDOS/issues/272)) | signed releases |
| G1 metal test ([#215](https://github.com/onemindos/ONEMINDOS/issues/215)), KVM on the Beelink ([#281](https://github.com/onemindos/ONEMINDOS/issues/281)) | update and VM claims on hardware |
| Company ([#213](https://github.com/onemindos/ONEMINDOS/issues/213)) | business items |

## Not in this run

Robotics (`parked`), hardware-only field work (#131, #137, #150, #151, #197, #202, #216, #217), the business and community items (#135, #136, #158, #162, #186, #187, #195, #210–#212, #214, #219), the 10,000-device fleet test (#203) and the clients extras (#207, #248, #249). They stay in the backlog for the next run.
