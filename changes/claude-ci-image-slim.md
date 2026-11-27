---
pr: pending
branch: claude/ci-image-slim
---
The image workflow now builds a light set on pull requests, pushes to release/next and plain manual runs (x86_64-efi and vm images, the cloud-proxmox image, first-boot smoke with boot menu lock, and the x86_64-efi battery up to T5 with its firewall check). The full set (all five boards, all five clouds, the installer, the vm-do and arm64 batteries) runs nightly at 3:17 AM ET, on pushes to main, and on a manual run with full=true. No test was weakened; only the matrix entries that run per event changed.
