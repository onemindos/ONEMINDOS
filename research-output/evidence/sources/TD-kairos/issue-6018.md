# kairos-io/kairos#6018: Upgrade to v4.4.0 replaces GRUB on the ESP but keeps the old grub.cfg on COS_STATE, so nodes with a TPM do not boot
state: closed created: 2026-11-07T07:07:38Z closed: 2026-11-10T06:10:15Z

**Kairos version:**

```
NAME="Fedora Linux"
VERSION="45 (Container Image)"
RELEASE_TYPE=stable
ID=fedora
VERSION_ID=45
VERSION_CODENAME=""
PRETTY_NAME="Fedora Linux 45 (Container Image)"
ANSI_COLOR="0;38;2;60;110;180"
LOGO=fedora-logo-icon
CPE_NAME="cpe:/o:fedoraproject:fedora:45"
DEFAULT_HOSTNAME="fedora"
HOME_URL="https://fedoraproject.org/"
DOCUMENTATION_URL="https://docs.fedoraproject.org/en-US/fedora/f45/"
SUPPORT_URL="https://ask.fedoraproject.org/"
BUG_REPORT_URL="https://bugzilla.redhat.com/"
REDHAT_BUGZILLA_PRODUCT="Fedora"
REDHAT_BUGZILLA_PRODUCT_VERSION=45
REDHAT_SUPPORT_PRODUCT="Fedora"
REDHAT_SUPPORT_PRODUCT_VERSION=45
SUPPORT_END=2027-12-08
VARIANT="Container Image"
VARIANT_ID=container
```

```
KAIROS_ARCH="amd64"
KAIROS_BUG_REPORT_URL="https://github.com/kairos-io/kairos/issues"
KAIROS_FAMILY="redhat"
KAIROS_FIPS="false"
KAIROS_FLAVOR="fedora"
KAIROS_FLAVOR_RELEASE=45
KAIROS_HOME_URL="https://github.com/kairos-io/kairos"
KAIROS_ID="kairos"
KAIROS_ID_LIKE="kairos-standard-fedora-45"
KAIROS_INIT_VERSION="v4.4.0"
KAIROS_MODEL="generic"
KAIROS_NAME="kairos-standard-fedora-45"
KAIROS_RELEASE="v1.0.0"
KAIROS_SOFTWARE_VERSION="v1.37.2+k3s1"
KAIROS_SOFTWARE_VERSION_PREFIX="k3s"
KAIROS_TARGETARCH="amd64"
KAIROS_TRUSTED_BOOT="false"
KAIROS_VARIANT="standard"
KAIROS_VERSION="v1.0.0-mack.2026.11.0"
```

This is the image after the upgrade. The node was installed in November 2023 with an older Kairos release, and before this upgrade it ran an image built with kairos-init v0.17.3.

**CPU architecture, OS, and Version:**

```
Linux <hostname-masked> 7.2.15-300.fc45.x86_64 #1 SMP PREEMPT_DYNAMIC Sun Nov  1 16:11:16 UTC 2026 x86_64 GNU/Linux
```

UEFI with Secure Boot off, and a TPM 2.0.

**Describe the bug**

After an upgrade to v4.4.0 and a reboot, no boot entry boots. The active, fallback and recovery entries all fail.

The upgrade refreshes shim, GRUB and the ESP grub.cfg (`refreshESPFromCtx` in `agent/pkg/action/upgrade_finalize.go`, line 242, which calls `grub.RefreshESP` at line 324). After the upgrade, the ESP has GRUB 2.12-83 from Fedora 45. The upgrade does not change `/grub2/grub.cfg` on COS_STATE. On this node, that file is from the 2023 install. It does not have the `rmmod tpm` line that the current grub.cfg has. kairos-io/packages#607 added that line on 2024-01-09, after this node was installed. The line is a workaround for [Launchpad bug 1851311](https://bugs.launchpad.net/ubuntu/+source/grub2/+bug/1851311).

With the tpm module loaded, the loopback of the 3 GiB `/cOS/*.img` file reads the whole file into the GRUB heap. The kernel then does not fit in the memory that remains, and the entry fails. The upgrade also rewrites the active, passive and recovery images, so no entry can boot.

**To Reproduce**

1. Install a node with a Kairos release whose grub.cfg does not have `rmmod tpm`. The node must use UEFI and have a TPM.
2. Upgrade the node to a v4.4.0 image with `kairos-agent upgrade`. We ran the upgrade through a kairos-operator `NodeOpUpgrade` with `upgradeRecovery: true`.
3. Reboot the node.

We also reproduced it in QEMU with OVMF (Secure Boot off), a swtpm TPM 2.0, GRUB 2.12-83 on the ESP, a 3 GiB ext2 `/cOS/active.img`, and a cold boot:

| COS_STATE grub.cfg | Result |
| --- | --- |
| From the 2023 install (no `rmmod tpm`) | `kernel_alloc:159 can't allocate kernel`. `lsmod` shows `tpm`. The loopback takes about 34 s, and loader memory grows from about 37 MB to about 5 GB. |
| The v4.4.0 `/etc/cos/grub.cfg` | Boots. |
| The 2023 file, with `rmmod tpm` from `/grubmenu` | Boots. The loopback takes 0.2 s. |

**Expected behavior**

An upgrade that replaces GRUB on the ESP also brings `/grub2/grub.cfg` on COS_STATE up to date. Alternatively, the upgrade does not replace GRUB when the grub.cfg on COS_STATE is from an older release.

**Logs**

The first boot entry fails with:

```
error: ../../grub-core/loader/i386/efi/linux.c:kernel_alloc:159:can't allocate kernel.
```

The next entries then fail with these errors, because the old grub.cfg has no `loopback -d loop0` guard and the heap is full:

```
error: ../../grub-core/disk/loopback.c:99:device name already exists.
```

```
too little memory
```

**Additional context**

Related history:

- #1842 and #2041 report the same GRUB out of memory on machines with a TPM. #2041 found the `rmmod tpm` workaround. #1842 was closed after kairos-io/packages#553 restored an older GRUB EFI binary.
- kairos-io/packages#607 added `rmmod tpm` on EFI to grub.cfg. A node installed before that change keeps its old grub.cfg on COS_STATE, and an upgrade does not replace it.

We use the third workaround below in our image: marinatedconcrete/config#1000.

Workarounds:

- At the GRUB shell, run `rmmod tpm`, and then run the commands of the boot entry.
- Replace `/grub2/grub.cfg` on COS_STATE with the grub.cfg from the new image.
- In the image, add `rmmod tpm` (on EFI) to `/etc/kairos/branding/grubmenu.cfg`. The upgrade copies that file to `/grubmenu`, and the old grub.cfg sources `/grubmenu` before an entry runs.

On a fresh v4.4.0 install, the third workaround runs `rmmod tpm` a second time. GRUB prints one `no such module` line and then boots without a key press.
