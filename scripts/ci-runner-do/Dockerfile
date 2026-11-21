# SPDX-License-Identifier: Apache-2.0
# The per-job container: a fresh copy of this image runs exactly one job and is deleted (docker run --rm).
# Built on each droplet by provision.sh. Ubuntu 24.04 like GitHub's `ubuntu-24.04`, x64, no Docker inside.
FROM ubuntu:24.04
ARG RUNNER_VERSION
ARG RUNNER_SHA256
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends \
      ca-certificates curl git jq make gcc g++ unzip zip xz-utils sudo python3 python3-yaml python3-venv \
      shellcheck openssh-client && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 1001 -s /bin/bash runner && echo 'runner ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/runner
RUN curl -fsSL -o /tmp/runner.tgz "https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz" \
 && echo "${RUNNER_SHA256}  /tmp/runner.tgz" | sha256sum -c - \
 && install -d -o runner /home/runner/actions-runner && tar -xzf /tmp/runner.tgz -C /home/runner/actions-runner \
 && /home/runner/actions-runner/bin/installdependencies.sh >/dev/null && rm -f /tmp/runner.tgz \
 && chown -R runner /home/runner/actions-runner
COPY job-started.sh /usr/local/bin/onemind-ci-job-started.sh
COPY run-one.sh /usr/local/bin/onemind-ci-run-one.sh
RUN chmod 0755 /usr/local/bin/onemind-ci-job-started.sh /usr/local/bin/onemind-ci-run-one.sh
ENV ACTIONS_RUNNER_HOOK_JOB_STARTED=/usr/local/bin/onemind-ci-job-started.sh
USER runner
WORKDIR /home/runner
ENTRYPOINT ["/usr/local/bin/onemind-ci-run-one.sh"]
