<!-- SPDX-License-Identifier: Apache-2.0 -->
# Licence notices: OneMind desktop base

This image is copied into every desktop app image at `/usr/share/doc/onemind-desktop/NOTICES.md`.

| Part | Licence | Where its full text is |
|---|---|---|
| OneMind files in this image (`supervisord.conf`, `onemind-desktop-session`, `flatpak-session.conf`, `onemind-installation.conf`, this file) | Apache-2.0 | <https://github.com/onemindos/ONEMINDOS/blob/main/LICENSE> |
| Neko 3.2.0, the streaming runtime (`/usr/bin/neko`, `/var/www`, Xorg `neko_drv` and `dummy_drv` modules) | Apache-2.0 | <https://github.com/m1k1o/neko/blob/v3.2.0/LICENSE> |
| Flatpak, from Debian 13 (`/usr/bin/flatpak`, runs the Flathub apps of issue #1097; each app keeps its own licence) | LGPL-2.1-or-later | `/usr/share/doc/flatpak/copyright` in the image |
| Debian 13 packages (Xorg, PulseAudio, GStreamer, supervisor, Openbox, fonts and the rest) | each package's own licence | `/usr/share/doc/<package>/copyright` in the image |

The SBOM attached to the published image (`docker buildx imagetools inspect --format '{{ json .SBOM }}'`) lists every
package and version. Not included: Widevine. Neko's arm64 image downloads Google's closed Widevine module; this base
deletes it, so no desktop app ships it.
