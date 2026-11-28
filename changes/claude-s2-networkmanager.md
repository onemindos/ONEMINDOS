---
pr: 1093
branch: claude/s2-networkmanager
---
Step 2 of the Debian bones, part 3: the hardware boards (x86_64-efi, its NVIDIA variant, arm64-efi, rpi5 and the vm board) now run NetworkManager with wpasupplicant, wireless-regdb, iw and rfkill, so a person can save a Wi-Fi or static profile. Saved profiles and NetworkManager's state live on /data (two bind mounts, profiles folder mode 0700) and survive reboots and updates. DNS goes through systemd-resolved, flannel, cni0, veth and tailscale0 are left unmanaged, and the DHCP identity uses the MAC address because /etc/machine-id is transient. k3s waits for NetworkManager-wait-online, which no longer waits for every NIC, so a second card with a link and no DHCP server cannot delay k3s. Cloud boards, the installer and the recovery target keep systemd-networkd. New checks NW1-NW4 in the first-boot battery and FW5 in the firewall battery, criteria pre-registered in test/qemu/CRITERIA-NETWORK.md. Wi-Fi association cannot be tested in QEMU.
