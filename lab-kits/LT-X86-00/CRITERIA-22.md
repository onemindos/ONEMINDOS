<!-- Copied verbatim from research-output/22-HARDWARE-LAB-TEST-PLAN.md (LT-X86-00), 2026-11-11. Do not edit: if 22 changes, re-copy. -->

### LT-X86-00 · Inventory of the founder machines · **G (enabler)**
**Aliases:** W10-T1, X-1, X-3, W2-HW-5, Q290 · **Prerequisite:** a live USB of Debian 13 (boot it; nothing is installed) · **Time:** 30 min per machine
```sh
# On the Dell and on the Beelink (booted from a Debian 13 live USB):
lscpu | grep -E 'Model name|^CPU\(s\)'
sudo dmidecode -t system -t bios | grep -E 'Product Name|Version|Release Date'   # do NOT record the serial number
ls /sys/class/tpm; systemd-analyze has-tpm2
mokutil --sb-state
mokutil --db | grep -i "UEFI CA 2023"          # Microsoft 2023 CA present?
grep MemTotal /proc/meminfo
lsblk -d -o NAME,ROTA,TRAN,SIZE
/lib64/ld-linux-x86-64.so.2 --help | grep -E 'x86-64-v[234]'   # "x86-64-v3 (supported)" = RHEL 10 floor [C-W2-011]
sudo dmesg | grep -i watchdog                   # which hardware watchdog driver (e.g. iTCO_wdt) the image needs
fwupdmgr get-devices                            # LVFS firmware support
# On the Mac:
sysctl -n machdep.cpu.brand_string hw.memsize; sw_vers -productVersion
```
- **Pass:** every field of the W10-T1 template filled (device, CPU, RAM, disk type, TPM yes/no, Secure Boot state, BIOS version, LVFS yes/no, x86-64 level, watchdog driver); no "unknown". U55 CPU confirmed.
- **Fail → consequence:** none on the architecture. U55 without TPM → it is marked "encryption with recovery key, no TPM" in the install matrix (X-3). A CPU below x86-64-v3 is excluded from the bootc Industrial profile (W2-HW-5).
- **Feeds:** Q290, 26 §B "Dell 5540's state", the x86 rows below.
