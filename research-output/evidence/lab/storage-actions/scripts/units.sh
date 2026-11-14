# SPDX-License-Identifier: Apache-2.0
# Installs the lab units: the assembly stand-in and the storage service (the unit the os patch proposes).
cat > /etc/systemd/system/lab-data-assemble.service <<'U'
[Unit]
Description=Lab: assemble and mount the OneMind data set
Wants=systemd-udev-settle.service
After=systemd-udev-settle.service local-fs.target
Before=onemind-storage.service
[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/local/sbin/lab-data-assemble
[Install]
WantedBy=multi-user.target
U
cat > /etc/systemd/system/onemind-storage.service <<'U'
[Unit]
Description=OneMind storage operations (onemindd storage serve)
After=lab-data-assemble.service
[Service]
ExecStart=/usr/local/bin/onemindd storage serve --group onemind
Restart=on-failure
RestartSec=2s
[Install]
WantedBy=multi-user.target
U
getent group onemind >/dev/null || groupadd --system onemind
systemctl daemon-reload
systemctl enable lab-data-assemble.service onemind-storage.service
