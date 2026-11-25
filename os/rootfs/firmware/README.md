# Firmware layer

Real computers need small closed programs to work: CPU microcode (fixes the CPU's own security bugs),
Wi-Fi, Ethernet and graphics firmware. Debian keeps them in a separate archive component,
`non-free-firmware`. The founder decided (2026-11-21) the image may include them. Nothing else
closed-source ships.

How it works
- `os/rootfs/sources/configure-apt.sh debian <snapshot> <yes|no>` turns the component on or off in the
  pinned snapshot (same date as everything else).
- `debian-amd64.txt` is the shared list. A board adds hardware with `os/boards/<board>/packages-firmware-debian.txt`.
  To support a new chip, add its package to a list and give it a row in `licences.txt`.
- `resolve.sh` prints the list for a build and refuses any package without a licence row.
- The Containerfile installs that list as its own step, so the firmware shows up as its own set of
  packages in `usr/lib/onemind/packages.txt` and in the SBOM, and `usr/lib/onemind/firmware-licences.txt`
  records the licences next to the image's `build-info.txt` line `firmware=yes|no`.

Fully open image (no closed firmware): `make image FIRMWARE=no` (build arg `FIRMWARE=no`). The component is
not enabled and nothing from the lists is installed; the build fails if a firmware package slipped in.
Hardware that needs firmware will not work on that image (Wi-Fi, some GPUs); wired networking on open
drivers still does.

Versions: the packages are pinned by the snapshot date (`os/versions.lock.yaml` `image_firmware`), the same way
every other Debian package is. The installer stick (`os/boards/installer-x86_64`) is a follow-up.
