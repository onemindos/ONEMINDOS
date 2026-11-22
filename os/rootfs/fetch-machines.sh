#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Pinned downloads for the optional machines layer (versions + sha256 in os/versions.lock.yaml, machines_extension).
#   fetch-machines.sh <dest-dir>
# Fetches the four KubeVirt and CDI release manifests, checks each sha256 against the pin, and writes them
# next to extension.json. Nothing is applied to a cluster here: the gateway applies them only after an owner
# approves the machines.enable action.
set -eu
DEST=$1
KUBEVIRT_VERSION=v1.9.1
CDI_VERSION=v1.66.1
KV_URL=https://github.com/kubevirt/kubevirt/releases/download/$KUBEVIRT_VERSION
CDI_URL=https://github.com/kubevirt/containerized-data-importer/releases/download/$CDI_VERSION
mkdir -p "$DEST"
get() { # name url sha256
  curl -fsSL --retry 5 --proto '=https' -o "$DEST/$1" "$2/$1"
  echo "$3  $DEST/$1" | sha256sum -c -
}
get kubevirt-operator.yaml "$KV_URL"  9ac45a436c49d32e6fc21d542bcb7600b970705297b9e6752f3ef9b0a1d292da
get kubevirt-cr.yaml       "$KV_URL"  43106136dbce3312bdbfdeae612aacafc6c12da518d233f90645b4685d84a2af
get cdi-operator.yaml      "$CDI_URL" c7d92bd1b2ee1a3952a5990000437c08d58109f31c0bd48ab6188ec27a13e224
get cdi-cr.yaml            "$CDI_URL" a497f90de608c1df26f9ee4095289373f17132d74a2042ca03e00c17c964f8a7
echo "machines extension: KubeVirt $KUBEVIRT_VERSION and CDI $CDI_VERSION manifests, sha256 verified"
