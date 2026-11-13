#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# NVIDIA's customer rootfs-validation hook. NVIDIA's validation service runs this path
# (nv-rootfs-validation-config.sh in nvidia-l4t-bootloader-utils 39.2.1,
# l4t-rootfs-validation-config.sh in nvidia-l4t-init 36.5.2) and, if it exits non-zero,
# runs `reboot`: a warm reset, which lowers the slot's retry counter. OneMind's gate decides.
exec /usr/lib/onemind/jetson/onemind-jetson gate
