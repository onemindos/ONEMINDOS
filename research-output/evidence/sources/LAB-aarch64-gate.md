# Sources: LAB-aarch64-gate

All accessed 2026-11-11. Saved copies are in `LAB-aarch64-gate/`, with hashes in `LAB-aarch64-gate/SHA256SUMS`.

| # | Source | Type | Pin / capture | Used for |
|---|---|---|---|---|
| S1 | RAUC upstream git, tag `v1.15.2`: https://github.com/rauc/rauc (cloned inside the lab VM) | PRIMARY | tag object `f1ceebd68b4edcf681c23d6a49aa5322d483c4d9`, commit `4fb7c798d6ae412344fb8f8d310d773046af3441` printed in `../lab/aarch64-gate/logs/build-rauc.log` | The RAUC build and its hash [C-LAB-aarch64-gate-001] |
| S2 | k3s v1.37.2+k3s1 release checksum file: https://github.com/k3s-io/k3s/releases/download/v1.37.2%2Bk3s1/sha256sum-arm64.txt | PRIMARY | `LAB-aarch64-gate/k3s-v1.37.2+k3s1-sha256sum-arm64.txt` | k3s arm64 artifact pins [C-LAB-aarch64-gate-002] |
| S3 | raspberrypi/documentation@21d772e7ee022e36a8f43c3ee75e20ca359fb832 `documentation/asciidoc/computers/config_txt/boot.adoc` L20-L28 | PRIMARY | `LAB-aarch64-gate/rpi-doc-boot-kernel_2712.txt` (local clone `<lab-dir>/src/rpi_doc`) | Pi 5 default kernel `kernel_2712.img` with 16K pages [C-LAB-aarch64-gate-007] |
| S4 | Debian 13 packages (deb.debian.org trixie + trixie-security, 2026-11-11): linux-image-arm64 6.12.116-1, grub-efi-arm64-bin 2.12-9+deb13u2, qemu-efi-aarch64 2025.02-8+deb13u1, qemu-system-arm 1:10.0.13+ds-0+deb13u1 | PRIMARY | versions in `../lab/aarch64-gate/image-packages.txt`, `logs/versions.txt`; firmware hashes in `logs/firmware.sha256` | Image and VM inputs [C-LAB-aarch64-gate-003, -008] |
| S5 | Homebrew QEMU 11.1.3 and its bundled EDK2 (`edk2-stable202408`) | PRIMARY | hashes in `../lab/aarch64-gate/logs/firmware-host.sha256` | Host HVF runs [C-LAB-aarch64-gate-008] |
| S6 | Prior spikes in this repo: `../lab/rauc-1152/` (scripts, results, Pi 5 founder test, claims C-LAB-rauc-1152-010..017), `../lab/rauc-k3s-gate/` | Internal | repo | The suite this spike ports; the tryboot one-shot claim [C-LAB-rauc-1152-012] |
