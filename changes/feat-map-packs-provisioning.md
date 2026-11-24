---
pr: 1066
branch: feat/map-packs-provisioning
---
Wire the platform's offline map pack directory and read-only image catalog paths into first boot and the installer. Keep map pack operations unavailable until the catalog can be verified. The platform provisions a retained local volume and re-reserves it for app reinstalls.
