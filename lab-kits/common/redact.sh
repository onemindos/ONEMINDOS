#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Mask what must never reach the public repo before you paste a result (22 §2.5, brief 30 rule 9):
# serial numbers, MAC addresses, private and public IPv4 addresses, tailnet names, e-mail
# addresses, home paths and user names in prompts. Read the output once more by eye anyway.
#   sh redact.sh < raw.txt > redacted.txt
sed -E \
  -e 's/(Serial Number|UUID|Asset Tag|SKU Number)[[:space:]]*:.*/\1: <masked>/I' \
  -e 's/([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}/<mac>/g' \
  -e 's/\b(10|127)\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\b/<private-ip>/g' \
  -e 's/\b192\.168\.[0-9]{1,3}\.[0-9]{1,3}\b/<private-ip>/g' \
  -e 's/\b172\.(1[6-9]|2[0-9]|3[01])\.[0-9]{1,3}\.[0-9]{1,3}\b/<private-ip>/g' \
  -e 's/\b100\.(6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])\.[0-9]{1,3}\.[0-9]{1,3}\b/<cgnat-ip>/g' \
  -e 's/\b([0-9]{1,3}\.){3}[0-9]{1,3}\b/<ip>/g' \
  -e 's/[A-Za-z0-9.-]+\.ts\.net/<tailnet-name>/g' \
  -e 's/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,}/<email>/g' \
  -e 's#/(Users|home)/[A-Za-z0-9._-]+#/<home>#g' \
  -e 's/^[A-Za-z0-9._-]+@[A-Za-z0-9._-]+:/<user>@<host>:/'
