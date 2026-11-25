# SPDX-License-Identifier: Apache-2.0
# OneMind desktop base (apps/_bases/desktop/base.yaml). Built by sdk/tools/app-factory base-build. An app image adds
# its program as /etc/neko/supervisord/<app>.conf and ends with USER 1000:1000. The com.onemindos.* labels are inherited
# by every image built FROM this one, so the box knows it is a desktop whatever the image is called.
FROM ghcr.io/m1k1o/neko/base:3.2.0@sha256:587a3389b6b99c8999eb00a768c79205a74647c57cf5b9695a90234a0edaa446
USER root
# Upgrade every Debian package to the security archive, add a window manager, then close the doors: no setuid or
# setgid file, no Widevine (a closed Google module the arm64 upstream image downloads; paths are the defaults of
# runtime/widevine-installer in neko v3.2.0), logs to the container log, a private runtime dir for uid 1000.
RUN set -eux; \
    apt-get -o Acquire::Retries=3 update; \
    apt-get -o Acquire::Retries=3 upgrade -y --no-install-recommends; \
    apt-get -o Acquire::Retries=3 install -y --no-install-recommends openbox; \
    apt-get clean -y; rm -rf /var/lib/apt/lists/* /var/cache/apt/*; \
    rm -rf /var/lib/widevine /usr/lib64/chromium-browser/WidevineCdm /usr/lib/environment.d/*widevine*; \
    find / -xdev -type f -perm /6000 -exec chmod a-s {} +; \
    mkdir -p /etc/neko/supervisord /tmp/runtime-neko /usr/share/doc/onemind-desktop; \
    chown 1000:1000 /tmp/runtime-neko; chmod 0700 /tmp/runtime-neko
COPY supervisord.conf /etc/neko/supervisord.conf
COPY NOTICES.md /usr/share/doc/onemind-desktop/NOTICES.md
# Flathub apps (#1097): Flatpak from Debian 13, the script that runs the app the owner opened, and its supervisord program, kept disabled here.
RUN set -eux; apt-get -o Acquire::Retries=3 update; \
    apt-get -o Acquire::Retries=3 install -y --no-install-recommends flatpak; \
    apt-get clean -y; rm -rf /var/lib/apt/lists/* /var/cache/apt/*; \
    find / -xdev -type f -perm /6000 -exec chmod a-s {} +
# The box's installation (Path=/data/onemind/flatpak, mounted read-only into the session) and an empty read-only user
# directory, so no per-user override can widen an app's sandbox. Neko 3.2.0 is Debian 13 trixie (base.yaml), the same release as the box, so the pod reads the installation the box's flatpak writes.
COPY onemind-installation.conf /etc/flatpak/installations.d/onemind.conf
RUN install -d -o root -g root -m 0555 /usr/share/onemind-flatpak-user
COPY --chmod=755 onemind-desktop-session /usr/local/bin/onemind-desktop-session
COPY flatpak-session.conf /etc/neko/supervisord/flatpak-session.conf.disabled
LABEL org.opencontainers.image.title="OneMind desktop base" \
      org.opencontainers.image.source="https://github.com/onemindos/ONEMINDOS" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.base.name="ghcr.io/m1k1o/neko/base:3.2.0" \
      com.onemindos.base="desktop" \
      com.onemindos.desktop.runtime="neko"
ENV USER=neko HOME=/home/neko
USER 1000:1000
CMD ["/usr/bin/supervisord", "-c", "/etc/neko/supervisord.conf"]
