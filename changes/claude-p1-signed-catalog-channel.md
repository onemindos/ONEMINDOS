---
pr: pending
branch: claude/p1-signed-catalog-channel
---
Signed Market catalog channel, first slice. The Market catalog can now arrive as a signed, versioned tarball (catalog/catalog-VERSION.tar.gz) in its own TUF repository with its own image-shipped root, so a new app reaches a box without an OS update. onemind catalog sync checks the channel with the same TUF client as OS updates, downloads into /data, checks the signed length and sha256, unpacks only regular files under apps/ with size caps, refuses an older version, and swaps one symlink; a tampered, mis-signed or unsafe catalog is refused and the box keeps what it has. The gateway reads the active channel catalog (ONEMIND_CATALOG_DIR) first and falls back to the apps in the image; a bad channel entry never hides the image app. A systemd timer and service ship inert until the catalog root exists. Not yet built: the release job that signs and publishes catalogs, and the scan.json freshness rule for channel apps.
