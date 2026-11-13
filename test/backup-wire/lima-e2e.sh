#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
#
# Prove "backups switched on" on a real hub inside a throwaway Debian 13 Lima VM (D-007 base):
# developer install, back up an app with a volume and a shared-PostgreSQL database, break both,
# restore through an approved action, browse the pre-restore snapshot, turn the badge green with a
# scratch restore, undo the restore. Nothing is installed on the host.
#
#   test/backup-wire/lima-e2e.sh            # create the VM, run, keep it for inspection
#   test/backup-wire/lima-e2e.sh --delete   # delete the VM afterwards
set -euo pipefail

VM="${ONEMIND_LIMA_VM:-onemind-backup-e2e}"
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
DELETE=0
[[ "${1:-}" == "--delete" ]] && DELETE=1

if ! limactl list -q 2>/dev/null | grep -qx "$VM"; then
  limactl start --name="$VM" --tty=false --plain --cpus=4 --memory=6 --disk=30 template:debian-13
elif [[ "$(limactl list "$VM" --format '{{.Status}}')" != "Running" ]]; then
  limactl start --tty=false "$VM"
fi
case "$(limactl shell "$VM" uname -m)" in
  aarch64) ARCH=arm64 ;;
  x86_64)  ARCH=amd64 ;;
  *) echo "unsupported VM architecture" >&2; exit 1 ;;
esac

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
(cd "$REPO" && CGO_ENABLED=0 GOOS=linux GOARCH="$ARCH" go build -trimpath \
  -ldflags "-s -w -X github.com/onemindos/onemindos/internal/version.Version=0.1.0+e2e" -o "$WORK/onemindd" ./cmd/onemindd)
# Only what the hub install reads (the onemindd binary is prebuilt, the dashboard is a stub).
(cd "$REPO" && git ls-files -co --exclude-standard -- deploy core sdk/schema apps test/backup-wire \
  | grep -v -e '^core/\.venv' -e '/node_modules/' | COPYFILE_DISABLE=1 tar -czf "$WORK/repo.tgz" -T -)
limactl copy "$WORK/repo.tgz" "$VM:/tmp/repo.tgz"
limactl copy "$WORK/onemindd" "$VM:/tmp/onemindd"
# The scenario runs detached inside the VM and writes its own log, so it finishes even if this
# host session is lost; the host only follows the log until the exit line appears.
limactl shell "$VM" sudo bash -euo pipefail -c '
  rm -rf /opt/onemind-src /var/log/onemind-backup-e2e.log && mkdir -p /opt/onemind-src
  tar -xzf /tmp/repo.tgz -C /opt/onemind-src 2>/dev/null
  chmod +x /tmp/onemindd
  setsid nohup bash -c "bash /opt/onemind-src/test/backup-wire/in-vm.sh /opt/onemind-src /tmp/onemindd; echo E2E-EXIT=\$?" \
    > /var/log/onemind-backup-e2e.log 2>&1 < /dev/null &
'
seen=0
while :; do
  sleep 5
  out=$(limactl shell "$VM" sudo cat /var/log/onemind-backup-e2e.log 2>/dev/null || true)
  total=$(printf '%s\n' "$out" | wc -l)
  printf '%s\n' "$out" | tail -n +"$((seen + 1))" | grep -v '^E2E-EXIT=' || true
  seen=$total
  if rc=$(printf '%s\n' "$out" | sed -n 's/^E2E-EXIT=//p' | tail -1) && [[ -n "$rc" ]]; then break; fi
done
if [[ "$DELETE" == 1 ]]; then
  limactl delete --force "$VM"
fi
exit "$rc"
