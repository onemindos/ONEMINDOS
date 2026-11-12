# Build the OneMind node agent (onemindd) and CLI (onemind) as static Linux
# binaries for both architectures OneMind ships on.
#   make build   -> dist/onemindd-linux-{amd64,arm64}, dist/onemind-linux-{amd64,arm64}
#   make test    -> go vet + go test for all Go code in the repo
#   make run     -> run onemindd on this machine (Mac or Linux), API on :7480
#   make clean
#
# CGO_ENABLED=0 makes the binaries static: no libc needed on the host, so the
# same file runs on Debian 13, Raspberry Pi OS, Jetson L4T and inside the
# read-only OneMind image. -trimpath strips local build paths from the binary.

REPO    := $(abspath ../..)
DIST    := $(CURDIR)/dist
VERSION ?= 0.1.0+$(shell git -C $(REPO) rev-parse --short HEAD 2>/dev/null || echo dev)
PKG     := github.com/onemindos/onemindos
LDFLAGS := -s -w -buildid= -X $(PKG)/internal/version.Version=$(VERSION)
ARCHES  := amd64 arm64
GO      ?= go

.PHONY: build test run clean

build:
	@mkdir -p $(DIST)
	@for arch in $(ARCHES); do \
	  for bin in onemindd onemind; do \
	    echo "building $$bin linux/$$arch"; \
	    (cd $(REPO) && CGO_ENABLED=0 GOOS=linux GOARCH=$$arch $(GO) build -trimpath -ldflags '$(LDFLAGS)' \
	      -o $(DIST)/$$bin-linux-$$arch ./cmd/$$bin) || exit 1; \
	  done; \
	done
	@cd $(DIST) && shasum -a 256 onemind* > SHA256SUMS 2>/dev/null || sha256sum onemind* > SHA256SUMS
	@cat $(DIST)/SHA256SUMS

test:
	cd $(REPO) && $(GO) vet ./... && $(GO) test -race -count=1 ./...

run:
	cd $(REPO) && $(GO) run ./cmd/onemindd

clean:
	rm -rf $(DIST)
