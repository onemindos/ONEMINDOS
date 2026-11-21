#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Runs on a droplet as root, called by `cycle` over SSH: start ONE fresh job container for slot $1.
# stdin carries one line, the JIT runner config, passed on into the container's stdin. Refuses to start unless
# the container firewall is in place (provision.sh adds it): a job must not reach the droplet's metadata
# service, the VPC, or the droplet itself. The container is deleted when the job ends or after MAX_JOB_MIN.
set -eu
slot=${1:-}
case $slot in ''|*[!0-9a-z-]*) echo "bad slot" >&2; exit 2 ;; esac
MAX_JOB_MIN=${MAX_JOB_MIN:-300}
for rule in "DOCKER-USER -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN" "DOCKER-USER -i docker0 -d 169.254.0.0/16 -j DROP" "DOCKER-USER -i docker0 -d 172.16.0.0/12 -j DROP" "INPUT -i docker0 -j DROP"; do
  # shellcheck disable=SC2086  # $rule is a fixed list of arguments
  iptables -C $rule 2>/dev/null || { echo "container firewall missing ($rule): not starting a job" >&2; exit 3; }
done
IFS= read -r cfg
name=onemind-job-$slot
docker rm -f "$name" >/dev/null 2>&1 || true
rc=0
printf '%s\n' "$cfg" | timeout -s KILL "${MAX_JOB_MIN}m" docker run --rm -i --name "$name" --pull never \
  --pids-limit 4096 --shm-size 1g --dns 1.1.1.1 --dns 9.9.9.9 onemind-ci-do:job || rc=$?
docker rm -f "$name" >/dev/null 2>&1 || true
exit "$rc"
