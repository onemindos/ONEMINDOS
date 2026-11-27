---
pr: pending
branch: ma/feat-os-installer-stick-built-from-the-r
---
The security build now makes the USB installer stick from the release-signed image (Refs #234, D-010, D-031): when its bundles were signed with the release keys, a new installer job copies only the public CA certificate the bundle was checked against (scripts/release/installer-payload.py), assembles the x86_64-efi disk image with it as the RAUC keyring and no signing key (make release-image, os/assemble/release-image.sh), checks the CA matches, builds the stick and runs I1-I5. A box installed from it trusts the release CA, so every later release installs as an update: install once, update forever. Without keys (dry run, and image.yml always) the stick is built exactly as before with the throwaway dev CA. The job reads no secret; the stick is a workflow artifact for now, not yet published.
