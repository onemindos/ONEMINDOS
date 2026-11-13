<!-- SPDX-License-Identifier: Apache-2.0 -->
# Cloud images: AWS, Google Cloud, Azure, Hetzner, Proxmox (CORE-IMAGE, cloud)

**Date:** 2026-11-12 · **Status:** built by CI and QEMU-tested, all required checks PASS (§5); not yet imported into or booted on any real cloud account · **Founder request:** 2026-11-12, "images for every deployment that boot straight into OneMind" · **Serves:** D-007, BD-DO-1 (the cloud layer, first made for DigitalOcean), brief 30 B2.2, `docs/leap/core/IMAGES.md` §3 (first boot) · **Tests:** `test/qemu/CRITERIA-CLOUD.md` (C0–C6, pre-registered)

> **Explain it like I am the founder**
> A cloud does not let you plug in a USB stick: you hand it a disk file in the format it understands, it turns that into an "image", and every new machine you start is a copy of it. Each cloud wants a different file (AWS a raw disk, Google a `.tar.gz`, Azure a `.vhd`, Proxmox a `.qcow2`) and Hetzner takes no upload at all, so there we copy the disk onto a temporary server and photograph it (a "snapshot").
> Inside, all five are the same OneMind OS: read-only, A/B updates, and first boot reads the box's role (`hub`, `worker`, `leaf`) from **user-data**, the text box every cloud has when you create a machine.
> The one thing that differs per cloud is how the machine asks "who am I and what is my user-data?". That program is **cloud-init**, and each cloud answers it at a different address (a **datasource**). Each image lists its own cloud first.

## 1. Where each cloud stands

| Cloud | Board | Boots with | You upload | Datasource order | Make the image | QEMU test (§5) | Real account |
|---|---|---|---|---|---|---|---|
| AWS EC2 | `cloud-aws` | UEFI (Nitro types) | `.raw` (CI ships `.raw.xz`) | `Ec2, NoCloud, None` | `os/cloud/aws-import.sh` | C0–C4 + C6 A/B update PASS (§5) | not yet |
| Google Compute Engine | `cloud-gcp` | UEFI (`UEFI_COMPATIBLE`) | `.tar.gz` (`disk.raw` inside) | `GCE, NoCloud, None` | `os/cloud/gcp-import.sh` | C0–C4 PASS (§5) | not yet |
| Azure | `cloud-azure` | UEFI (Hyper-V generation 2) | fixed `.vhd` (CI ships `.vhd.xz`) | `Azure, NoCloud, None` | `os/cloud/azure-import.sh` | C0–C4 PASS (§5) | not yet |
| Hetzner Cloud | `cloud-hetzner` | BIOS (x86 servers) | nothing: `.raw.xz` written from rescue mode, then snapshotted | `Hetzner, NoCloud, None` | `os/cloud/hetzner-snapshot.sh` | C0–C5 PASS, wizard local-only (§5) | not yet |
| Proxmox VE | `cloud-proxmox` | UEFI (OVMF) | `.qcow2` | `NoCloud, ConfigDrive, None` | `os/cloud/proxmox-template.sh` | C0–C4 PASS (§5) | not yet |
| Any other KVM cloud (OpenStack, …) | `cloud` | UEFI | `.raw` from `make image BOARD=cloud` | generic: `NoCloud, ConfigDrive, Ec2, GCE, Azure, Hetzner, None` | — | not run | — |
| DigitalOcean | `vm-do` | BIOS | `.qcow2` | `ConfigDrive, NoCloud, None` | `IMAGES.md` §1, kit LT-DO-01 | battery T0–T5 + TC1 | not yet |

Build: `make cloud-image CLOUD=aws` (or `gcp`, `azure`, `hetzner`, `proxmox`) → `out/image-cloud-<cloud>/`, with `SHA256SUMS`, the RAUC bundle of the same version and a `-next` bundle (development keys, made and destroyed in the build). CI builds all five on every change (`image.yml`, job `cloud`) and keeps them 14 days. **Uploading is never done by CI**: the scripts run with the owner's own cloud accounts.

## 2. How they are built

- **One rootfs, five images.** `os/boards/cloud` is a normal board (amd64) whose rootfs carries the cloud layer. Each `os/boards/cloud-<name>` has no rootfs of its own (`rootfs_from: cloud`): `os/cloud/cloud-image.sh` assembles it from the `cloud` rootfs plus the board's `overlay/`, which holds one file, `/etc/cloud/cloud.cfg.d/90-onemind-datasource.cfg`. One Containerfile build serves all clouds.
- **Own RAUC `compatible` per cloud** (`onemind-cloud-aws`, …). An update bundle is a whole system slot, so it must carry its cloud's datasource file; a GCP bundle cannot be installed on an AWS instance by mistake. C6 checks that the datasource order survives an A/B update.
- **The cloud layer** (`os/boards/cloud/`, the `vm-do` pattern adapted):
  - `cloud-init` 25.1 (Debian 13), with a `cloud.cfg` that enables only modules that work on a **read-only root**: they write to `/data`, `/run`, `/home`, `/root` or to `/etc/systemd/network`, which is a tmpfs re-rendered every boot.
  - Writable spots cloud-init needs: `/var/lib/cloud` (bind mount from `/data`), `/var/lib/waagent` (Azure's provisioning file, bind mount from `/data`), `/var/lib/dhcpcd` (tmpfs: `dhcpcd` is the DHCP client cloud-init uses to reach a metadata service before the network is up).
  - `sshd`, key-only; host keys generated per instance on `/data`, none in the image. Admin user **`admin`**, locked password, passwordless `sudo` (the name `onemind` belongs to the gateway's system user).
  - `growpart` grows the `onemind-data` partition to the instance's volume and `onemind-data-grow` grows its filesystem, so a 16 GiB image fills a 40 GiB disk.
  - `onemind-firstboot` waits for `cloud-init-network.service`: on EC2, GCE, Azure and Hetzner the user-data arrives over the network, and there is no seed disk to fall back to.
  - The setup wizard (`onemind-setup`, which hands out the owner token when the box has no role) answers **only on the instance itself** (`IPAddressDeny=any`, `IPAddressAllow=localhost`): a cloud instance has a public address and Hetzner and DigitalOcean have no default firewall.
- **Layout.** The `vm-do` sizes: 16 GiB disk, 4 GiB system slots, data last (so it can grow). 16 GiB is a whole number of GiB (GCE requires it) and of MiB (Azure requires it). Hetzner's layout adds the 2 MiB BIOS boot partition for GRUB `i386-pc`.
- **Datasource order, and why** (cloud-init's `ds-identify` reads the machine's DMI data and keeps only the datasources it finds, so the order matters only when more than one could match):
  - each cloud's own datasource first; `NoCloud` next, so the same image also boots from a seed disk (the QEMU test, a rescue, a local VM); `None` last, so cloud-init still finishes when nothing is found.
  - Proxmox's cloud-init drive is NoCloud by default and ConfigDrive with `--citype configdrive2`, so both, NoCloud first.
  - DigitalOcean (`vm-do`) needs ConfigDrive **before** NoCloud (BD-DO-1).
- **Packaging** (`os/cloud/package.sh`): AWS and Hetzner `.raw` + `.raw.xz`; GCE `tar --format=oldgnu -S` of a file named `disk.raw`; Azure `qemu-img convert -O vpc -o subformat=fixed,force_size=on` (fixed VHD, exact size); Proxmox compressed `qcow2`.
- **Secure Boot is off on every cloud.** GRUB here is unsigned (BD-08: the signed UKI route is BM2). Launch with Secure Boot / Trusted Launch / Shielded VM Secure Boot **off**; the scripts say how.

Cloud format requirements above come from each provider's import documentation as known before this session (AWS VM Import/Export, GCE "Import boot disk images", Azure "Prepare a Linux VHD", Hetzner Cloud API, Proxmox `qm` manual). **UNVERIFIED this session**: they were not re-fetched, and none of the scripts has run against a real account; the first run on each cloud is the check.

## 3. Making the image on each cloud

Every script checks the file against the `SHA256SUMS` next to it, prints what it did and how to launch a hub. They need the cloud's own CLI, logged in to the owner's account.

### 3.1 AWS (`os/cloud/aws-import.sh <.raw|.raw.xz> <s3-bucket> [region]`)

Uploads to S3, `ec2 import-snapshot` (format RAW), then `ec2 register-image --boot-mode uefi --ena-support --imds-support v2.0`. Not `import-image`: that service inspects and rewrites the OS and accepts only listed distributions; a snapshot is imported byte for byte. Needs the `vmimport` service role once per account. Launch on a **Nitro** type with UEFI (for example `t3.medium`; 4 GiB RAM or more for a hub), a security group that opens 22 to you only, and `--user-data file://hub.yaml`.

### 3.2 Google Cloud (`os/cloud/gcp-import.sh <.tar.gz> <gs://bucket> [family]`)

Uploads to Cloud Storage and runs `gcloud compute images create --guest-os-features UEFI_COMPATIBLE,GVNIC,VIRTIO_SCSI_MULTIQUEUE`. Launch with `--metadata-from-file user-data=hub.yaml` and `--metadata ssh-keys=admin:<your public key>`. GCE's own guest agent is not in the image: OS Login and other agent features do not work; cloud-init installs the metadata SSH keys for `admin`.

### 3.3 Azure (`os/cloud/azure-import.sh <.vhd|.vhd.xz> <resource-group> <storage-account>`)

Uploads a page blob and runs `az image create --hyper-v-generation V2`. There is no Azure Linux agent: cloud-init provisions and reports "ready" itself, so create VMs with `--enable-agent false` (VM extensions do not work). Because `/etc/passwd` is read-only, create the VM with **`--admin-username admin`** and **SSH-key authentication** (another name or a password would need a write to `/etc`). `--security-type Standard` (Trusted Launch needs a signed boot chain). User-data goes in `--custom-data`.

### 3.4 Hetzner Cloud (`os/cloud/hetzner-snapshot.sh <https-url-of-.raw.xz> <sha256> <ssh-key-name> [location] [type]`)

Hetzner Cloud takes no image uploads. The script creates a temporary x86 server, boots it into the rescue system, downloads the `.raw.xz` there, checks its sha256, writes it to `/dev/sda`, powers off, takes a snapshot and deletes the temporary server (deleted on any exit). The `.raw.xz` must be reachable over HTTPS (a release asset or your own bucket; a CI artifact link needs a login). **Attach a firewall** (22 from you); Hetzner has none by default. Launch with `hcloud server create --image <snapshot> --user-data-from-file hub.yaml`.

### 3.5 Proxmox VE (`os/cloud/proxmox-template.sh <.qcow2> <vmid> [storage] [bridge]`, on the host)

Creates a q35 + OVMF VM without pre-enrolled Secure Boot keys, imports the disk (`import-from`, Proxmox VE 8+), adds a cloud-init drive (NoCloud), a serial console, and turns it into a template. The role goes in a `cicustom` user snippet; that snippet **replaces** Proxmox's generated user-data, so it must also carry your SSH key (`os/cloud/user-data.hub.yaml` shows where). Then `qm clone`, `qm set --cicustom user=local:snippets/onemind-hub.yaml --ipconfig0 ip=dhcp`, `qm resize … +24G`, `qm start`.

## 4. First boot on a cloud

1. **User-data** (`os/cloud/user-data.hub.yaml`): a plain `#cloud-config` with an `onemind:` mapping, as in `IMAGES.md` §3. It must not be MIME multipart or gzip, because first boot reads that mapping from the stored user-data.
2. **The owner token** (hub only) is printed once on the **serial console** and kept in `/run/onemind/owner-token` until the first reboot:
   - AWS: `aws ec2 get-console-output --latest --instance-id <id>`; GCE: `gcloud compute instances get-serial-port-output`; Azure: `az vm boot-diagnostics get-boot-log`; Proxmox: `qm terminal <vmid>`.
   - Every cloud (and the only way on Hetzner, whose console is VGA): `ssh admin@<address> sudo cat /run/onemind/owner-token` before the first reboot.
   - The serial log is readable by anyone in the cloud account allowed to read console output; keep that permission to the owner. Only the token's sha256 is stored on the box.
3. **Firewall:** open 22 to yourself. The gateway answers on 8080 (dashboard + API behind the owner token); open it to your address only, or use `ssh -L 8080:localhost:8080 admin@<address>`. NATS (4222, 7422) is user/password without TLS in v0 (`IMAGES.md` §5): open it only to your own workers and leaves.
4. **No user-data:** first boot starts the setup wizard, which answers only on the instance: `ssh -L 8080:localhost:8080 admin@<address>` and open `http://localhost:8080/`.

## 5. Test results

Criteria: `test/qemu/CRITERIA-CLOUD.md` (sha256 `7140d427…5e1d`, committed before the boards and the test existed; §6 amendment `8159f12e…10d9`, committed after the first run and before the re-run). Raw results: `test/qemu/results/cloudboot-*-2026-11-12.json`. Environment: the Lima VM on an Apple-silicon Mac (14 vCPUs, other agents' builds and tests running at the same time), amd64 guests under **TCG** (no KVM for x86 on arm64), QEMU and firmware from the arm64 tools image. Images built from commit `595cdf2` (a clean `git archive`, Debian 13 snapshot `20261111T000000Z`).

**Final run (judged by the criteria with the §6 amendment):**

| Cloud | Artifact (compressed size) | C0 artifact | C1 first boot as hub | C2 cloud-init as that cloud | C3 OneMind answers | C4 data grows, reboot keeps state | C5 wizard local-only | C6 A/B update keeps the cloud | Minutes |
|---|---|---|---|---|---|---|---|---|---|
| AWS | `.raw.xz` 583 MB (16 GiB raw) | PASS | PASS | PASS | PASS | PASS | — | **PASS** (`mark-good slot=B` after 152 s) | 14 |
| Google Cloud | `.tar.gz` 637 MB | PASS | PASS | PASS (MTU 1460) | PASS | PASS | — | — | 10 |
| Azure | `.vhd.xz` 583 MB (fixed VHD 16 GiB + 512 B) | PASS (re-run, harness fix) | PASS | PASS | PASS | PASS | — | — | 10 |
| Hetzner | `.raw.xz` 582 MB | PASS | PASS (SeaBIOS) | PASS (`eth0`, IPv6 `2001:db8::1/64`) | PASS | PASS | **PASS** | — | 13 |
| Proxmox VE | `.qcow2` 662 MB | PASS | PASS | PASS | PASS | PASS | — | — | 10 |

What the passes show, in plain words: each file is in the format its cloud imports; the image boots from that exact file with that cloud's firmware and disk controller (NVMe for AWS); cloud-init picks up the cloud's instance id, SSH key and network settings and the image lists the cloud's datasource first; the box becomes a hub from user-data alone, prints the owner token once, and serves the dashboard and API (token required); the data partition grows from 16 to 24 GiB on its own; a reboot keeps every secret; on AWS an A/B update installs, the gate commits slot B, and the cloud's datasource order and the box's identity survive it; with no role, the setup wizard answers inside the instance and **not** from outside. Every guest also had the owner token in `/run/onemind/owner-token` (reported, not judged).

**First run and harness fixes (kept on record, `cloudboot-*-run1-*.json`):**

- C2 failed on aws, gcp and hetzner for two reasons, neither in the image: the harness read `cloud-init status --wait` with `^status: done`, but `--wait` prints its progress dots and `status: done` on one line (harness bug, fixed); and the pre-registered network item asked for a default route, which QEMU's `restrict=on` network never gives (criteria flaw: under the original wording that item is **BLOCKED (environment)**; amended in criteria §6 before the re-run). The debug boot showed GCE's MTU 1460 was applied all along.
- C6 on aws: the bundle installed, but under the heaviest load of the session (rootfs build, another agent's installer test and three TCG guests) k3s took more than 300 s even on the committed slot, and the trial slot was rolled back at 305 s, as the gate is meant to do. **BLOCKED (TCG timing)** per criteria §5; it passed in the final run on a quieter host (152 s).
- Azure C0 in the final run: `qemu-img info` without `-f` reports a fixed VHD as `raw`, because the only VHD footer is at the end and QEMU never guesses that format. The harness now opens it with `-f vpc` (which fails on an invalid footer) and checks the footer cookie and disk type; C0 re-run alone on the same artifact: PASS.
- The first build ran from the shared worktree and so included other agents' uncommitted changes; the final run was rebuilt from a clean export of the branch, and also carries one image fix the first run found (`sudo: null` in place of the deprecated `sudo: false`).

**Not tested:** the real metadata services and import pipelines (§6); arm64 cloud images; `vm-do` first boot (it is the other DigitalOcean board and has its own tests).

## 6. Limits and what is not done

- **Real clouds:** no image has been imported or booted on a real account; the metadata services (EC2 IMDSv2, GCE metadata, Azure IMDS + wireserver report-ready, Hetzner metadata, Proxmox's ISO drive) were emulated with a NoCloud seed shaped like each cloud's data. The first real boot per cloud is a founder step (the scripts above).
- **amd64 only.** AWS Graviton, GCE Tau T2A, Azure Cobalt and Hetzner CAX (arm64) need a `cloud` rootfs for arm64 (`arm64-efi` has one; the per-cloud overlays would carry over).
- **AWS UEFI only:** Xen-based types (t2, m4 …) boot BIOS only and are not supported by this AMI.
- **No cloud guest agents** (Azure Linux agent, Google guest environment, SSM agent): provisioning works through cloud-init; agent features (extensions, OS Login, Session Manager) do not.
- **Secure Boot off** everywhere until the signed boot route (BD-08, BM2).
- **cloud-init ends "done" with `extended_status: degraded done`**, from two warnings that are expected here: (1) the `onemind:` key in user-data is not in cloud-init's schema (`cloud-init schema --system`: "Additional properties are not allowed ('onemind' was unexpected)"); first boot reads it anyway. Moving the settings to a key cloud-init knows is a follow-up for the first-boot design (`IMAGES.md` §3), not done here. (2) "Not unlocking blank password for existing user admin": `lock_passwd: false` is required because `/etc/shadow` is read-only; the password stays locked in the image.
- **On a slow host the gate can miss its budget:** the trial boot after an update must bring k3s up within 300 s. Under heavy TCG emulation that budget was missed (§5); on real cloud hardware k3s starts in well under that (x86_64-efi under TCG on a quiet host: about 120 s, `IMAGES.md` §6).
