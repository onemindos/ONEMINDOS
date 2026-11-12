#!/bin/bash
# W2-L1 build phase. Run as root inside the disposable lab VM (Fedora 45 aarch64, podman, qemu-kvm, edk2).
set -euxo pipefail
: "${REG:?set REG to <QEMU user-net gateway>:5000 (the gateway address is listed in the QEMU networking docs)}"
W=/root/w2; mkdir -p $W/out; cd $W
K3S=v1.37.2%2Bk3s1; SEL=v1.6.latest.1
curl -fsSLo k3s-arm64 https://github.com/k3s-io/k3s/releases/download/$K3S/k3s-arm64
curl -fsSLo k3s-sha.txt https://github.com/k3s-io/k3s/releases/download/$K3S/sha256sum-arm64.txt
grep ' k3s-arm64$' k3s-sha.txt | sha256sum -c -
curl -fsSLo k3s-selinux.noarch.rpm https://github.com/k3s-io/k3s-selinux/releases/download/$SEL/k3s-selinux-1.6-1.coreos.noarch.rpm
curl -fsSLo sel-sha.txt https://github.com/k3s-io/k3s-selinux/releases/download/$SEL/sha256sum-coreos-noarch.txt
echo "$(grep 'k3s-selinux-1.6-1.coreos.noarch.rpm' sel-sha.txt | awk '{print $1}')  k3s-selinux.noarch.rpm" | sha256sum -c -
cp files/* . && sed -i "s|__REG__|$REG|" registries-lab.conf
podman rm -f reg 2>/dev/null || true
podman run -d --name reg -p 5000:5000 docker.io/library/registry:2
podman build --pull=newer -f Containerfile.good -t localhost:5000/onemind-lab:good .
podman tag localhost:5000/onemind-lab:good ${REG}/onemind-lab:good
podman push --tls-verify=false localhost:5000/onemind-lab:good
podman build -f Containerfile.bad -t localhost:5000/onemind-lab:bad .
podman push --tls-verify=false localhost:5000/onemind-lab:bad
[ -f labkey ] || ssh-keygen -q -t ed25519 -N '' -f labkey
sed "s#__SSH_PUBKEY__#$(cat labkey.pub)#" files/config.toml > config.toml
podman run --rm --privileged --pull=newer --security-opt label=type:unconfined_t \
  -v ./config.toml:/config.toml:ro -v ./out:/output -v /var/lib/containers/storage:/var/lib/containers/storage \
  quay.io/centos-bootc/bootc-image-builder:latest --type qcow2 --rootfs xfs ${REG}/onemind-lab:good
{ podman --version; podman image inspect --format '{{.Id}} {{index .RepoDigests 0}}' quay.io/fedora/fedora-iot:45 localhost:5000/onemind-lab:good localhost:5000/onemind-lab:bad quay.io/centos-bootc/bootc-image-builder:latest docker.io/library/registry:2; sha256sum k3s-arm64 k3s-selinux.noarch.rpm; qemu-system-aarch64 --version | head -1; rpm -q edk2-aarch64; } > versions.txt
ls -la out out/*
