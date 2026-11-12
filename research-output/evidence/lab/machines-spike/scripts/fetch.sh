#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# LAB-machines-spike T0: fetch every pinned file inside the disposable VM and check its sha256
# against the pin AND the upstream-published value. Root, inside the lab VM only.
set -euo pipefail
LAB=${LAB:?"set LAB to <lab-dir>/machines-spike"}; OUT=$LAB/run; D=/opt/machlab/dl; mkdir -p "$D" /opt/machlab/img /opt/machlab/www
exec > >(tee -a "$OUT/fetch.log") 2>&1
cd "$D"
KV=v1.9.1; CDI=v1.66.1; NOVNC=1.7.0; FED=Fedora-Cloud-Base-Generic-45-1.4.aarch64.qcow2
declare -A PIN=(
  [kubevirt-operator.yaml]=9ac45a436c49d32e6fc21d542bcb7600b970705297b9e6752f3ef9b0a1d292da
  [kubevirt-cr.yaml]=43106136dbce3312bdbfdeae612aacafc6c12da518d233f90645b4685d84a2af
  [virtctl-$KV-linux-arm64]=12a26aa4f1088594eeafb76b209e1c9752fa6a10d968b6c98364f96f6c1ecbc5
  [cdi-operator.yaml]=c7d92bd1b2ee1a3952a5990000437c08d58109f31c0bd48ab6188ec27a13e224
  [cdi-cr.yaml]=a497f90de608c1df26f9ee4095289373f17132d74a2042ca03e00c17c964f8a7
  [novnc-$NOVNC.tgz]=32689f18d6abe96bc6530828a6bd0b9ae33bda07c083a6575ed255b5a8f2e903
  [$FED]=1632acc8bc14d45b6c9596a0acc71b070d3748d1abdcf1a519be5c983bb0286c
)
get(){ [ -f "$2" ] || curl -fsSL --retry 3 -o "$2" "$1"; }
chk(){ local got; got=$(sha256sum "$1" | cut -d' ' -f1)
  [ "$got" = "${PIN[$1]}" ] || { echo "T0 FAIL hash $1 got=$got want=${PIN[$1]}"; exit 1; }; echo "sha256 OK pin $1 $got"; }
ghd(){ # upstream: GitHub release asset digest (the API's "digest" field)
  local d; d=$(curl -fsSL "https://api.github.com/repos/$1/releases/tags/$2" | jq -r --arg n "$3" '.assets[]|select(.name==$n)|.digest')
  [ "$d" = "sha256:${PIN[$3]}" ] && echo "sha256 OK upstream GitHub asset digest $3" || { echo "T0 FAIL upstream digest $3: $d"; exit 1; }; }
GH=https://github.com/kubevirt
for f in kubevirt-operator.yaml kubevirt-cr.yaml virtctl-$KV-linux-arm64; do
  get $GH/kubevirt/releases/download/$KV/$f $f; chk $f; ghd kubevirt/kubevirt $KV $f; done
for f in cdi-operator.yaml cdi-cr.yaml; do
  get $GH/containerized-data-importer/releases/download/$CDI/$f $f; chk $f; ghd kubevirt/containerized-data-importer $CDI $f; done
get https://registry.npmjs.org/@novnc/novnc/-/novnc-$NOVNC.tgz novnc-$NOVNC.tgz; chk novnc-$NOVNC.tgz
want=$(curl -fsSL https://registry.npmjs.org/@novnc/novnc/$NOVNC | jq -r .dist.integrity)
got="sha512-$(openssl dgst -sha512 -binary novnc-$NOVNC.tgz | openssl base64 -A)"
[ "$got" = "$want" ] && echo "sha512 OK upstream npm integrity novnc-$NOVNC.tgz" || { echo "T0 FAIL npm integrity $got != $want"; exit 1; }
FU=https://dl.fedoraproject.org/pub/fedora/linux/releases/45/Cloud/aarch64/images
get $FU/$FED $FED; chk $FED
get $FU/Fedora-Cloud-45-1.4-aarch64-CHECKSUM fedora-CHECKSUM
grep -q "^SHA256 ($FED) = ${PIN[$FED]}$" fedora-CHECKSUM && echo "sha256 OK upstream Fedora CHECKSUM contains pin" || { echo "T0 FAIL Fedora pin not in CHECKSUM"; exit 1; }
# Signature on the CHECKSUM file (recorded; the keyring comes from fedoraproject.org over TLS)
if curl -fsSL -o fedora.gpg https://fedoraproject.org/fedora.gpg; then
  gpg --batch --dearmor < fedora.gpg > fedora-keyring.gpg
  gpgv --keyring ./fedora-keyring.gpg fedora-CHECKSUM 2>&1 | sed -E 's/^/gpgv: /' || echo "gpgv: signature NOT verified"
else echo "gpgv: keyring download failed, signature not checked"; fi
install -m755 virtctl-$KV-linux-arm64 /usr/local/bin/virtctl; virtctl version --client 2>&1 | head -2 || true
cp -n $FED /opt/machlab/img/fedora.qcow2
rm -rf /opt/machlab/www/novnc && mkdir -p /opt/machlab/www/novnc && tar xzf novnc-$NOVNC.tgz -C /opt/machlab/www/novnc --strip-components=1
cp "$LAB/scripts/console/console.html" /opt/machlab/www/
grep -E 'image: ' kubevirt-operator.yaml cdi-operator.yaml | sort -u
echo "== T0 fetch done $(date -u +%FT%TZ)"
