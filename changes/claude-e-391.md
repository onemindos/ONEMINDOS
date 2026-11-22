---
pr: pending
branch: claude/e-391
---
Fixes the cloud first-boot hang in issue 391 (rauc.service failed, cloud-init never ran, C1 timed out on aws and hetzner). Cause, shown on a booted image: onemind-data-extend rewrote the data partition entry while udev re-read the table, so for a moment the by-partlabel and by-partuuid names of the mounted data partition vanished, systemd stopped the device units and unmounted /data and everything that needs it, about one first boot in fifty. data_extend.py now pauses udev's event queue around the table rewrite and always starts it again; 240 rewrites no longer dropped /data, where 30 were enough before. The cloud boot test also gives its test machine a diagnostic unit through SMBIOS systemd credentials (no login, image unmodified) that prints rauc, cloud-init, first-boot and mount state on the serial console when first boot is late, and CI keeps it as serial-diag.log.
