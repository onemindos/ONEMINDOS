#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Runs on a new droplet as root, from `up`, with the kit copied to /opt/onemind-ci. Installs Docker, builds the
# job image (runner download checked against runner.pin) and puts the container firewall in place.
# The firewall is allow-by-internet: containers can reach the public internet and nothing else. Blocked: the
# metadata service (169.254.169.254, which holds droplet data), every private range (the VPC, other
# droplets, home networks), CGNAT, and the droplet itself (INPUT from the container bridge).
set -eu
cd /opt/onemind-ci
# shellcheck disable=SC1091
. ./runner.pin
export DEBIAN_FRONTEND=noninteractive
systemctl disable --now apt-daily.timer apt-daily-upgrade.timer 2>/dev/null || true
apt-get update -qq && apt-get install -y -qq docker.io iptables
systemctl enable --now docker
for d in 169.254.0.0/16 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 100.64.0.0/10; do
  iptables -C DOCKER-USER -d "$d" -j DROP 2>/dev/null || iptables -I DOCKER-USER 1 -d "$d" -j DROP
done
iptables -C INPUT -i docker0 -j DROP 2>/dev/null || iptables -I INPUT 1 -i docker0 -j DROP
docker build -q -t onemind-ci-do:job --build-arg "RUNNER_VERSION=$RUNNER_VERSION" --build-arg "RUNNER_SHA256=$RUNNER_SHA256" .
chmod 0755 start-job.sh
echo "provisioned: $(docker image inspect -f '{{.Id}}' onemind-ci-do:job | cut -c1-19)"
