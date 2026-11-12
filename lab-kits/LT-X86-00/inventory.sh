#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# LT-X86-00: run 22's inventory commands on a box booted from a Debian 13 live USB (nothing is
# installed) and print a redacted report. The serial number is never printed.
#   sudo sh inventory.sh | tee inventory.txt
run() { echo "\$ $*"; sh -c "$*" 2>&1 | sed 's/^/  /'; echo; }
{
run "lscpu | grep -E 'Model name|^CPU\(s\)'"
run "dmidecode -t system -t bios | grep -E 'Product Name|Version|Release Date'"
run "ls /sys/class/tpm; systemd-analyze has-tpm2"
run "mokutil --sb-state"
run "mokutil --db | grep -i 'UEFI CA 2023'"
run "grep MemTotal /proc/meminfo"
run "lsblk -d -o NAME,ROTA,TRAN,SIZE"
run "/lib64/ld-linux-x86-64.so.2 --help | grep -E 'x86-64-v[234]'"
run "dmesg | grep -i watchdog"
run "ls /dev/watchdog* ; cat /sys/class/watchdog/watchdog*/identity 2>/dev/null"
run "fwupdmgr get-devices 2>/dev/null | grep -E '^[^ ]|Current version' | head -40"
} | sh "$(dirname "$0")/../common/redact.sh"
