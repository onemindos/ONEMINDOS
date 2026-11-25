---
pr: pending
branch: claude/ci-image-tiers
---
Image CI is now tiered. Every run that builds images (pull requests, pushes to main and release/next, the nightly schedule, plain dispatch) builds tier 1 and tier 2 (x86_64-efi, vm, arm64-efi, the x86 installer, the proxmox cloud image, smoke and the x86_64-efi battery to T5). Tier 3 (vm-do, rpi5, aws, azure, gcp, hetzner and the vm-do and arm64-efi batteries) runs only on a manual dispatch with full=true (issue 1110). Superseded release/next push runs are cancelled. release.yml refuses a run without the tier 3 artifacts and dev-build.yml picks the newest run that has them.
