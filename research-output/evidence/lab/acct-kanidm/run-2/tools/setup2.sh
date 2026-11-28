#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# UMB-ACCT-1 run-2 setup: Kanidm as a systemd host service, ONE canonical domain (the WebAuthn RP ID),
# listening on every interface so the LAN path and the (simulated) mesh path reach the same service.
# usage: setup2.sh deb <dir-with-debs> | setup2.sh ppa      (ppa = dev rehearsal only, not counted)
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
CANON=${CANON:-idm.onemind.test}   # canonical sign-in host = RP ID (PK-9 overrides it)
ALIAS=idm.mesh.test             # a second, different name (negative control)
SUBALIAS=mesh.$CANON            # a sub-domain of the RP ID (negative control)
apt-get install -y -qq openssl libnss3-tools tcpdump iproute2 curl python3-cryptography >/dev/null
if [ "$1" = deb ]; then
  D=$2; (cd "$D" && sha256sum kanidmd_*.deb kanidm_*.deb)
  apt-get install -y "$D"/kanidmd_*.deb "$D"/kanidm_*.deb 2>&1 | tail -3
else
  apt-get install -y kanidmd kanidm 2>&1 | tail -3
fi
grep -q "$CANON" /etc/hosts || echo "127.0.0.1 $CANON $ALIAS $SUBALIAS" >> /etc/hosts
sed -i "/^[0-9.]* idm.onemind.test /d" /etc/hosts 2>/dev/null; grep -q "$CANON" /etc/hosts || echo "127.0.0.1 $CANON $ALIAS $SUBALIAS" >> /etc/hosts
# our own test CA + one server certificate that is valid for all three names (so TLS never hides the WebAuthn result)
install -d -m 0700 /var/lib/private; mkdir -p /etc/kanidmd; install -d -m 0750 /var/lib/private/kanidmd
cd /etc/kanidmd
openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes -keyout ca.key -out ca.pem -days 30 -subj "/CN=OneMind lab test CA" -addext "basicConstraints=critical,CA:TRUE" -addext "keyUsage=critical,keyCertSign,cRLSign" -addext "subjectKeyIdentifier=hash" 2>/dev/null
openssl req -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes -keyout key.pem -out srv.csr -subj "/CN=$CANON" 2>/dev/null
printf "subjectAltName=DNS:$CANON,DNS:$ALIAS,DNS:$SUBALIAS,DNS:localhost,IP:127.0.0.1\nextendedKeyUsage=serverAuth\nkeyUsage=critical,digitalSignature\nbasicConstraints=CA:FALSE\nauthorityKeyIdentifier=keyid,issuer\nsubjectKeyIdentifier=hash\n" > san.ext
openssl x509 -req -in srv.csr -CA ca.pem -CAkey ca.key -CAcreateserial -out chain.pem -days 30 -extfile san.ext 2>/dev/null
cat ca.pem >> chain.pem
chmod 600 ca.key; chown root:kanidmd chain.pem key.pem; chmod 640 chain.pem key.pem; chmod 644 ca.pem
cat > /etc/kanidmd/server.toml <<TOML
# UMB-ACCT-1 run-2: one canonical domain; kanidmd listens on all interfaces (LAN + mesh paths).
version = "2"
bindaddress = "0.0.0.0:8443"
db_path = "/var/lib/private/kanidmd/kanidm.db"
tls_chain = "/etc/kanidmd/chain.pem"
tls_key = "/etc/kanidmd/key.pem"
domain = "$CANON"
origin = "https://$CANON:8443"
log_level = "info"

[online_backup]
path = "/var/lib/private/kanidmd/backups/"
schedule = "* * * * *"
versions = 3
compression = "gzip"
TOML
chown root:kanidmd /etc/kanidmd/server.toml; chmod 640 /etc/kanidmd/server.toml
mkdir -p /etc/kanidm; cp /etc/kanidmd/ca.pem /etc/kanidm/ca.pem
printf 'uri = "https://%s:8443"\nca_path = "/etc/kanidm/ca.pem"\n' "$CANON" > /etc/kanidm/config
# trust the test CA in the browser's (NSS) store
mkdir -p /root/.pki/nssdb; [ -f /root/.pki/nssdb/cert9.db ] || certutil -d sql:/root/.pki/nssdb -N --empty-password
certutil -d sql:/root/.pki/nssdb -D -n onemind-lab-ca 2>/dev/null || true
certutil -d sql:/root/.pki/nssdb -A -t "C,," -n onemind-lab-ca -i /etc/kanidmd/ca.pem
ls -l /etc/kanidmd
