---
pr: pending
branch: claude/sockets-tw19-guard
---
Host add-ons (plugin socket E3) can now only reach the read-only image as signed system or configuration extensions. systemd-sysext and systemd-confext merge disk images only when their dm-verity root hash is signed by a certificate in the read-only /usr/lib/verity.d, keep the result read-only and finish before k3s starts. A small guard runs first and refuses plain directory extensions and any certificate planted in /etc/verity.d or /run/verity.d, so one bad entry means nothing merges. Staged extensions live on the data partition and survive A/B updates, and os-release carries SYSEXT_LEVEL=1 and CONFEXT_LEVEL=1. The new QEMU test T-W19-01 (make sysextguard, criteria pre-registered in test/qemu/CRITERIA-SYSEXT.md) builds signed, wrongly signed, unsigned, naked and directory extensions with throwaway keys inside the guest, plays a one-time root, reboots and switches slots. Its result decides founder decision Z-22 for issue #186.
