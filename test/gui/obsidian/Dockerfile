# SPDX-License-Identifier: Apache-2.0
# Bake-off test image only (issue #786): Obsidian on the OneMind desktop base. Obsidian's licence lets a person use it
# but not redistribute it, so its .deb is fetched while this image builds on a lab box and checked against the
# sha256 that GitHub publishes for the release asset. The file is never committed and this image is never pushed.
#   docker build -t onemind-bakeoff/obsidian:local --build-arg DESKTOP_BASE=ghcr.io/onemindos/bases/desktop:local test/gui/obsidian
ARG DESKTOP_BASE=ghcr.io/onemindos/bases/desktop:local
FROM ${DESKTOP_BASE}
# Release v1.15.1 (github.com/obsidianmd/obsidian-releases), asset digest read from the GitHub API on 2026-11-21. amd64 only.
ARG OBSIDIAN_VERSION=1.15.1
ARG OBSIDIAN_SHA256=f77b6dfc8c040214f2febad2b1b9b051b6a838a47b0f4fb90a31cfcb79b8fcec
USER root
RUN set -eux; \
    wget -q -O /tmp/obsidian.deb "https://github.com/obsidianmd/obsidian-releases/releases/download/v${OBSIDIAN_VERSION}/obsidian_${OBSIDIAN_VERSION}_amd64.deb"; \
    echo "${OBSIDIAN_SHA256}  /tmp/obsidian.deb" | sha256sum -c -; \
    apt-get -o Acquire::Retries=3 update; \
    apt-get -o Acquire::Retries=3 install -y --no-install-recommends /tmp/obsidian.deb; \
    apt-get clean -y; rm -rf /var/lib/apt/lists/* /tmp/obsidian.deb; \
    find / -xdev -type f -perm /6000 -exec chmod a-s {} +
COPY obsidian.conf /etc/neko/supervisord/obsidian.conf
LABEL org.opencontainers.image.title="OneMind bake-off: Obsidian (test only, never pushed)"
USER 1000:1000
