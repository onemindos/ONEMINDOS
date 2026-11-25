---
pr: pending
branch: claude/p0-firmware-microcode-layer
---
The image now has a firmware layer for real hardware: Debian's non-free-firmware component is enabled in the pinned snapshot, and CPU microcode (Intel, AMD) plus Wi-Fi, Ethernet and graphics firmware are installed as their own build step, from a shared amd64 list plus a per-board list. Every package has a licence row, the licences ship in the image and the build info says firmware=yes or no. Building with FIRMWARE=no gives a fully open image and the build fails if closed firmware leaks in. Nothing closed-source other than firmware and microcode is added.
