---
pr: 1066
branch: feat/map-packs-provisioning
---
Wire the platform's offline map pack directory and read-only image catalog paths into first boot and the installer. A box without the signed region catalogue and key (every fresh hub until they are provisioned) still lists and removes installed packs; adding one is refused 409 `map_catalog_not_configured`, and a catalogue that is present but fails its signature check stays 503 `map_catalog_unavailable`. The platform provisions a retained local volume and re-reserves it for app reinstalls.
