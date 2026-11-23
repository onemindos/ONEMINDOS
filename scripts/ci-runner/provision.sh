#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Runs once inside a Lima VM, as root (CI-10 and CI-13, issue 299): installs the tools the local jobs
# need, creates the `runner` user and unpacks the pinned GitHub Actions runner. Idempotent.
#   ROLE=worker (default): the base VM that `cycle` clones for every job; INSTANCES runner folders
#                          (actions-runner-1, ...). The runner user gets passwordless sudo.
#   ROLE=gate:             the small gate base VM for API-only jobs (merge-gate), also cloned per job;
#                          one runner folder (actions-runner-gate-1). No sudo: these jobs only poll the
#                          GitHub API, so they get no root even inside their throwaway clone.
# Docs: docs/learning/self-hosted-runner.md.
set -eu
cd /opt/onemind-ci
. ./runner.pin
export DEBIAN_FRONTEND=noninteractive

apt-get update -qq
apt-get install -y -qq --no-install-recommends ca-certificates curl git jq make build-essential \
  python3 python3-yaml python3-venv shellcheck unzip xz-utils sudo >/dev/null

ROLE=${ROLE:-worker}
case $ROLE in worker) prefix=actions-runner- ;; gate) prefix=actions-runner-gate- ;; *) echo "ROLE must be worker or gate" >&2; exit 2 ;; esac

id runner >/dev/null 2>&1 || useradd --create-home --shell /bin/bash runner
if [ "$ROLE" = worker ]; then
  # Passwordless sudo, because the jobs we move here run `sudo apt-get`. Safe only because the VM holds no
  # secrets, shares nothing with the Mac, only trusted events reach it, and every job gets a fresh clone.
  echo 'runner ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/runner && chmod 0440 /etc/sudoers.d/runner
else
  rm -f /etc/sudoers.d/runner   # API-only jobs: no root for them
fi

if [ "$ROLE" = worker ] && ! command -v gitleaks >/dev/null; then
  curl -fsSL -o /tmp/gl.tgz "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_linux_arm64.tar.gz"
  echo "${GITLEAKS_SHA256}  /tmp/gl.tgz" | sha256sum -c -
  tar -xzf /tmp/gl.tgz -C /usr/local/bin gitleaks
  rm -f /tmp/gl.tgz
fi

# Node 22 for ci-apps (#299): Debian 13 ships Node 20, so take the pinned official build. The job also runs
# setup-node; this keeps `node` on PATH for any local job that does not.
if [ "$ROLE" = worker ] && ! node --version 2>/dev/null | grep -q "^v${NODE_VERSION}$"; then
  curl -fsSL -o /tmp/node.txz "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-arm64.tar.xz"
  echo "${NODE_SHA256}  /tmp/node.txz" | sha256sum -c -
  rm -rf /usr/local/lib/nodejs && mkdir -p /usr/local/lib/nodejs
  tar -xJf /tmp/node.txz -C /usr/local/lib/nodejs --strip-components=1
  for b in node npm npx corepack; do ln -sf "/usr/local/lib/nodejs/bin/$b" "/usr/local/bin/$b"; done
  rm -f /tmp/node.txz
fi

RH=$(getent passwd runner | cut -d: -f6)
N=${INSTANCES:-1}
if [ ! -f "$RH/runner-$RUNNER_VERSION.tgz" ]; then
  curl -fsSL -o /tmp/runner.tgz "https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-linux-arm64-${RUNNER_VERSION}.tar.gz"
  echo "${RUNNER_SHA256}  /tmp/runner.tgz" | sha256sum -c -
  rm -f "$RH"/runner-*.tgz && mv /tmp/runner.tgz "$RH/runner-$RUNNER_VERSION.tgz"
  rm -rf "$RH"/actions-runner-*
fi
i=1
while [ "$i" -le "$N" ]; do
  R=$RH/$prefix$i
  if [ ! -x "$R/run.sh" ]; then
    mkdir -p "$R" && tar -xzf "$RH/runner-$RUNNER_VERSION.tgz" -C "$R"
    "$R/bin/installdependencies.sh" >/dev/null   # the runner's own list of system libraries
  fi
  # Fail-closed fork-PR guard: the runner runs this before every job (the name must end in .sh).
  grep -v '^ACTIONS_RUNNER_HOOK_JOB_STARTED=' "$R/.env" 2>/dev/null > "$R/.env.new" || true
  echo 'ACTIONS_RUNNER_HOOK_JOB_STARTED=/usr/local/bin/onemind-ci-job-started.sh' >> "$R/.env.new"
  mv "$R/.env.new" "$R/.env"
  i=$((i + 1))
done
chown -R runner:runner "$RH"
install -m 0755 -o root -g root /opt/onemind-ci/run-one.sh /usr/local/bin/onemind-ci-run-one
install -m 0755 -o root -g root /opt/onemind-ci/job-started.sh /usr/local/bin/onemind-ci-job-started.sh
echo "provisioned ($ROLE): runner $RUNNER_VERSION x $N"
