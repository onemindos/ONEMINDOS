---
pr: pending
branch: fix-621/net-2vm
---
The 2-VM network proof (N2-6, N2-7) installs an app through the per-app proxy. It used vaultwarden, whose daily rescan of 2026-11-21 failed on 4 fixable CRITICAL findings, so the gateway correctly refused the install (409 stale_precondition) and the job failed without any network fault. The proof now installs ntfy, whose scan passes, and ONEMIND_NET_APP picks another app. The gate and the scan data are untouched.
