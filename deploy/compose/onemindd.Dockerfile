# SPDX-License-Identifier: Apache-2.0
# onemindd for the compose dev stack (deploy/compose/compose.yaml), plus simnode (the same agent on
# the Raspberry Pi 5 and Jetson fixture trees of internal/detect) for the simulated machines.
# Build context: repo root.
# Base images are pinned by multi-arch index digest; the Debian one is os/versions.lock.yaml base.debian.
FROM docker.io/library/golang:1.26.11-trixie@sha256:fa340cb59ebeb1d53ac1cccfc334201d938fe5f3458003cccb767096d8e032b8 AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY cmd ./cmd
COPY internal ./internal
COPY deploy/compose/simnode ./deploy/compose/simnode
RUN CGO_ENABLED=0 go build -trimpath -buildvcs=false \
      -ldflags "-s -w -buildid= -X github.com/onemindos/onemindos/internal/version.Version=0.1.0+compose" \
      -o /onemindd ./cmd/onemindd \
 && CGO_ENABLED=0 go build -trimpath -buildvcs=false \
      -ldflags "-s -w -buildid= -X github.com/onemindos/onemindos/internal/version.Version=0.1.0+compose-sim" \
      -o /simnode ./deploy/compose/simnode

FROM docker.io/library/debian:trixie@sha256:9c6e381421d0f48d1b8133e573f33c185ee16cbf505eda9c4a8a4791b25ea8a6
COPY --from=build /onemindd /usr/local/bin/onemindd
COPY --from=build /simnode /usr/local/bin/simnode
COPY internal/detect/testdata/rpi5 /fixture/rpi5
COPY internal/detect/testdata/jetson /fixture/jetson
USER 65534:65534
EXPOSE 7480
ENTRYPOINT ["/usr/local/bin/onemindd"]
