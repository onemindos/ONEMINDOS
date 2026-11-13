---
pr: 66
branch: feat/image-line
---
Image line (HANDOFF B2, PR 66): images for x86_64, arm64, Pi 5, Jetson and the cloud, the x86_64 USB installer, first-boot and QEMU batteries in CI, and the os/ patches from the other streams applied; release workflow and downloads page (publishing refuses unsigned, waits on F-27). The QEMU harnesses now fail fast on fatal boot signs and dump the gateway journal, a smoke first boot gates the heavy image jobs, superseded PR runs are cancelled, the image builds the dashboard with ui/src, and `make local-firstboot` runs F0-F4 under KVM on a PC. Details in the PR.
