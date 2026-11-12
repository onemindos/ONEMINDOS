#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
#
# Offline bundle for deploy/install.sh --bundle (ported from PR #27). It holds everything a hub or a
# node would otherwise download or build on the box, for one CPU architecture, and a SHA256SUMS
# file that install.sh checks before it uses anything:
#
#   onemindd-linux-<arch>, onemind-linux-<arch>   node agent and CLI (static, from cmd/)
#   gateway-runtime-linux-<arch>.tar.gz           hub: Python 3.12 + the gateway venv, built for /opt/onemind
#   dashboard/                                    hub: the built dashboard
#   downloads/                                    k3s + its install.sh + airgap images, NATS (hub);
#                                                 the same pinned files install.sh fetches, same sha256
#   src/                                          deploy/, apps/, sdk/schema/ from this checkout
#   BUNDLE.txt, SHA256SUMS                        what is in it; a checksum for every other file
#
#   deploy/bundle.sh --arch amd64                 # Beelink, DigitalOcean droplet
#   deploy/bundle.sh --arch arm64                 # Raspberry Pi 5, Jetson
#   deploy/bundle.sh --arch arm64 --node-only     # a node needs only onemindd + k3s
#   options: --out DIR (default out/onemind-bundle-<arch>, gitignored), --no-airgap,
#            --go auto|local|docker (auto: the local Go if there is one, else the pinned Go container)
#
# Then copy the folder to the machine (scp -r, rsync, a USB stick) and run there:
#   sudo ./onemind-bundle-amd64/src/deploy/install.sh --role hub --bundle ./onemind-bundle-amd64
#
# Needs bash, curl, tar, git. Hub parts are built in pinned containers, so Docker is needed for a
# full bundle (for the other architecture: Docker Desktop, or QEMU binfmt on Linux). onemindd is
# built with the local Go if there is one, else in the pinned Go container.
set -euo pipefail

ARCH="" NODE_ONLY=0 OUT="" AIRGAP=1 GO_MODE=auto
while [ $# -gt 0 ]; do
  case "$1" in
    --arch) ARCH=${2:-}; shift 2 ;;
    --node-only) NODE_ONLY=1; shift ;;
    --out) OUT=${2:-}; shift 2 ;;
    --no-airgap) AIRGAP=0; shift ;;
    --go) GO_MODE=${2:-}; shift 2 ;;
    -h|--help) sed -n '4,29p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1 (see --help)" >&2; exit 2 ;;
  esac
done
case "$ARCH" in amd64|arm64) ;; *) echo "usage: $0 --arch amd64|arm64 [--node-only] [--out DIR] [--no-airgap] [--go auto|local|docker]" >&2; exit 2 ;; esac
case "$GO_MODE" in
  auto) if command -v go >/dev/null 2>&1; then GO_MODE=local; else GO_MODE=docker; fi ;;
  local|docker) ;;
  *) echo "--go must be auto, local or docker" >&2; exit 2 ;;
esac

REPO=$(cd "$(dirname "$0")/.." && pwd)
# shellcheck source=deploy/pins.env
. "$REPO/deploy/pins.env"
OUT=${OUT:-$REPO/out/onemind-bundle-$ARCH}
mkdir -p "$OUT"
OUT=$(cd "$OUT" && pwd)
WORK=$(mktemp -d "${TMPDIR:-/tmp}/onemind-bundle.XXXXXX")
trap 'rm -rf "$WORK"' EXIT

log() { printf '==> %s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
pick() { eval "printf '%s' \"\${$1_$ARCH}\""; }   # pick K3S_SHA256 -> value for this arch
sha() { if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1"; else shasum -a 256 "$1"; fi | cut -d' ' -f1; }

# fetch URL SHA256 DEST: the same pinned files install.sh downloads, checked the same way.
fetch() {
  if [ -f "$3" ] && [ "$(sha "$3")" = "$2" ]; then log "have ${3##*/}"; return 0; fi
  log "download $1"
  curl -fsSL --retry 3 --proto '=https' -o "$WORK/dl" "$1"
  [ "$(sha "$WORK/dl")" = "$2" ] || die "sha256 mismatch for $1 (expected $2)"
  mv "$WORK/dl" "$3"
}

# The build empties --out (keeping downloads/), so it must be new, empty or an earlier bundle: a
# mistyped --out such as a home or project folder is refused, never wiped.
if [ -n "$(ls -A "$OUT")" ]; then
  STRAY=$(find "$OUT" -mindepth 1 -maxdepth 1 ! -name downloads ! -name src ! -name dashboard ! -name BUNDLE.txt \
    ! -name SHA256SUMS ! -name 'onemindd-linux-*' ! -name 'onemind-linux-*' ! -name 'gateway-runtime-linux-*' \
    ! -name .DS_Store -print | head -n 1)
  if [ -n "$STRAY" ] || [ ! -d "$OUT/downloads" ]; then
    die "--out $OUT is not empty and not an earlier bundle${STRAY:+ (it holds ${STRAY##*/})}; give a new or empty folder"
  fi
fi

if [ "$NODE_ONLY" = 0 ] || [ "$GO_MODE" = docker ]; then
  if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
    die "Docker is needed (gateway runtime and dashboard, or onemindd without a local Go)"
  fi
fi

COMMIT=$(git -C "$REPO" rev-parse --short=12 HEAD 2>/dev/null || echo unknown)
if [ "$COMMIT" != unknown ] && [ -n "$(git -C "$REPO" status --porcelain -- cmd internal core dashboard deploy apps sdk/schema go.mod go.sum 2>/dev/null)" ]; then
  COMMIT="$COMMIT-dirty"
fi
VERSION="0.1.0+bundle.$COMMIT"
HOST_IDS="$(id -u):$(id -g)"

# Start clean, but keep verified downloads from an earlier run (they are re-checked below).
find "$OUT" -mindepth 1 -maxdepth 1 ! -name downloads -exec rm -rf {} +
mkdir -p "$OUT/downloads" "$OUT/src"

# ---- 1. pinned upstream downloads -----------------------------------------------------------
K3S_NAME=k3s; [ "$ARCH" = arm64 ] && K3S_NAME=k3s-arm64
fetch "$K3S_URL_BASE/$K3S_NAME" "$(pick K3S_SHA256)" "$OUT/downloads/k3s-$K3S_VERSION-$ARCH"
fetch "https://raw.githubusercontent.com/k3s-io/k3s/$K3S_INSTALL_COMMIT/install.sh" "$K3S_INSTALL_SHA256" \
  "$OUT/downloads/k3s-install-$K3S_INSTALL_COMMIT.sh"
if [ "$AIRGAP" = 1 ]; then
  fetch "$K3S_URL_BASE/k3s-airgap-images-$ARCH.tar.zst" "$(pick K3S_AIRGAP_SHA256)" "$OUT/downloads/k3s-airgap-images-$ARCH.tar.zst"
else
  rm -f "$OUT/downloads/k3s-airgap-images-$ARCH.tar.zst"
fi
NATS_TGZ="nats-server-$NATS_VERSION-linux-$ARCH.tar.gz"
if [ "$NODE_ONLY" = 0 ]; then
  fetch "https://github.com/nats-io/nats-server/releases/download/$NATS_VERSION/$NATS_TGZ" "$(pick NATS_SHA256)" "$OUT/downloads/$NATS_TGZ"
else
  rm -f "$OUT/downloads/$NATS_TGZ"
fi
# Nothing else may sit in downloads/ (install.sh refuses files SHA256SUMS does not list anyway).
find "$OUT/downloads" -type f ! -name "k3s-$K3S_VERSION-$ARCH" ! -name "k3s-install-$K3S_INSTALL_COMMIT.sh" \
  ! -name "k3s-airgap-images-$ARCH.tar.zst" ! -name "$NATS_TGZ" -delete

# ---- 2. onemindd + onemind (static) ---------------------------------------------------------
LDFLAGS="-s -w -buildid= -X github.com/onemindos/onemindos/internal/version.Version=$VERSION"
if [ "$GO_MODE" = local ]; then
  log "onemindd + onemind for linux/$ARCH with the local $(go version | awk '{print $3}')"
  for b in onemindd onemind; do
    (cd "$REPO" && CGO_ENABLED=0 GOOS=linux GOARCH="$ARCH" GOFLAGS=-mod=readonly \
      go build -trimpath -buildvcs=false -ldflags "$LDFLAGS" -o "$OUT/$b-linux-$ARCH" "./cmd/$b")
  done
  GO_USED=$(go version | awk '{print $3}')
else
  log "onemindd + onemind for linux/$ARCH in $BUNDLE_GO_IMAGE"
  docker run --rm --user "$HOST_IDS" -v "$REPO:/src:ro" -v "$OUT:/out" -w /src \
    -e CGO_ENABLED=0 -e GOOS=linux -e GOARCH="$ARCH" -e GOFLAGS="-mod=readonly -buildvcs=false" \
    -e HOME=/tmp -e GOCACHE=/tmp/go-build -e GOMODCACHE=/tmp/go-mod "$BUNDLE_GO_IMAGE" \
    sh -ec 'for b in onemindd onemind; do go build -trimpath -ldflags "$1" -o "/out/$b-linux-$2" "./cmd/$b"; done' \
    sh "$LDFLAGS" "$ARCH"
  GO_USED=${BUNDLE_GO_IMAGE%%@*}
fi

if [ "$NODE_ONLY" = 0 ]; then
  # ---- 3. gateway runtime: exactly install.sh's uv step, run for /opt/onemind in a container ----
  UA=x86_64; [ "$ARCH" = arm64 ] && UA=aarch64
  fetch "https://github.com/astral-sh/uv/releases/download/$UV_VERSION/uv-$UA-unknown-linux-gnu.tar.gz" "$(pick UV_SHA256)" "$WORK/uv.tgz"
  log "gateway runtime for linux/$ARCH (uv $UV_VERSION, core/uv.lock, Python 3.12) in $BUNDLE_DEBIAN_IMAGE"
  docker run --rm --platform "linux/$ARCH" -v "$REPO/core:/src:ro" -v "$WORK:/work" -e HOST_IDS="$HOST_IDS" \
    "$BUNDLE_DEBIAN_IMAGE" sh -ec '
      mkdir -p /tmp/uv /opt/onemind/core
      tar -xzf /work/uv.tgz -C /tmp/uv --strip-components=1
      cd /src && tar --exclude=./.venv --exclude=./data --exclude=__pycache__ --exclude=.pytest_cache -cf - . \
        | tar -C /opt/onemind/core -xf -
      cd /opt/onemind/core
      env UV_CACHE_DIR=/tmp/uv-cache UV_PYTHON_INSTALL_DIR=/opt/onemind/python UV_PROJECT_ENVIRONMENT=/opt/onemind/venv \
        UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy \
        /tmp/uv/uv sync --frozen --no-dev --no-editable --managed-python --python 3.12 --quiet
      cd / && /opt/onemind/venv/bin/python -c "import onemind_core"
      tar -C / --owner=0 --group=0 --numeric-owner -czf /work/gateway-runtime.tar.gz opt/onemind/python opt/onemind/venv
      chown "$HOST_IDS" /work/gateway-runtime.tar.gz'
  mv "$WORK/gateway-runtime.tar.gz" "$OUT/gateway-runtime-linux-$ARCH.tar.gz"

  # ---- 4. dashboard (arch-independent): install.sh's npm step, in the pinned Node container ----
  log "dashboard in $BUNDLE_NODE_IMAGE (npm ci --ignore-scripts, vite build)"
  mkdir -p "$OUT/dashboard"
  docker run --rm -v "$REPO/dashboard:/src:ro" -v "$OUT/dashboard:/out" --tmpfs /work:exec,size=2g \
    -e HOST_IDS="$HOST_IDS" -e npm_config_update_notifier=false "$BUNDLE_NODE_IMAGE" sh -ec '
      cd /src && tar --exclude=./node_modules --exclude=./dist -cf - . | tar -C /work -xf -
      cd /work && npm ci --ignore-scripts --no-audit --no-fund --loglevel=error >/dev/null && npm run build >/dev/null
      cp -R dist/. /out/ && chown -R "$HOST_IDS" /out'
  [ -f "$OUT/dashboard/index.html" ] || die "the dashboard build produced no index.html"
fi

# ---- 5. src/: what install.sh reads from a checkout (tracked + new files; gitignored ones never) --
log "src/: deploy/, apps/, sdk/schema/"
if git -C "$REPO" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  (cd "$REPO" && git ls-files -z --cached --others --exclude-standard -- deploy apps sdk/schema \
     | while IFS= read -r -d '' f; do [ -f "$f" ] && printf '%s\0' "$f"; done \
     | COPYFILE_DISABLE=1 tar --null -T - -cf -) | tar -C "$OUT/src" -xf -
else
  (cd "$REPO" && COPYFILE_DISABLE=1 tar --exclude=deploy/compose/local --exclude=__pycache__ -cf - deploy apps sdk/schema) \
    | tar -C "$OUT/src" -xf -
fi

# ---- 6. BUNDLE.txt + SHA256SUMS -------------------------------------------------------------
cat > "$OUT/BUNDLE.txt" <<EOF
# OneMind offline bundle (deploy/bundle.sh). deploy/install.sh --bundle checks SHA256SUMS first.
# Integrity only: it proves the copy is intact, not who built it. Build your own bundle.
format=1
arch=$ARCH
contents=$([ "$NODE_ONLY" = 1 ] && echo node || echo full)
commit=$COMMIT
onemindd_version=$VERSION
go=$GO_USED
k3s=$K3S_VERSION
k3s_airgap_images=$([ "$AIRGAP" = 1 ] && echo yes || echo no)
nats=$([ "$NODE_ONLY" = 1 ] && echo none || echo "$NATS_VERSION")
uv=$([ "$NODE_ONLY" = 1 ] && echo none || echo "$UV_VERSION")
built_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
EOF
(cd "$OUT" && find . -type f ! -name SHA256SUMS -print0 | LC_ALL=C sort -z \
   | if command -v sha256sum >/dev/null 2>&1; then xargs -0 sha256sum; else xargs -0 shasum -a 256; fi) > "$WORK/SHA256SUMS"
mv "$WORK/SHA256SUMS" "$OUT/SHA256SUMS"

log "bundle ready: $OUT ($(du -sh "$OUT" | cut -f1), $(wc -l < "$OUT/SHA256SUMS" | tr -d ' ') files in SHA256SUMS)"
printf '\nOn the machine (after copying the folder there):\n'
if [ "$NODE_ONLY" = 0 ]; then
  printf '    sudo ./%s/src/deploy/install.sh --role hub --bundle ./%s\n' "${OUT##*/}" "${OUT##*/}"
fi
printf '    sudo ./%s/src/deploy/install.sh --role node --hub http://<hub>:8080 --token <join token> --bundle ./%s\n' "${OUT##*/}" "${OUT##*/}"
