#!/bin/bash
# Runs INSIDE the disposable Lima VM.
set -x
uname -a; nproc; free -g; cat /etc/debian_version
echo "== H1 nested KVM"; ls -l /dev/kvm && python3 -c "import os;fd=os.open('/dev/kvm',os.O_RDWR);print('kvm open ok');os.close(fd)" 2>&1 || sudo python3 -c "import os;fd=os.open('/dev/kvm',os.O_RDWR);print('kvm open ok (root)')"
sudo apt-get update -qq && sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq build-essential bc bison flex libssl-dev libelf-dev gcc-x86-64-linux-gnu xz-utils curl cpio dwarves python3 qemu-user-static binfmt-support >/dev/null && echo deps-ok
cd ~ && V=6.18.62
curl -fsSLO https://cdn.kernel.org/pub/linux/kernel/v6.x/linux-$V.tar.xz && sha256sum linux-$V.tar.xz && tar xf linux-$V.tar.xz
cd linux-$V
echo "== H2 native arm64"; make -s ARCH=arm64 O=../b-arm64 defconfig; S=$(date +%s); make -s ARCH=arm64 O=../b-arm64 -j$(nproc) Image modules >/dev/null 2>../arm64.err; echo "arm64 rc=$? seconds=$(( $(date +%s)-S ))"
echo "== H3 cross x86_64"; make -s ARCH=x86_64 CROSS_COMPILE=x86_64-linux-gnu- O=../b-x86 x86_64_defconfig; S=$(date +%s); make -s ARCH=x86_64 CROSS_COMPILE=x86_64-linux-gnu- O=../b-x86 -j$(nproc) bzImage modules >/dev/null 2>../x86.err; echo "x86_64 rc=$? seconds=$(( $(date +%s)-S ))"
echo "== H4 PREEMPT_RT"
for A in arm64 x86_64; do D=../b-$A; [ $A = x86_64 ] && D=../b-x86; CC=""; [ $A = x86_64 ] && CC="CROSS_COMPILE=x86_64-linux-gnu-"; scripts/config --file $D/.config -e EXPERT -e PREEMPT_RT; make -s ARCH=$A $CC O=$D olddefconfig; echo "$A: $(grep -E '^CONFIG_PREEMPT_RT=' $D/.config || echo 'PREEMPT_RT not set')"; done
echo "== H5 amd64 user-mode"; ls /proc/sys/fs/binfmt_misc/ | grep -i x86 ; echo 'int main(){return 0;}' > /tmp/t.c; x86_64-linux-gnu-gcc -static /tmp/t.c -o /tmp/t && /tmp/t && echo "x86_64 static binary ran via binfmt: $(file /tmp/t | cut -c1-80)"
