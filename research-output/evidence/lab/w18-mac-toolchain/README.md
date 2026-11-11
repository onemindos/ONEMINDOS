# W18 spike: Mac (Apple Silicon) build path for OneMind kernels and images

Written 2026-11-10 BEFORE running.

Goal: test whether an Apple Silicon Mac can be the founder's build machine via a Linux VM (Lima, vz).
Host: Apple M5 Max, macOS 27.2, Lima 2.3.0. Disposable VM, no host mounts, no credentials.

Hypotheses and pass/fail criteria:
H1 nested KVM: with nestedVirtualization=true on vz, /dev/kvm exists in the guest. PASS if present and `kvm-ok`-style open succeeds; FAIL otherwise. (Decides whether debos KVM fakemachine and QEMU-KVM boot tests run locally.)
H2 native arm64 kernel build (Linux 6.18.y LTS, arm64 defconfig, -j$(nproc)) completes in the VM in < 30 min. PASS/FAIL on wall time.
H3 cross x86_64 kernel build (x86_64_defconfig, gcc-x86-64-linux-gnu) completes in < 30 min. PASS/FAIL on wall time.
H4 PREEMPT_RT selectable: after `scripts/config -e EXPERT -e PREEMPT_RT` + olddefconfig, .config has CONFIG_PREEMPT_RT=y on arm64 and x86_64. PASS/FAIL.
H5 x86_64 user-mode emulation for containers: an amd64 container (debian:13) runs `uname -m` = x86_64 in the arm64 VM via binfmt/QEMU user. PASS/FAIL. (Informational.)

## Results (run 2026-11-10 20:11-20:22 local, Lima vz Debian 13 arm64 guest, 10 vCPU / 16 GiB, guest kernel 6.12.115+deb13.1)
- H1 nested KVM: PASS. /dev/kvm present (crw-rw---- root:kvm); open as root OK (user needs kvm group).
- H2 native arm64 Linux 6.18.62 defconfig Image+modules: PASS, 333 s.
- H3 cross x86_64 Linux 6.18.62 x86_64_defconfig bzImage+modules (gcc-x86-64-linux-gnu): PASS, 101 s.
- H4 PREEMPT_RT selectable after enabling EXPERT: PASS on arm64 and x86_64 (CONFIG_PREEMPT_RT=y after olddefconfig).
- H5 x86_64 static binary runs via binfmt qemu-x86_64: PASS.
Kernel tarball sha256 490a7aed...7d651 matches kernel.org sha256sums.asc.
VM deleted after the run.
