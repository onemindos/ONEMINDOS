---
pr: 1112
branch: claude/s3-printing
---
Printing in the image (Step 3): CUPS with driverless IPP printing, cups-filters and ipp-usb from the pinned Debian 13 snapshot (no cups-browsed, so a printer is only ever added by the owner). cupsd runs from boot with remote administration, sharing and network browsing off; its settings, printers, spool and cache are bind mounts from /data/state so they survive a reboot and an A/B update, and /etc/cups is seeded once from the image. Port 631 is opened in the host firewall from the LAN and the mesh only, never from a public address. New first-boot checks FP1 to FP3 print a test page to a file queue, prove a non-owner cannot add a printer and that the queue survives the reboot and the update; the firewall scan gains 631 and a check that the LAN cannot reach the admin pages. Real printers must still be proven on the Dell all-in-one.
