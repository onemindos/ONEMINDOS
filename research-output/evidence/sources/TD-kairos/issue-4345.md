# kairos-io/kairos#4345: kairos-agent v2.24.10 fails during UKI upgrade when target image .conf uses the "uki" key: "no efi entry in .conf file"
state: closed created: 2026-08-19T22:05:16Z closed: 2026-09-29T08:15:33Z

# Context

We build UKI provider images with CanvOS (AuroraBoot v0.26.2 / go-ukify v0.5.0). Two provider images are involved:

- **Source image (installed)**: built from an older CanvOS branch that produced the ISO the host was installed from. Ships **kairos-agent v2.24.10**.
- **Target image (day-2 k8s upgrade)**: built from the current CanvOS main. Its `trusted-boot/loader/entries/norole.conf` is written by go-ukify v0.5.0 and uses the **type-2 (`uki`)** Boot Loader Spec form:

  ```ini
  title Palette eXtended Kubernetes Edge
  sort-key norole-0
  uki /EFI/kairos/norole.efi
  profile 0
  ```

Both images are signed by the same SecureBoot db cert and carry the same TPM measured-boot key, so the SecureBoot verification step of the upgrade completes fine. The host booted successfully from the source image. Day-2 k8s upgrade to the target image failed at the boot-loader-entry rewrite step.

**Environment / versions**

| Item | Value |
|---|---|
| Kairos (base image) | v3.5.9 |
| kairos-agent | v2.24.10 |
| immucore | v0.11.3 |
| systemd-boot (in ESP, from UKI SBAT) | 256.7 |
| OS | Ubuntu 24.04.3 LTS |
| Kernel | 6.14.0-36-generic |
| Trusted-boot writer for target image | AuroraBoot v0.26.2 / go-ukify v0.5.0 |
| Source provider payload | k3s v1.34.5, kernel 6.14 |
| Target provider payload | k3s v1.35.3, kernel 7.0 |

---

# Issue

## What happens

Day-2 UKI upgrade runs. The new payload is rsynced into `/efi`, the signature on `norole.efi` verifies, then role promotion (`norole` → `active`) fails on the boot-loader-entry rewrite:

```
INF Kairos Agent version=v2.24.10
INF Boot Mode boot_mode=active_boot
INF Boot in uki mode result=true
INF Checking if OCI image <extract-path>/trusted-boot exists
INF Setting image size to 1023Mb
INF Running stage: kairos-uki-upgrade.pre …
INF installing entry: active
INF Copying <extract-path>/trusted-boot source to /efi
INF Starting rsync...
INF Finished syncing
INF Checking artifact for valid signature what=/efi/EFI/Kairos/norole.efi
INF verified subject="ACME Corp-db" what=/efi/EFI/Kairos/norole.efi
ERR installing the new artifacts as active: copying artifact set role from norole to active: no efi entry in .conf file
1 error occurred:
        * installing the new artifacts as active: copying artifact set role from norole to active: no efi entry in .conf file
```

## On-disk state after the failure

`/efi/EFI/kairos/`:

```
active.efi                                          923,451,280 B   (new UKI — role rename succeeded)
passive.efi                                         923,451,280 B   (new UKI — byte-identical to active)
norole.efi                                          923,451,280 B   (rsync source, byte-identical)
recovery_install-mode_stylus.registration.efi       999,771,536 B   (unchanged, from install-time ISO)
statereset_install-mode_stylus.registration.efi     999,771,536 B   (unchanged, from install-time ISO)
```

`/efi/loader/entries/`:

- `active.conf`, `norole.conf`, `passive.conf` — all type-2 (from the target image), **all three still literally point at `norole.efi`**:

  ```ini
  title Palette eXtended Kubernetes Edge
  sort-key norole-0
  uki /EFI/kairos/norole.efi
  profile 0
  ```

- `recovery_install-mode_stylus.registration+3.conf` — type-1 (untouched, from install-time ISO):

  ```ini
  title Palette eXtended Kubernetes Edge recovery
  efi /EFI/kairos/recovery_install-mode_stylus.registration.efi
  sort-key 0003
  ```

- `statereset_install-mode_stylus.registration+3.conf` — type-1 (untouched, from install-time ISO):

  ```ini
  title Palette eXtended Kubernetes Edge state reset (auto)
  efi /EFI/kairos/statereset_install-mode_stylus.registration.efi
  sort-key 0004
  ```

`/efi/loader/loader.conf` — the target image ships one **without** a `default` line:

```ini
timeout 5
console-mode max
editor no
secure-boot-enroll if-safe
```

## Expected

Role promotion of `norole` → `active` (and → `passive`) should copy the `.conf` and rewrite its payload-referencing line so the copied `.conf` points at the newly renamed `.efi`, regardless of whether the entry uses `efi <path>` (type-1) or `uki <path>` (type-2). Both forms are accepted by systemd-boot.

## Actual

The rewrite path fails on type-2 entries with `no efi entry in .conf file`. `active.efi` / `passive.efi` end up on disk with the new UKI content, but `active.conf` / `passive.conf` still literally say `uki /EFI/kairos/norole.efi` — a broken invariant that could later fault a subsequent upgrade if `norole.efi` is removed while the `.conf` files still reference it.

## Reproduction

1. Install a UKI host from a build produced by an older CanvOS/AuroraBoot combination whose `.conf` files use `efi <path>` (type-1). The kairos-agent baked into that base image is v2.24.10.
2. Build a target provider image with AuroraBoot v0.26.2 (go-ukify v0.5.0), which writes `.conf` files using `uki <path>` (type-2).
3. Trigger a day-2 UKI upgrade to the target image.
4. Observe the error above at role-promotion time.

Signature verification is unrelated (both images are signed by the same db cert). TPM measured-boot unseal is unrelated (same measured-boot key). The failure is purely in the `.conf` rewrite step.


## Side note

The target image's `loader.conf` also loses `default active.conf`. Combined with the misaligned `.conf` payloads above, this pushes systemd-boot into sort-key-based default selection, which happens to still boot the new UKI on our host (all three of `active/passive/norole.conf` share `sort-key norole-0` and their payload line points at `norole.efi`, which is present). If a subsequent upgrade removes `norole.efi` before the invariant is repaired, the fallback path could land on the older installer-flavour entries still on the ESP.

