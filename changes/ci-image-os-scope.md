---
pr: pending
branch: ci/image-os-scope
---
CI-14: the heavy image tests run only for pull requests that change the OS. A PR that only changes what the image carries (the gateway, dashboard, design system or app catalogue) now runs one job from image.yml, the x86_64-efi first-boot smoke that proves the gateway starts on the image, next to the e2e golden path; the five image builds, the QEMU battery, the five cloud images and the installer test (about 14 hosted jobs of 1 to 2 hours) still run for OS PRs, on every push to main and on manual runs. scripts/ci-image-scope.py decides from the PR's file list and runs everything when in doubt.
