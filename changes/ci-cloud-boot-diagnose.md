---
pr: 372
branch: ci/cloud-boot-diagnose
---
The flaky AWS cloud-boot test now leaves evidence. Now and then (twice in the last sixty image runs) an AWS run goes silent right after GRUB and the C1 first-boot step times out after 15 minutes, but the kept log held only filtered evidence lines, so the cause could not be read. On that timeout the cloud harness now asks the guest over SSH what systemd is waiting on (jobs, failed units, the first-boot, RAUC and cloud-init journals) and says whether the guest was alive at all, and CI keeps the last 400 lines of the serial console, with VM addresses masked, next to the trimmed log. The test's pass and fail rules are unchanged.
