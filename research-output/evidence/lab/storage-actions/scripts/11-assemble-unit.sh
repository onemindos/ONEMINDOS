# SPDX-License-Identifier: Apache-2.0
# Phase 11: the boot assembly becomes the shipped code. The lab unit runs
# "onemindd storage assemble" (the os patch's onemind-data-assemble.service) instead of assemble.sh;
# --key-file stands in for the owner typing the recovery key, --mount-normal for /etc/fstab's data.mount.
sed -i 's#^ExecStart=.*#ExecStart=/usr/local/bin/onemindd storage assemble --key-file /root/lab/recovery.key --mount-normal --wait 20s#' /etc/systemd/system/lab-data-assemble.service
systemctl daemon-reload
grep ExecStart /etc/systemd/system/lab-data-assemble.service
