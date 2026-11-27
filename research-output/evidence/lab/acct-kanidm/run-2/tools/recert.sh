#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# TLS-only fix on the running box: re-issue the lab CA and server certificate with the extensions Python 3.13's strict verifier needs
set -e; export HOME=/root; cd /etc/kanidmd; CANON=idm.onemind.test; ALIAS=idm.mesh.test; SUBALIAS=mesh.idm.onemind.test
pkill -f chain.sh || true; pkill -f ak6.sh || true; pkill -f aklab.py || true
openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes -keyout ca.key -out ca.pem -days 30 -subj "/CN=OneMind lab test CA" -addext "basicConstraints=critical,CA:TRUE" -addext "keyUsage=critical,keyCertSign,cRLSign" -addext "subjectKeyIdentifier=hash" 2>/dev/null
openssl req -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes -keyout key.pem -out srv.csr -subj "/CN=$CANON" 2>/dev/null
printf "subjectAltName=DNS:$CANON,DNS:$ALIAS,DNS:$SUBALIAS,DNS:localhost,IP:127.0.0.1\nextendedKeyUsage=serverAuth\nkeyUsage=critical,digitalSignature\nbasicConstraints=CA:FALSE\nauthorityKeyIdentifier=keyid,issuer\nsubjectKeyIdentifier=hash\n" > san.ext
openssl x509 -req -in srv.csr -CA ca.pem -CAkey ca.key -CAcreateserial -out chain.pem -days 30 -extfile san.ext 2>/dev/null
cat ca.pem >> chain.pem; chmod 600 ca.key; chown root:kanidmd chain.pem key.pem; chmod 640 chain.pem key.pem; chmod 644 ca.pem
cp ca.pem /etc/kanidm/ca.pem
certutil -d sql:/root/.pki/nssdb -D -n onemind-lab-ca 2>/dev/null || true
certutil -d sql:/root/.pki/nssdb -A -t "C,," -n onemind-lab-ca -i /etc/kanidmd/ca.pem
systemctl restart kanidmd; sleep 4; systemctl is-active kanidmd
python3 -I -c "
import ssl; c=ssl.create_default_context(cafile='/etc/kanidm/ca.pem'); import urllib.request
print('python strict TLS verify:', urllib.request.urlopen('https://idm.onemind.test:8443/status', context=c).read())"
cd /root/aklab/run-2; mkdir -p attempt-1; mv AK-3.txt AK-4.txt AK-5.txt AK-6.txt ../chain*.out ../chain.log attempt-1/ 2>/dev/null || true
export HOME=/root; . /root/aklab/lib.sh; T=DEV; admin_relogin
for p in adult1 adult2 child1 guest1; do kanidm person delete $p -D idm_admin 2>&1 | tail -1; done
for g in onemind_owners onemind_adults onemind_children onemind_guests; do kanidm group delete $g -D idm_admin 2>&1 | tail -1; done
rm -f /root/aklab/secrets/{adult1,adult2,child1,guest1}.* 
kanidm service-account delete onemind_gateway -D idm_admin 2>&1 | tail -1 || true
kanidm group list -D idm_admin 2>/dev/null | grep -c onemind || true
