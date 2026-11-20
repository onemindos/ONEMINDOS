#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Runs once inside the template VM, as root (CI-14): installs what the x86/KVM jobs use on GitHub's
# ubuntu-24.04 runners (Docker with buildx, git, make, python3), creates the `runner` user, unpacks the
# pinned x64 Actions runner and installs the one-job service. The job VMs are clones of this template.
# Reads runner.pin from the same folder. Idempotent.
set -eu
cd "$(dirname "$0")"
. ./runner.pin
export DEBIAN_FRONTEND=noninteractive

apt-get update -qq
apt-get install -y -qq --no-install-recommends ca-certificates curl git jq make build-essential \
  python3 python3-yaml python3-venv unzip xz-utils zstd sudo docker.io docker-buildx \
  qemu-guest-agent >/dev/null
systemctl enable --now docker qemu-guest-agent >/dev/null 2>&1

id runner >/dev/null 2>&1 || useradd --create-home --shell /bin/bash runner
usermod -aG docker,kvm runner
# Passwordless sudo, as on GitHub's runners (the jobs run `sudo rm`, `sudo udevadm`, `sudo chmod`).
# Safe only because every job gets a fresh clone that is destroyed afterwards and that holds no secret.
echo 'runner ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/runner && chmod 0440 /etc/sudoers.d/runner

RH=$(getent passwd runner | cut -d: -f6)
if [ ! -x "$RH/actions-runner/run.sh" ]; then
  curl -fsSL -o /tmp/runner.tgz "https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz"
  echo "${RUNNER_SHA256}  /tmp/runner.tgz" | sha256sum -c -
  mkdir -p "$RH/actions-runner" && tar -xzf /tmp/runner.tgz -C "$RH/actions-runner" && rm -f /tmp/runner.tgz
  "$RH/actions-runner/bin/installdependencies.sh" >/dev/null
fi
chown -R runner:runner "$RH"
install -m 0755 -o root -g root run-one.sh /usr/local/bin/onemind-ci-run-one

# The one-job service: the host writes /run/onemind-ci/job (org URL, group, name, token) through the
# guest agent and starts this unit. When the job ends, the VM powers off and the host destroys it.
cat > /etc/systemd/system/onemind-ci-job.service <<'UNIT'
[Unit]
Description=OneMind CI: take exactly one job, then power off (CI-14)
After=network-online.target docker.service
Wants=network-online.target
[Service]
Type=oneshot
User=runner
ExecStart=/usr/local/bin/onemind-ci-run-one
ExecStopPost=+/usr/bin/systemctl --no-block poweroff
UNIT
systemctl daemon-reload

# A clone must look new: no machine-id, no SSH host keys, cloud-init runs again.
apt-get clean
cloud-init clean --logs >/dev/null 2>&1 || true
rm -f /etc/ssh/ssh_host_*
truncate -s 0 /etc/machine-id
echo "provisioned: runner $RUNNER_VERSION (x64), docker $(docker --version | cut -d' ' -f3 | tr -d ,)"
