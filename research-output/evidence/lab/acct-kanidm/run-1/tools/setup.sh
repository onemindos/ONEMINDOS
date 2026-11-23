#!/bin/bash
# Install Kanidm v1.12.0 (debs built natively on Debian 13 with kanidm_ppa_automation) as a systemd host service.
# usage: setup.sh <deb-dir>
set -euo pipefail
D=$1
export DEBIAN_FRONTEND=noninteractive
echo "+ sha256sum of the packages"; (cd "$D" && sha256sum kanidmd_*.deb kanidm_*.deb)
echo "+ apt-get install ./kanidmd ./kanidm"; apt-get install -y "$D"/kanidmd_*.deb "$D"/kanidm_*.deb 2>&1 | grep -vE '^(Get|Reading|Building|Preparing|Selecting|Hit)' | tail -15
grep -q 'idm.onemind.test' /etc/hosts || echo '127.0.0.1 idm.onemind.test' >> /etc/hosts
cat > /etc/kanidmd/server.toml <<'TOML'
# UMB-ACCT-1 lab: one fixed test domain for the whole run (ACCT-D1).
version = "2"
bindaddress = "127.0.0.1:8443"
db_path = "/var/lib/private/kanidmd/kanidm.db"
tls_chain = "/etc/kanidmd/chain.pem"
tls_key = "/etc/kanidmd/key.pem"
domain = "idm.onemind.test"
origin = "https://idm.onemind.test:8443"
log_level = "info"

[online_backup]
path = "/var/lib/private/kanidmd/backups/"
# every minute (the README needs a backup taken while the service runs)
schedule = "* * * * *"
versions = 3
compression = "gzip"
TOML
chown root:kanidmd /etc/kanidmd/server.toml; chmod 640 /etc/kanidmd/server.toml
# the state directory systemd's DynamicUser= would create on first start; cert-generate checks it exists
install -d -m 0700 /var/lib/private; install -d -m 0750 /var/lib/private/kanidmd
echo "+ kanidmd cert-generate (local test CA, not for production)"
kanidmd cert-generate -c /etc/kanidmd/server.toml > /tmp/cert-generate.log 2>&1 || { tail -5 /tmp/cert-generate.log; exit 1; }
tail -2 /tmp/cert-generate.log
test -s /etc/kanidmd/ca.pem && test -s /etc/kanidmd/chain.pem && test -s /etc/kanidmd/key.pem
chown root:kanidmd /etc/kanidmd/*.pem; chmod 640 /etc/kanidmd/*.pem; chmod 644 /etc/kanidmd/ca.pem
mkdir -p /etc/kanidm; cp /etc/kanidmd/ca.pem /etc/kanidm/ca.pem
printf 'uri = "https://idm.onemind.test:8443"\nca_path = "/etc/kanidm/ca.pem"\n' > /etc/kanidm/config
ls -l /etc/kanidmd
