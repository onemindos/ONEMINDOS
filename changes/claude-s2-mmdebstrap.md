---
pr: pending
branch: claude/s2-mmdebstrap
---
The Debian base of the OS image now comes from mmdebstrap and the pinned snapshot instead of a Docker Hub image (Step 2 of the Debian bones, PR 9, stacked on the reproducible-build PR). Debian's archive keyring checks every package, and the image no longer ships the Hub image's container leftovers: the policy-rc.d that blocks service starts, the docker-* apt files and the dpkg speedup file. The T0 build check now fails if any of them come back. The Ubuntu CI hedge still starts from its own image.
