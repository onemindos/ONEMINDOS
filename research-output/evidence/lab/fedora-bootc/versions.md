# Pinned versions and hashes (LAB-fedora-bootc)

The authoritative table is README §"Pinned versions and hashes"; this file restates it so every lab folder has the same layout. Compiled 2026-11-11 by the HYG agent; nothing was re-run.

| Item | Version / pin |
|---|---|
| Host | Apple M5 Max, macOS 27.2, Lima 2.3.0, QEMU 11.1.3 (Homebrew) |
| Base image | `quay.io/fedora/fedora-bootc@sha256:a2e3dea74c6ba8b9c8dbdfd1a2e63fccc1d446cfce20e1efbeb567b63e9e940d` (tag 44, 44.20261110.0) |
| In-image packages | bootc 1.17.1, kernel 7.3.3-200.fc44, ostree 2026.4, bootupd 0.3.2, grub2-efi-aa64 2.12-66.fc44, systemd 259.10, greenboot 0.16.4-0.fc44 |
| Disk builder | `quay.io/centos-bootc/bootc-image-builder@sha256:dab86ee6b46dcade411b37f4e70b07d93b6a06da0dbfec6fe89247a220e0d9f8` |
| Lab registry | `docker.io/library/registry@sha256:a3d8aaa63ed8681a604f1dea0aa03f100d5895b6a58ace528858a7b332415373` |
| Build VM | Lima `template:fedora-44`, vz, aarch64, 8 vCPU / 16 GiB, podman 5.8.1 |
| Test VM | QEMU 11.1.3 `-machine virt -accel hvf`, 4 vCPU / 4 GiB, edk2-aarch64 |
| v1 disk | qcow2 sha256 `0650c58fb68cf67431f279b9e61ac20685fd11429a110b820019227e51ad6517` (deleted after the run) |
| Registry digests | see README (v1, v2, v3-bad, alt, v4-big ×4) |

`SHA256SUMS` hashes the committed scripts and logs. No run-time hash file of the scripts was written, and the run-time folder holds only the build output and VM state.

**Masking (2026-11-11, critic pass-3 P3-10):** `README.md` (How to rerun block), `scripts/lab.sh` and `scripts/run-vm.sh` no longer name the lab host's folder layout. The README says `<lab-dir>/fedora-bootc`; the scripts now stop with an error unless `LAB` is set (`${LAB:?…}`) instead of defaulting to a host path. `SHA256SUMS` carries the masked hashes; the original hashes and the unmasked originals (commit `414d60a`) are listed in `../PREREGISTRATION.md` §"Masking log". Nothing was re-run.
