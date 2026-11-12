# Updates, rollback, backups and security, as flows {#sec-flows}

> **Explain it like I'm the founder.** These were your top four worries. Here is how each one works, drawn as a picture. **Updates:** the box keeps two copies of the OS, writes the new one into the spare copy, tries it, and only keeps it if fresh checks pass; otherwise it quietly goes back. **Backups:** everything is encrypted with restic, there is a printed recovery key, and the box proves every week that it can actually restore. **Security:** each stage of boot checks the next, the data disk is encrypted from day one, and nothing physical happens on an AI's say-so without your approval.

## The update flow {#sec-update-flow}

![One update, end to end. The gate uses only signals produced after this boot.](img/update-sequence.png){width=100%}

**Why the gate matters.** After an update, Kubernetes shows the *previous* boot's "all good" status. A gate that only read that status committed an update whose Kubernetes never started, first with Rugix [C-LAB-debian-rugix-023] and again with RAUC and real k3s, in about a minute, in both runs [C-LAB-rauc-k3s-gate-008]. The fresh gate rejected it every time. Competitors commit earlier: Umbrel commits the moment its daemon starts [C-W3-036], and Home Assistant commits even after logging "unhealthy" [C-W3-025].

**Rules that came out of the labs** (`01` §4.2):

- Write the trial marker in RAUC's **pre-install** handler, because RAUC marks the slot active before post-install runs [C-LAB-rauc-k3s-gate-001].
- k3s needs bind-mounts to run on a read-only root [C-LAB-rauc-k3s-gate-004].
- Accept only **verity** bundles; a validly signed "plain" bundle was refused [C-DEC-005].
- Ship **OneMind's own RAUC** from a pinned upstream tag: Debian's 1.13 cannot install on kernels ≥ 6.19 [C-LAB-ubuntu-2604-leg-010].
- **Never auto-retry** a release that failed on this box: bootc's default timer re-staged a known-bad image in our lab [C-LAB-fedora-bootc-009].
- **The same gate passed on native Arm** (RAUC 1.15.2 + k3s for arm64, gate unchanged) [C-LAB-aarch64-gate-004].
- **Where "safe" is proven, and where not yet (revision 4).** The design is shown safe for **one box on SQLite**. A multi-server cluster rolls back through k3s's snapshot restore, which is not yet tested. Three more rules came from the refuters: app database migrations wait until the update commits; the gate gives two verdicts, **"image bad"** (final) and **"environment bad"** (for example, a core pod starved by an app: rolled back, then re-offered a limited number of times with an alert, so a hostile app cannot block a security update for ever); and after a commit, RAUC's `prevent-late-fallback` retires the old slot and security releases raise a version floor [C-LAB-secureboot-1152-010, C-REF4-DC-security-001] (`01` R4-8).
- **Sign from release 1:** offline root, 2-of-3 signers, manifest expiry with an offline grace period, revocation, and a CA rotation drill using Home Assistant's cross-signing method [C-W3-024]. Umbrel's *stable* release still runs a script supplied by its server [C-W3-034].

## The rollback states {#sec-rollback}

![Every path out of a trial boot ends on a good slot.](img/rollback-states.png){width=86%}

**Boot tries differ by board.** The x86 GRUB route allows three tries, as Home Assistant does [C-LAB-rauc-010]. The Pi 5 firmware falls back after one missed tryboot [C-LAB-rauc-1152-012], and the x86 `efi` route gives one try per boot entry [C-LAB-secureboot-rauc-003]. So an interrupted trial is **re-offered automatically** from the kept download, never for a release the gate marked bad. Stock Mender also allows only one try, so one power cut during that boot discards a good update [C-LAB-mender-013]. **Jetson** uses NVIDIA's own rootfs A/B and image-based OTA with OneMind's gate in NVIDIA's validation hook [C-W3-049, C-W3-050].

## The update engine decision (S2) {#sec-engine}

![Update engines and the other scorecards. S2 is a tie that RAUC wins on the tie-break.](img/chart-s2-s5.png){width=100%}

| | RAUC (chosen) | Mender (runner-up) | Rugix (alternative) |
|---|---|---|---|
| Used by | Home Assistant OS, ZimaOS [C-TD-casaos-zimaos-012] | umbrelOS earlier; still a legacy variant [C-W3-040] | umbrelOS 2.0 |
| Bus factor | Core mostly two engineers at one company [C-REF-W3-longevity-001] | Company-backed | One person wrote 303 of 304 commits in a year [C-W3-001] |
| Lab on our layout | Real k3s, Secure Boot, 1.15.2, native arm64: pass [C-LAB-rauc-1152-011, C-LAB-aarch64-gate-004] | Pass, with a one-try limit [C-LAB-mender-013] | Pass (x86 and arm64) [C-LAB-debian-rugix-022] |
| Deltas, phased rollout | Free | Paid [C-STEEL-updates-mender-015] | — |
| Debian/Ubuntu precedent | **None field-proven** [C-DEC-013 (UNVERIFIED: negative search)]; IronFlockOS pre-1.0 [C-CIT4-001] | umbrelOS | umbrelOS |

RAUC wins the recount 5–3 on Secure Boot, revocation, free deltas, the Pi 5 path and three boot tries. **The disk layout stays engine-neutral**, so switching engines later is an update, not a reflash (Z-03).

## The disk layout, decided now {#sec-disk}

| # | Partition | Size | Content |
|---|---|---|---|
| 1 | `onemind-esp` | 1 GiB | Recovery UKI (efi route) or first-stage GRUB |
| 2–3 | `onemind-boot-a/b` | 512 MiB each, FAT32 ESP type | Kernel + initrd now; signed UKIs later |
| 4–5 | `onemind-system-a/b` | 10 GiB each, ≥ 10% verity headroom | Read-only root |
| 6 | `onemind-recovery` | 1 GiB | Reserved |
| 7 | `onemind-data` | Rest | **LUKS2 from first boot** [C-W6-047] |

Changing a layout after boxes ship means a reflash, so it is fixed on day 1 even though Secure Boot enforcement comes later. Under emulated Secure Boot this exact layout booted signed kernels per slot, updated, rolled back, refused tampered and unsigned kernels and unlocked the data by TPM after every update [C-LAB-secureboot-rauc-020, C-LAB-secureboot-rauc-013].

## The backup flow {#sec-backup-flow}

![What is backed up, where it goes, which keys open it, and how the box proves it can restore.](img/backup-flow.png){width=100%}

- **ADR-001's `k3s etcd-snapshot` fails on a single box**, which uses SQLite, not etcd [C-W5-001]. The fix: an online SQLite backup plus the token, inside restic. In our lab a whole box restored onto a fresh VM with all 32 pods and identical data [C-LAB-k3s-footprint-restore-011].
- **Kubernetes snapshots are not encrypted**, so they always go inside restic [C-W5-013].
- **restic over Kopia:** one repository can hold several keys, so the owner gets a printed recovery key beside the box's own [C-W5-023]. restic scores 75, Kopia 66 (`01` §3.4).
- **The default storage class deletes app data when a volume claim is deleted** [C-W5-019]; OneMind uses a Retain class.
- **After a restore, Kubernetes briefly reports the old saved status** [C-W5-010], so restore checks use fresh signals too.
- **A backup counts as "verified" only with datastore-health checks** (revision 4): the k3s database inside a size budget, no compaction lag, and a k3s datastore library (kine) at or above OneMind's pinned floor (`01` §4.6). kine itself is mostly one maintainer's work [C-REF4-DC-longevity-016].
- **Nobody among the competitors proves a backup can be restored.** Your cloud cluster already does for its databases [C-W5-056]. The dashboard line "last verified restore: 3 hours ago" is the feature to lead with.

| Competitor | What it backs up | Constraint fit |
|---|---|---|
| Home Assistant | Everything, encrypted, with an "emergency kit" key | High: copy the kit |
| umbrelOS | Whole box every hour with Kopia | High |
| Olares | restic, but restores one app at a time | Medium |

## The chain of trust {#sec-security-flow}

![Each stage checks the next; the gateway is the last line between AI and the physical world.](img/chain-of-trust.png){width=86%}

- **Secure Boot route on x86:** RAUC's `efi` backend with one signed unified kernel image (UKI) per slot, proven in emulation with only OneMind's keys [C-LAB-secureboot-rauc-013]. **Anti-downgrade:** an old signed kernel booted against a newer root and was committed [C-LAB-secureboot-rauc-018], so the gate checks that kernel and root versions match, and security releases bump SBAT or rotate keys.
- **Data key:** bound to PCR 7 plus a signed PCR 11 policy; a literal PCR 7 binding alone turns every key change into a recovery prompt [C-REF-DC-technical-008]. The initrd also checks the unlocked volume's identity, against an attack that swaps in a fake encrypted volume [C-REF3-DC-security-009].
- **Factory key enrolment on every x86 box from the first shipment**, because the 2026 Microsoft CA rotation left some machines unbootable or needing physical access [C-REF3-DC-longevity-008].
- **Burning keys into a Pi 5 or a Jetson can never be undone**, so fusing is only for OneMind-built hardware (Z-15).
- **AI safety:** human approval enforced in the gateway for actuation, OS updates, installs and data export; prompt injection has no reliable prevention [C-W6-068].
- **Real time and robots:** an RT kernel exists on every flavor, but on the Pi 5 memory contention gave spikes over 1 ms under stress [C-REF-DC-technical-001], so control loops tighter than about 1 ms default to a microcontroller.
- **Public safety:** FIPS 140-3 modules, not RKE2's old 140-2 certificate [C-W6-026]. k3s crashes in Go's FIPS-only mode today [C-REF-DC-longevity-010], so the regulated tier runs RKE2 until that is fixed (Z-25).

## The law: the Cyber Resilience Act and friends {#sec-cra}

- **The EU CRA applies from 2027-12-11** [C-W6-001]. An operating system is an "important, class I" product [C-W6-011]. Annex I asks for security updates installed automatically by default, with an opt-out, "where applicable" [C-W6-008]; that is Z-02.
- **The image and the box are classified differently:** a downloadable OS image is Class I; a box is probably classified by its own core function [C-REF-W6-technical-008].
- **Art. 13(10)** lets OneMind patch only the latest version, but only where the customer can actually upgrade on hardware they own [C-REF-W6-technical-001]; a Jetson frozen on an old JetPack must be patched on its old version for the whole declared period.
- **Route:** self-assessment as free and open-source with public documentation stays primary, with a parallel notified-body pre-assessment from 2027-Q1 (`01` §4.7). The EU Machinery Regulation (from 2027-01-14) requires robots to log safety-related decisions for a year [C-W7-046]; the AI Act's high-risk duties start 2027-12-02 and 2028-08-02 [C-W6-042]. Not legal advice: counsel items are in `07-…` §13.

**Requirements served:** R-1, R-2, R-3, M-2, M-4, M-8, U-4, UX-6, AI-4, AI-5, AI-7, P-7, H-4.
