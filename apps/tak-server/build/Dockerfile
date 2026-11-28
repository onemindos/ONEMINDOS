# SPDX-License-Identifier: Apache-2.0
# OneMind's build of TAK Server from its public GPL-3.0 source (github.com/TAK-Product-Center/Server).
# This Dockerfile and onemind-tak-start.sh are OneMind's (Apache-2.0); they only fetch, build and start
# TAK Server, which stays a separate GPL-3.0 program. No TAK source is copied into this repo.
#
# Build (amd64, from the repo root; a Linux builder with Docker, for example the Lima guest):
#   docker buildx build --platform linux/amd64 -t ghcr.io/onemindos/tak-server:5.7-RELEASE-14-om1 apps/tak-server/build
# Status: written from the upstream build files at the pinned commit (README "Image"); not yet run.
# The first build PR runs it, publishes the image with its source, and pins the digest in
# apps/tak-server/manifests/deployment.yaml.

ARG TAK_TAG=5.7-RELEASE-14
ARG TAK_COMMIT=5187abd46d827d37cfc5708805eced197a837e49

# Builder: Java 17 JDK ("Requires Java 17", upstream README.md). eclipse-temurin is what upstream's own
# Dockerfile.takserver uses (17-jammy); this is the current 17 release on Ubuntu 24.04, pinned by digest.
FROM docker.io/library/eclipse-temurin:17.0.21.1_2-jdk-noble@sha256:db8bece667eded68935d95726450a5810930754ef91e2b9141647bf30249f33e AS build
ARG TAK_TAG
ARG TAK_COMMIT
RUN apt-get update \
 && apt-get install -y --no-install-recommends git unzip ca-certificates \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /src
# Fetch exactly the release tag and refuse anything else: the commit is the one this recipe was read at.
RUN git clone --depth 1 --branch "${TAK_TAG}" https://github.com/TAK-Product-Center/Server.git . \
 && test "$(git rev-parse HEAD)" = "${TAK_COMMIT}" \
 && git archive --format=tar.gz --prefix="takserver-${TAK_TAG}/" -o /takserver-source.tar.gz HEAD
WORKDIR /src/src
# README.md: "./gradlew clean bootWar bootJar shadowJar". buildDocker (src/takserver-package/build.gradle)
# then lays the server out as takserver-package/build/distributions/takserver-docker-<version>.zip with a
# tak/ folder (constructDockerZip in src/takserver-package/utils/utils.gradle).
RUN ./gradlew --no-daemon clean bootWar bootJar shadowJar \
 && ./gradlew --no-daemon :takserver-package:buildDocker \
 && mkdir /unpacked \
 && unzip -q takserver-package/build/distributions/takserver-docker-*.zip -d /unpacked \
 && mv /unpacked/takserver-docker-*/tak /opt/tak

# Runtime: the Java 17 JRE (it includes keytool, which the certificate scripts call) plus openssl.
FROM docker.io/library/eclipse-temurin:17.0.21.1_2-jre-noble@sha256:a9fc3bded7efe95fe0c06f3f5d7e5beea947925f729b71b61e39e0b9ddd4d7e3
ARG TAK_TAG
ARG TAK_COMMIT
LABEL org.opencontainers.image.title="TAK Server (OneMind build)" \
      org.opencontainers.image.version="${TAK_TAG}" \
      org.opencontainers.image.revision="${TAK_COMMIT}" \
      org.opencontainers.image.source="https://github.com/TAK-Product-Center/Server" \
      org.opencontainers.image.licenses="GPL-3.0 AND Apache-2.0" \
      org.opencontainers.image.description="TAK Server built from source; the complete corresponding source is in /usr/share/doc/tak-server/"
RUN apt-get update \
 && apt-get install -y --no-install-recommends openssl \
 && rm -rf /var/lib/apt/lists/* \
 && (userdel -r ubuntu 2>/dev/null || true) \
 && groupadd -g 1000 tak && useradd -u 1000 -g 1000 -M -d /opt/tak -s /usr/sbin/nologin tak
COPY --from=build /opt/tak /opt/tak
# GPL-3.0 s6: the complete corresponding source travels with every copy of the image, together with the
# licence and OneMind's build recipe (this file and the start script).
COPY --from=build /takserver-source.tar.gz /usr/share/doc/tak-server/takserver-source.tar.gz
COPY --from=build /src/LICENSE.md /usr/share/doc/tak-server/LICENSE.md
COPY Dockerfile onemind-tak-start.sh /usr/share/doc/tak-server/onemind-build/
COPY --chmod=0755 onemind-tak-start.sh /usr/local/bin/onemind-tak-start.sh
# Everything the server writes lives on the app's volume at /data (README "How it runs here"):
# certificates, CoreConfig.xml, the user file and logs. The shipped certs/ folder (scripts and config.cfg)
# is kept as certs.dist and copied to /data/certs on the first start.
RUN mv /opt/tak/certs /opt/tak/certs.dist \
 && ln -s /data/certs /opt/tak/certs \
 && ln -s /data/config/CoreConfig.xml /opt/tak/CoreConfig.xml \
 && ln -s /data/config/UserAuthenticationFile.xml /opt/tak/UserAuthenticationFile.xml \
 && rm -rf /opt/tak/logs && ln -s /data/logs /opt/tak/logs \
 && chown -R 1000:1000 /opt/tak
USER 1000:1000
WORKDIR /opt/tak
EXPOSE 8089 8443 8446
ENTRYPOINT ["/usr/local/bin/onemind-tak-start.sh"]
