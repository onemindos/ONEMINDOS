| scan | all unique IDs | all C+H | kernel IDs | kernel C+H | userspace IDs | userspace C+H | userspace fix states |
|---|---|---|---|---|---|---|---|
| legA-debian/grype-syft-rootfs-nok3s-onlyfixed | 361 | 132 | 361 | 132 | 0 | 0 | {} |
| legA-debian/grype-syft-rootfs-nok3s | 589 | 186 | 428 | 149 | 161 | 37 | {'not-fixed': 74, 'wont-fix': 87} |
| legA-debian/grype-syft-rootfs-onlyfixed | 362 | 133 | 361 | 132 | 1 | 1 | {'fixed': 1} |
| legA-debian/grype-syft-rootfs | 590 | 187 | 428 | 149 | 162 | 38 | {'not-fixed': 74, 'wont-fix': 87, 'fixed': 1} |
| legA2-debian-apparmor/grype-syft-rootfs-nok3s-onlyfixed | 361 | 132 | 361 | 132 | 0 | 0 | {} |
| legA2-debian-apparmor/grype-syft-rootfs-nok3s | 589 | 186 | 428 | 149 | 161 | 37 | {'not-fixed': 74, 'wont-fix': 87} |
| legA2-debian-apparmor/grype-syft-rootfs-onlyfixed | 362 | 133 | 361 | 132 | 1 | 1 | {'fixed': 1} |
| legA2-debian-apparmor/grype-syft-rootfs | 590 | 187 | 428 | 149 | 162 | 38 | {'not-fixed': 74, 'wont-fix': 87, 'fixed': 1} |
| legB-buildroot/grype-buildroot-cdx-onlyfixed | 445 | 159 | 373 | 137 | 72 | 22 | {'fixed': 72} |
| legB-buildroot/grype-buildroot-cdx-onlyfixed minus BR-resolved | 424 | 153 | 373 | 137 | 51 | 16 | {'fixed': 51} |
| legB-buildroot/grype-buildroot-cdx | 585 | 208 | 440 | 154 | 145 | 54 | {'fixed': 72, '': 73} |
| legB-buildroot/grype-buildroot-cdx minus BR-resolved | 534 | 188 | 440 | 154 | 94 | 34 | {'fixed': 51, '': 43} |
| legB-buildroot/grype-buildroot-target-cdx-onlyfixed | 426 | 154 | 373 | 137 | 53 | 17 | {'fixed': 53} |
| legB-buildroot/grype-buildroot-target-cdx-onlyfixed minus BR-resolved | 405 | 148 | 373 | 137 | 32 | 11 | {'fixed': 32} |
| legB-buildroot/grype-buildroot-target-cdx | 549 | 195 | 440 | 154 | 109 | 41 | {'fixed': 53, '': 56} |
| legB-buildroot/grype-buildroot-target-cdx minus BR-resolved | 498 | 175 | 440 | 154 | 58 | 21 | {'fixed': 32, '': 26} |
| legB-buildroot/grype-syft-rootfs-nok3s-onlyfixed | 379 | 141 | 373 | 137 | 6 | 4 | {'fixed': 6} |
| legB-buildroot/grype-syft-rootfs-nok3s | 451 | 159 | 440 | 154 | 11 | 5 | {'': 5, 'fixed': 6} |
| legB-buildroot/grype-syft-rootfs-onlyfixed | 380 | 142 | 373 | 137 | 7 | 5 | {'fixed': 7} |
| legB-buildroot/grype-syft-rootfs | 452 | 160 | 440 | 154 | 12 | 6 | {'fixed': 7, '': 5} |
| legB-buildroot-k6.12.117/grype-buildroot-cdx-onlyfixed | 433 | 154 | 361 | 132 | 72 | 22 | {'fixed': 72} |
| legB-buildroot-k6.12.117/grype-buildroot-cdx-onlyfixed minus BR-resolved | 412 | 148 | 361 | 132 | 51 | 16 | {'fixed': 51} |
| legB-buildroot-k6.12.117/grype-buildroot-cdx | 573 | 203 | 428 | 149 | 145 | 54 | {'fixed': 72, '': 73} |
| legB-buildroot-k6.12.117/grype-buildroot-cdx minus BR-resolved | 522 | 183 | 428 | 149 | 94 | 34 | {'fixed': 51, '': 43} |
| legB-buildroot-k6.12.117/grype-buildroot-target-cdx-onlyfixed | 414 | 149 | 361 | 132 | 53 | 17 | {'fixed': 53} |
| legB-buildroot-k6.12.117/grype-buildroot-target-cdx-onlyfixed minus BR-resolved | 393 | 143 | 361 | 132 | 32 | 11 | {'fixed': 32} |
| legB-buildroot-k6.12.117/grype-buildroot-target-cdx | 537 | 190 | 428 | 149 | 109 | 41 | {'fixed': 53, '': 56} |
| legB-buildroot-k6.12.117/grype-buildroot-target-cdx minus BR-resolved | 486 | 170 | 428 | 149 | 58 | 21 | {'fixed': 32, '': 26} |
| legB-buildroot-k6.12.117/grype-syft-rootfs-nok3s-onlyfixed | 367 | 136 | 361 | 132 | 6 | 4 | {'fixed': 6} |
| legB-buildroot-k6.12.117/grype-syft-rootfs-nok3s | 439 | 154 | 428 | 149 | 11 | 5 | {'': 5, 'fixed': 6} |
| legB-buildroot-k6.12.117/grype-syft-rootfs-onlyfixed | 368 | 137 | 361 | 132 | 7 | 5 | {'fixed': 7} |
| legB-buildroot-k6.12.117/grype-syft-rootfs | 440 | 155 | 428 | 149 | 12 | 6 | {'fixed': 7, '': 5} |
legA-debian: deb binary packages 139, deb source packages 85
legA2-debian-apparmor: deb binary packages 140, deb source packages 85
legB-buildroot: deb binary packages 0, deb source packages 0
legB-buildroot: Buildroot target components 27: ['busybox', 'ca-certificates', 'dbus', 'e2fsprogs', 'expat', 'gcc-final', 'glibc', 'grub2', 'iproute2', 'iptables', 'kbd', 'kmod', 'libcap', 'libmnl', 'libnftnl', 'libopenssl', 'libxcrypt', 'libzlib', 'linux', 'linux-headers', 'openssh', 'skeleton-init-common', 'skeleton-init-systemd', 'systemd', 'tzdata', 'util-linux', 'util-linux-libs']
legB-buildroot-k6.12.117: deb binary packages 0, deb source packages 0
legB-buildroot-k6.12.117: Buildroot target components 27: ['busybox', 'ca-certificates', 'dbus', 'e2fsprogs', 'expat', 'gcc-final', 'glibc', 'grub2', 'iproute2', 'iptables', 'kbd', 'kmod', 'libcap', 'libmnl', 'libnftnl', 'libopenssl', 'libxcrypt', 'libzlib', 'linux', 'linux-headers', 'openssh', 'skeleton-init-common', 'skeleton-init-systemd', 'systemd', 'tzdata', 'util-linux', 'util-linux-libs']
