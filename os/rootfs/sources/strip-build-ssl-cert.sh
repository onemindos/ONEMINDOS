#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# ssl-cert's postinst creates these files even when policy-rc.d blocks services.
# Run in the apt install layer, so a per-build TLS identity never enters an image layer.
set -eu
root=${1:?rootfs directory}
find "$root/etc/ssl/certs" -maxdepth 1 -type l -lname 'ssl-cert-snakeoil.pem' -delete
rm -f "$root/etc/ssl/certs/ssl-cert-snakeoil.pem" "$root/etc/ssl/private/ssl-cert-snakeoil.key"
