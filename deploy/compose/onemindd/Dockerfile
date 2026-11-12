# SPDX-License-Identifier: Apache-2.0
# The real onemindd node agent (cmd/onemindd), built from this checkout, as the
# Mac hub's own node in the compose demo. Build context = repo root:
#   docker build -f deploy/compose/onemindd/Dockerfile .
# Base images are pinned by digest (tag kept for humans).
FROM golang:1.26.11-alpine@sha256:ae52b5bc6ed045a9ed26ab03dc19327a802a9cc9aa8b27ed57f5c6b60579b0bb AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY cmd/ ./cmd/
COPY internal/ ./internal/
RUN CGO_ENABLED=0 go build -trimpath -ldflags '-s -w -buildid= -X github.com/onemindos/onemindos/internal/version.Version=0.1.0+compose' \
      -o /out/onemindd ./cmd/onemindd

# Static binary on distroless Debian 13: no shell, no package manager, but it has
# /etc/os-release, so the heartbeat's "os" field reads "Debian GNU/Linux 13 (trixie)".
FROM gcr.io/distroless/static-debian13:nonroot@sha256:25ac8f0c3b2334a9eb05452266bd4697864a8c8ef0ef71e5e6480d7f92868329
COPY --from=build /out/onemindd /onemindd
USER 65532:65532
EXPOSE 7480
ENTRYPOINT ["/onemindd"]
