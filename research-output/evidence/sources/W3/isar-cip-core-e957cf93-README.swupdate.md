# SWUpdate support for the CIP core image

This document describes how to build and test the SWUpdate pre-integration for
isar-cip-core, targeting a QEMU x86 virtual machine.

Start with cloning the isar-cip-core repository:
```
host$ git clone https://gitlab.com/cip-project/cip-core/isar-cip-core.git
```

## Update Partition selector(swupdate-handler-roundrobin)

SWUpdate uses the handler [swupdate-handler-roundrobin](https://gitlab.com/cip-project/cip-sw-updates/swupdate-handler-roundrobin) to select the partition to update.
The handler uses the information from sw-description file  to select the boot partition.
In the cip-core provided images the boot partitions are labeled `BOOT0`
and `BOOT1`, see [ebg-sysparts.inc](../wic/ebg-sysparts.inc).

The [sw-description](recipes-core/images/swu/sw-description.tmpl) contains the mapping from boot
partition to root file system partition, e.g.:
```
device = "C:BOOT0:linux.efi->${ABROOTFS_PART_UUID_A},C:BOOT1:linux.efi->${ABROOTFS_PART_UUID_B}";
```
The variables `ABROOTFS_PART_UUID_A` and `ABROOTFS_PART_UUID_B` contain partition uuids. The handler searches
for the matching device and SWUpdate writes the image to the selected device.

> :exclamation: For production image the content of the variable
`ABROOTFS_PART_UUID_A` and `ABROOTFS_PART_UUID_B` must contain project specific
values.

## SWUpdate Efibootguard update

:warning: **If the efibootguard binary is corrupted the system can no longer boot**

If you build a CIP Core image with SWUpdate support an additional swu will
be generated. This swu ends on `*-ebg.swu` and contains a sw-description to
update only efibootguard. SWUpdate will copy the file to a temporary location
and rename the binary in place to reduce the time the system can be destroyed
by a power failure. As FAT partitions have **no** atomic operations a small error
window is still possible.

If the variable `SWU_EBG_UPDATE` is set to `"1"` the update is also stored in
the `*.swu` file.

## SWUpdate scripts

It is possible to add [scripts](https://sbabic.github.io/swupdate/sw-description.html?#scripts) to a swu file.

To add a script entry in isar-cip-core set the variable `SWU_SCRIPTS`.
The content of the variable has the following pattern:
`script_name`

For each `script_name` the following flags need to be set:

```
SWU_SCRIPT_script_name[file] = "<script_file_name>"
```

The optional flag `type` can be used to set one of the following script types:
 - [lua](https://sbabic.github.io/swupdate/sw-description.html#lua)
 - [shellscript](https://sbabic.github.io/swupdate/sw-description.html#shellscript)
 - [preinstall](https://sbabic.github.io/swupdate/sw-description.html#preinstall)
 - [postinstall](https://sbabic.github.io/swupdate/sw-description.html#postinstall)

If no type is given SWUpdate defaults to "lua".
```
SWU_SCRIPT_script_name[type] = "<script_type>"
```

The optional flag `data` can be used as an script argument:

```
SWU_SCRIPT_script_name[data] = "<script argument>"
```

The file referenced by `<script_file_name>` is added to the variables `SRC_URI`
and `SWU_ADDITIONAL_FILES`. Therefore, it needs to be saved in a `FILESPATH`
location.

### Example: postinstall.sh

```
SWU_SCRIPTS = "postinstall"
SWU_SCRIPT_postinstall[file] = "postinstall.sh"
SWU_SCRIPT_postinstall[type] = "postinstall"
SWU_SCRIPT_postinstall[data] = "some_data"
```

This will add  `file://postinstall.sh` to the variable `SRC_URI` and
`postinstall.sh` to `SWU_ADDTIONAL_FILES`. The sw-description will contain
the following section:
```
    scripts: (
        {
          filename = "postinstall.sh";
          type = "postinstall";
          data = "some_data"
          sha256 = "<sha256 of postinstall.sh>";
        }):
```
### Example: Luascript
The simplest lua script has the following content:
```lua
function preinst()
	local message = "preinst called\n"
	local success = true
	return success, message
end
function postinst()
	local message = "postinst called\n"
	local success = true
	return success, message
end
```
and is added:

```
SWU_SCRIPTS = "luascript"
SWU_SCRIPT_luascript[file] = "luascript.lua"
SWU_SCRIPT_luascript[type] = "luascript"
SWU_SCRIPT_luascript[data] = "some_data"
```

The sw-description will contain the following section:
```
    scripts: (
        {
          filename = "luascript.lua";
          type = "lua";
          data = "some_data"
          sha256 = "<sha256 of luascript.lua>";
        }):
```
## SWUpdate Signing

The ISAR layer isar-cip-core provides templates to sign the swu binaries with
a CMS certificate.

By default the insecure [Debian snake-oil keys](./recipes-devtools/secure-boot-secrets/files/bookworm/) are used.
To use other key and certificate the following variables must be set:
```
PREFERRED_PROVIDER_swupdate-certificates-key = "swupdate-certificates-key"
PREFERRED_PROVIDER_swupdate-certificates = "swupdate-certificates"
PREFERRED_PROVIDER_swupdate-signer = "swupdate-signer-cms"
SWU_SIGN_KEY  = "<siging key file name>"
```

The files `<sigining certificate file name>` and `<siging key file name>` need to be stored
in `recipes-devtools/swupdate-certificates/files/` or in a path defined by an bbappend file, e.g.`swupdate-certificates-key_%.bbappend`

### signing script

The package [swupdate-signer-cms](recipes-devtools/swupdate-signer/) provides a [cms signing script](./recipes-devtools/swupdate-certificates/files/sign-swu-cms).
When signing requires a project specific signing script,
e.g. for using a hardware security module(HSM), an own package can be added.
The package can replace the default package by adding the following lines:

```
PREFERRED_PROVIDER_swupdate-signer = "<own swupdate signer>"
PREFERRED_PROVIDER_swupdate-certificates = "<own certificate provider>"
```

The packages `swupdate-signer` and `swupdate-certificate` must be set to sign the swu-binary
and verify the signed swu-binary during an update.
An key to the signing script can be provided with:
```
PREFERRED_PROVIDER_swupdate-certificates-key = "<own key provider>"
```

The package `<own signing package>` needs to install a executable to `/usr/bin/sign-swu`.

An empty signer to be used as a template is provided in [swupdate-signer-empty](recipes-devtools/swupdate-signer/swupdate-signer-empty.bb).

## SWUpdate Hardware compatibility

The variable `SWU_HW_COMPAT` contains a space separate list of
compatible hardware revisions.
SWUpdate checks the compatibility against `/etc/hwrevision`, see
[hardware-compatibility in the SWUpdate documentation.](https://sbabic.github.io/swupdate/sw-description.html#hardware-compatibility)

For testing purpose the content of `/etc/hwrevision` can be set with
the variable `MACHINE_HW_VERSION`.

In production scenarios it is recommended to acquire a HW specific
identifier (e.g., Board identifer with dmidecode) during boot up and
write it to `/etc/hwrevision`.

# Building and testing the CIP Core image

Set up `kas-container` as described in the [top-level README](../README.md).
Then build the image which will later serve as update package:
```
host$ ./kas-container build kas-cip.yml:kas/board/qemu-amd64.yml:kas/opt/ebg-swu.yml
```
Save the generated swu `build/tmp/deploy/images/qemu-amd64/cip-core-image-cip-core-trixie-qemu-amd64.swu` into a separate folder (ex: /tmp).

Next, rebuild the image, switching to the RT kernel as modification:
```
host$ ./kas-container build kas-cip.yml:kas/board/qemu-amd64.yml:kas/opt/ebg-swu.yml:kas/opt/rt.yml
```

Now start the image which will contain the RT kernel:
```
host$ DISTRO_RELEASE=trixie SWUPDATE_BOOT=y ./start-qemu.sh amd64
```

Copy `cip-core-image-cip-core-trixie-qemu-amd64.swu` file from `tmp` folder into the running system:
```
host$ scp -P 22222 /tmp/cip-core-image-cip-core-trixie-qemu-amd64.swu root@localhost:
```

## SWUpdate verification

Check which partition is booted, e.g. with lsblk:
```
root@demo:~# lsblk
NAME   MAJ:MIN RM  SIZE RO TYPE MOUNTPOINTS
sda      8:0    0  2.8G  0 disk
├─sda1   8:1    0   16M  0 part /boot
├─sda2   8:2    0  128M  0 part
├─sda3   8:3    0  128M  0 part
├─sda4   8:4    0    1G  0 part /
├─sda5   8:5    0    1G  0 part
└─sda6   8:6    0  512M  0 part /var
```

Also check that you are running the RT kernel (i.e PREEMPT_RT):
```
root@demo:~# uname -a
Linux demo 6.12.85-cip22 #1 SMP PREEMPT_RT Thu, 01 Jan 1970 06:30:00 +0530 x86_64 GNU/Linux
root@demo:~# ls /lib/modules
6.12.85-cip22
```

Now apply swupdate and reboot
```
root@demo:~# swupdate -i cip-core-image-cip-core-trixie-qemu-amd64.swu
root@demo:~# reboot
```
Use the `-v` flag when running swupdate for verbose logs of any errors.

Check which partition is booted, e.g. with lsblk and the rootfs should have changed
```
root@demo:~# lsblk
NAME   MAJ:MIN RM  SIZE RO TYPE MOUNTPOINTS
sda      8:0    0  2.8G  0 disk
├─sda1   8:1    0   16M  0 part /boot
├─sda2   8:2    0  128M  0 part
├─sda3   8:3    0  128M  0 part
├─sda4   8:4    0    1G  0 part
├─sda5   8:5    0    1G  0 part /
└─sda6   8:6    0  512M  0 part /var
```

Check the active kernel:
```
root@demo:~# uname -a
Linux demo 6.12.85-cip22 #1 SMP PREEMPT_DYNAMIC Thu, 01 Jan 1970 06:30:00 +0530 x86_64 GNU/Linux
root@demo:~# ls /lib/modules
6.12.85-cip22
```

Check bootloader ustate after swupdate
```
root@demo:~# bg_printenv

----------------------------
 Config Partition #0 Values:
in_progress:      no
revision:         2
kernel:           C:BOOT0:linux.efi
kernelargs:
watchdog timeout: 120 seconds
ustate:           0 (OK)

user variables:



----------------------------
 Config Partition #1 Values:
in_progress:      no
revision:         3
kernel:           C:BOOT1:linux.efi
kernelargs:
watchdog timeout: 120 seconds
ustate:           2 (TESTING)

user variables:


```

If Partition #1 ustate is 2 (TESTING) then execute below command to confirm swupdate and the command will set ustate to "OK".
```
root@demo:~# bg_setenv -c
```

## SWUpdate rollback example

Build the image for swupdate with a service which causes kernel panic during system boot using below command:

```
host$ ./kas-container build kas-cip.yml:kas/board/qemu-amd64.yml:kas/opt/ebg-swu.yml:kas/opt/kernel-panic.yml
```
Save the generated swu `build/tmp/deploy/images/qemu-amd64/cip-core-image-cip-core-trixie-qemu-amd64.swu` in a separate folder.
Then build the image without `kernel-panic.yml` recipe using below command:
```
host$ ./kas-container build kas-cip.yml:kas/board/qemu-amd64.yml:kas/opt/ebg-swu.yml
```

Start the target on QEMU:
```
host$ DISTRO_RELEASE=trixie SWUPDATE_BOOT=y ./start-qemu.sh amd64
```

Copy `cip-core-image-cip-core-trixie-qemu-amd64.swu` file from `tmp` folder into the running system:
```
host$ scp -P 22222 /tmp/cip-core-image-cip-core-trixie-qemu-amd64.swu root@localhost:
```

Apply swupdate as below:
```
root@demo:~# swupdate -i cip-core-image-cip-core-trixie-qemu-amd64.swu
```

Check bootloader ustate after swupdate. If the swupdate is successful then **revision number** should be **3** and status should be changed to **INSTALLED** for Partition #1.
```
root@demo:~# bg_printenv

----------------------------
 Config Partition #0 Values:
in_progress:      no
revision:         2
kernel:           C:BOOT0:linux.efi
kernelargs:
watchdog timeout: 120 seconds
ustate:           0 (OK)

user variables:



----------------------------
 Config Partition #1 Values:
in_progress:      no
revision:         3
kernel:           C:BOOT1:linux.efi
kernelargs:
watchdog timeout: 120 seconds
ustate:           1 (INSTALLED)

user variables:


```

Execute the reboot command.
```
root@demo:~# reboot
```

The new kernel should cause a kernel panic error.
The watchdog timer should expire and restart the VM (it will take 2 minutes due to an issue in.
The bootloader will then select the previous, working partition and boot from it.

Once the system is restarted, check the bootloader ustate.
If update is failed then **revision number** should be reduced to **0** and status should have changed to **FAILED** for Partition #1.
```
root@demo:~# bg_printenv

----------------------------
 Config Partition #0 Values:
in_progress:      no
revision:         2
kernel:           C:BOOT0:linux.efi
kernelargs:
watchdog timeout: 120 seconds
ustate:           0 (OK)

user variables:



----------------------------
 Config Partition #1 Values:
in_progress:      no
revision:         0
kernel:           C:BOOT1:linux.efi
kernelargs:
watchdog timeout: 120 seconds
ustate:           3 (FAILED)

user variables:


```

# Building and testing the CIP Core image for Delta Software Update

Set up `kas-container` as described in the [top-level README](../README.md), and then proceed with the following steps.

First build an image using the following command:
```
host$ ./kas-container build kas-cip.yml:kas/board/qemu-amd64.yml:kas/opt/ebg-swu.yml:kas/opt/rt.yml
```
The image is built with the RT kernel just so that there are some differences between the two images used. The above image will be used as the base image to which the update is applied.

## Delta Software Update using rdiff (rdiff_image & rdiff_file handlers)

**Note**: Only `rdiff` supports delta kernel binary update using `rdiff_file` handler.

Creating an delta update file for rdiff_image (rootfs) and rdiff_file (kernel)  handlers requires a reference artifacts (against which the delta is computed). In this case, the image and kernel built in the previous section can be used as the reference artifacts. By default the `DELTA_UPDATE_TYPE` is set to `rdiff`, `DELTA_RDIFF_REF_IMAGE` is set to the name `${IMAGE_FULLNAME}.squashfs` (or ${IMAGE_FULLNAME}.verity in the case of Secure boot enabled image) and `DELTA_RDIFF_REF_KERNEL_IMAGE` is set to the name `linux.efi`. The values of `DELTA_UPDATE_TYPE`, `DELTA_RDIFF_REF_IMAGE` and `DELTA_RDIFF_REF_KERNEL_IMAGE` can be changed in the `delta-update.yml` file.

The build system looks for the reference artifact in a directory named `previous-image` in the build directory used for the build process.

Copy the reference artifacts to the mentioned directory with the following commands:
```
mkdir -p build-v2/previous-image
cp build/tmp/deploy/images/qemu-amd64/cip-core-image-cip-core-trixie-qemu-amd64.squashfs build-v2/previous-image
cp build/tmp/deploy/images/qemu-amd64/linux.efi build-v2/previous-image
```
Build the second image with `build-v2` as the build directory with the following command:
```
KAS_BUILD_DIR=build-v2 ./kas-container build kas-cip.yml:kas/board/qemu-amd64.yml:kas/opt/ebg-swu.yml:kas/opt/delta-update.yml
```
Now start the first image. Run the following commands:
```
host$ DISTRO_RELEASE=trixie SWUPDATE_BOOT=y ./start-qemu.sh amd64
```
Copy `cip-core-image-cip-core-trixie-qemu-amd64.swu` file from `build-v2/tmp/deploy/images/qemu-amd64/` folder into the running system:
```
host$ cd build-v2/tmp/deploy/images/qemu-amd64/
host$ scp -P 22222 ./cip-core-image-cip-core-trixie-qemu-amd64.swu root@localhost:
```

## Delta Software Update using zchunk handler

Currently zchunk based delta updates are supported only in trixie images. Make sure to build the first image with trixie as the distribution with the following command:
```
host$ ./kas-container build kas-cip.yml:kas/board/qemu-amd64.yml:kas/opt/ebg-swu.yml
```
For Delta update with zchunk, set the variable `DELTA_ZCK_URL` with the URL of the zck file that is hosted in a http server and set the `DELTA_UPDATE_TYPE` to `zchunk` in `delta-update.yml` file.

Build the second image with the modification as shown above with the following command:
```
KAS_BUILD_DIR=build-v2 ./kas-container build kas-cip.yml:kas/board/qemu-amd64.yml:kas/opt/ebg-swu.yml:kas/opt/delta-update.yml
```
Now start the first image. Run the following commands:
```
host$ DISTRO_RELEASE=trixie SWUPDATE_BOOT=y ./start-qemu.sh amd64
```
Copy `cip-core-image-cip-core-trixie-qemu-amd64.swu` file from `build-v2/tmp/deploy/images/qemu-amd64/` folder into the running system:
```
host$ cd build-v2/tmp/deploy/images/qemu-amd64/
host$ scp -P 22222 ./cip-core-image-cip-core-trixie-qemu-amd64.swu root@localhost:
```
The `cip-core-image-cip-core-trixie-qemu-amd64.zck` file must be hosted in a http server.
Any http server (service) can be used to host the .zck file as long as the http server supports http range requests. Copy the `build-v2/tmp/deploy/images/qemu-amd64/cip-core-image-cip-core-trixie-qemu-amd64.zck` to the server directory. For more information on the integration of zchunk handler in swupdate, refer the [documentation](https://sbabic.github.io/swupdate/delta-update.html#integration-in-swupdate-the-delta-handler)

## Delta Software Update Verification

Follow the steps mentioned in the section [SWUpdate verification](#swupdate-verification) for verification.

# Software update with wfx

**NOTE**: In the following sections, `WFX_HOST` refers to the IP address or DNS-resolvable name of your `wfx` server. Please substitute `WFX_HOST` with the appropriate value wherever it appears.

Set the `WFX backend URL` to `http://WFX_HOST:8080/api/wfx/v1` via the `Kconfig` menu.

Install `wfxctl` and `wfx` in the host:
The instructions below assume that `wfxctl` and `wfx` are running on a `x86-64` host. Binaries for other architectures are also available for [download](https://github.com/siemens/wfx/releases).
```
## Install wfxctl
host$ curl -LO https://github.com/siemens/wfx/releases/download/v0.4.1/wfxctl_0.4.1_linux_x86_64.deb
host$ dpkg -i wfxctl_0.4.1_linux-x86_64.deb

## Install wfx
host$ curl -LO https://github.com/siemens/wfx/releases/download/v0.4.1/wfx_0.4.1_linux_x86_64.deb
host$ dpkg -i wfx_0.4.1_linux-x86_64.deb
```

Build an image using the Kconfig menu which will later serve as update package. Set `WFX backend URL`.
```
    -> "Target Board"
      -> "QEMU AMD64 (x86-64)"
    -> "CIP kernel version"
      -> "Kernel 6.12.x-cip"
    -> "Debian Release"
      -> "trixie (13)"
    -> "SWUpdate support for root partition"
      -> "WFX backend URL"
      -> "Update type"
        -> "Complete Update"
```

Save the generated swu build/tmp/deploy/images/qemu-amd64/cip-core-image-cip-core-trixie-qemu-amd64.swu into a separate folder

```
host$ mkdir -p /tmp/artifacts
host$ cp build/tmp/deploy/images/qemu-amd64/cip-core-image-cip-core-trixie-qemu-amd64.swu /tmp/artifacts
```

Next, rebuild the image using the Kconfig menu, switching to the RT kernel as modification:
```
    -> "Target Board"
      -> "QEMU AMD64 (x86-64)"
    -> "CIP kernel version"
      -> "Kernel 6.12.x-cip"
    -> "Real-time CIP kernel"
    -> "Debian Release"
      -> "trixie (13)"
    -> "SWUpdate support for root partition"
      -> "WFX backend URL"
      -> "Update type"
        -> "Complete Update"
```

Now start the image which will contain the RT kernel:
```
host$ DISTRO_RELEASE=trixie SWUPDATE_BOOT=y ./start-qemu.sh amd64
```

By default, SWUpdate uses the machine-id from `/etc/machine-id` as the `client-id` (configurable via `WFX_DEVICE_ID` in the `swupdate-config-wfx` recipe). This `client-id` is later used to create `wfx` job for the client:
```
root@demo cat /etc/machine-id
049adc79659044f8887c83b3203c84f1
```

Start `wfx` server in the host:
```
host$ wfx --simple-fileserver /tmp/artifacts
```
Alternatively, `wfx` can also be run as a [docker container](https://github.com/siemens/wfx/blob/a6ecb60bb47eaf1f95a2b65b4190538a246d79d1/docs/installation.md#build-and-installation).

Create `wfx.workflow.dau.direct` wofkflow:
```
host$ curl -L https://raw.githubusercontent.com/siemens/wfx/refs/heads/main/workflow/dau/wfx.workflow.dau.direct.yml | wfxctl workflow create -
```

Create a wfx job that updates the device. Set `client-id` with the device identity (default: `/etc/machine-id`) from qemu:
```
host$ cat <<EOF | envsubst | wfxctl job create --client-id '049adc79659044f8887c83b3203c84f1' --workflow wfx.workflow.dau.direct -
{
  "version": "1.0",
  "type": ["firmware"],
  "artifacts": [
    {
      "name": "Example Device Firmware Artifact",
      "version": "1.1",
      "uri": "http://${WFX_HOST}:8080/download/cip-core-image-cip-core-trixie-qemu-amd64.swu"
    }
  ]
}
EOF
```

Wait for the next swupdate polling round (every 20 seconds) to see how swupdate downloads and applies the update.
```
root@demo journalctl -u swupdate -f

// truncated output
swupdate.sh[432]: [TRACE] : SWUPDATE running :  [start_suricatta] : Suricatta awakened.
swupdate.sh[432]: [DEBUG] : SWUPDATE running :  [notify_helper] : Suricatta querying "http://WFX_HOST:8080/api/wfx/v1/jobs?clientId=049adc79659044f8887c83b3203c84f1&group=OPEN"
```

Once the update is successfully installed, the device automatically reboots. After reboot, suricatta automatically updates the bootloader state.
```
root@demo bg_printenv

----------------------------
 Config Partition #0 Values:
in_progress:      no
revision:         2
kernel:           C:BOOT0:linux.efi
kernelargs:
watchdog timeout: 120 seconds
ustate:           0 (OK)

user variables:



----------------------------
 Config Partition #1 Values:
in_progress:      no
revision:         3
kernel:           C:BOOT1:linux.efi
kernelargs:
watchdog timeout: 120 seconds
ustate:           0 (OK)

user variables:
```

# Building and testing the CIP Core image for BBB

Follow the steps mentioned in the section [Building and testing the CIP Core image](README.swupdate.md#building-and-testing-the-cip-core-image) for creating images and .swu files.
- Replace qemu-amd64.yml kas file with BBB board specific file i.e bbb.yml
- .swu file will be generated in the following folder build/tmp/deploy/images/bbb/
- Create Non-RT and RT Kernel images as mentioned in the section

Flash the BeagleBone Black RT kernel image into SDcard
```
host$ dd if=build/tmp/deploy/images/bbb/cip-core-image-cip-core-trixie-bbb.wic \
   of=/dev/<medium-device> bs=1M status=progress
```

After flashing the BBB RT kernel image into SD card, mount the SD card on host PC and copy .swu file from `tmp` folder to root partition like below.

```
host$ sudo cp tmp/cip-core-image-cip-core-trixie-bbb.swu /<mnt>/root/
```

Connect a serial port cable between host PC and BBB.
Insert SD card to BBB, hold S2 button while applying power supply to BBB.

For verifying swupdate on BBB use the same steps as mentioned in above [SWUpdate Verification](README.swupdate.md#swupdate-verification).
