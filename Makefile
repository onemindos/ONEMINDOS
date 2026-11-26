# SPDX-License-Identifier: Apache-2.0
# OneMind OS build entry points (brief 30 §5, D-B1.2). Image builds run in containers built
# from os/rootfs/Containerfile; Mac setup and native tests: docs/learning/mac-dev-loop.md.
#
#   make rootfs  BOARD=x86_64-efi [LEG=debian|ubuntu]   -> out/rootfs-<leg>-<board>.tar
#   make repro-check BOARD=x86_64-efi                   -> builds the rootfs twice and compares (reproducible build)
#   make image   BOARD=x86_64-efi [VERSION=...]         -> out/image-<board>/ (disk .img, .raucb, SHA256SUMS)
#   make image   BOARD=x86_64-efi SECUREBOOT=1          -> the Secure Boot route (efi backend, signed UKI per slot, dev key; off by default)
#   make image   BOARD=x86_64-efi VERSION=0.1.0 KEYRING=rauc-ca.pem -> an image that trusts the real RAUC CA (Step 5; public cert only)
#   make fixtures BOARD=x86_64-efi [UPTO=T5] [HW=1]     -> out/fx-<board>/ (battery inputs; HW=1 for founder kits)
#   make fixtures ... DATA_FS=luks2                      -> data partition left blank, encrypted on first boot
#   make dataenc BOARD=x86_64-efi                       -> out/dataenc-<board>/ (E1-E7 and the reset tests R1-R2; DATAENC_ARGS='--only reset' runs just R1-R2)
#   make battery BOARD=x86_64-efi [UPTO=T5]             -> out/battery-<board>/ (serial log, results.json)
#   make firstboot BOARD=x86_64-efi [FUPTO=F4]          -> out/firstboot-<board>/ (F0-F4, CRITERIA-FIRSTBOOT.md)
#   make secureboot-test                                -> out/secureboot-x86_64-efi/ (SB1-SB7, CRITERIA-SECUREBOOT.md)
#   make bootlock  BOARD=x86_64-efi                     -> out/bootlock-<board>/ (B1-B6, CRITERIA-BOOTLOCK.md)
#   make rollback  BOARD=x86_64-efi                     -> out/rollback-<board>/ (RB0-RB4, CRITERIA-ROLLBACK.md)
#   make edge      BOARD=x86_64-efi                     -> out/edge-<board>/ (EG1-EG7, CRITERIA-EDGE.md; fixtures with EDGE=1)
#   make sysextguard BOARD=x86_64-efi                   -> out/sysextguard-<board>/ (T-W19-01 X0-X7, CRITERIA-SYSEXT.md)
#   make convert BOARD=vm                               -> qcow2 / vhdx / vmdk / vdi / ova next to the image
#   make jetson-layer [VERSION=...]                     -> out/onemind-layer-jetson-orin-<version>.tar.gz
#   make hygiene | hygiene-selftest | lint | test | kit LT=LT-X86-01
SHELL      := /bin/bash
BOARD      ?= x86_64-efi
LEG        ?= debian
UPTO       ?= T5
HW         ?= 0
DATA_FS    ?=
SECUREBOOT ?= 0
EDGE       ?= 0
FUPTO      ?= F4
VERSION    ?= 0.1.0-dev
OUT        ?= out
ARCH_OF     = $(shell sed -n 's/^arch: *//p' os/boards/$(BOARD)/board.yaml)
PLATFORM    = linux/$(ARCH_OF)
# FIRMWARE=no builds the fully open image, without closed firmware or microcode (os/rootfs/firmware/README.md)
FIRMWARE   ?= yes
# The man pages are dated with the commit time (reproducible per commit); 0 outside git. Not named SOURCE_DATE_EPOCH on purpose:
# BuildKit treats that build-arg as "rewrite every file time in the image", which made the gateway recompile its Python at each start (F11).
EPOCH      ?= $(shell git log -1 --format=%ct 2>/dev/null || echo 0)
LEG_ARGS    = $(shell sed -n 's/^\([A-Z]*=.*\)/--build-arg \1/p' os/rootfs/$(LEG).args)
TOOLS      ?= onemind-tools:$(ARCH_OF)
ROOTFS      = $(OUT)/rootfs-$(LEG)-$(BOARD).tar
# Reproducible build: the epoch is the pinned snapshot's own timestamp (os/rootfs/source-date-epoch.py), empty on a
# leg without a snapshot. Build args, tar timestamps and the assembler's mke2fs all take it.
SOURCE_DATE_EPOCH ?= $(shell python3 -I os/rootfs/source-date-epoch.py "$$(sed -n 's/^SNAPSHOT=//p' os/rootfs/$(LEG).args)")
SDE_ARG     = $(if $(SOURCE_DATE_EPOCH),--build-arg SOURCE_DATE_EPOCH=$(SOURCE_DATE_EPOCH))
SDE_TAR     = $(if $(SOURCE_DATE_EPOCH),$(comma)rewrite-timestamp=true)
comma       = ,
DOCKER_RUN  = docker run --rm --platform $(PLATFORM) -v "$(CURDIR)":/src:ro -v "$(CURDIR)/$(OUT)":/out
KVM         = $(shell [ -w /dev/kvm ] && echo --device /dev/kvm)

.PHONY: help tools rootfs repro-check image fixtures battery firstboot bootlock rollback sysextguard dataenc convert hygiene hygiene-selftest lint test kit clean secureboot-image secureboot-test

help:
	@sed -n 's/^#   make/make/p' Makefile

$(OUT):
	mkdir -p $(OUT)

tools: | $(OUT)
	docker image inspect $(TOOLS) >/dev/null 2>&1 || docker buildx build -f os/rootfs/Containerfile --target tools --platform $(PLATFORM) \
	  $(shell sed -n 's/^\([A-Z]*=.*\)/--build-arg \1/p' os/rootfs/debian.args) --load -t $(TOOLS) .

rootfs: | $(OUT)
	docker buildx build -f os/rootfs/Containerfile --target rootfs --platform $(PLATFORM) \
	  --build-arg BOARD=$(BOARD) --build-arg FIRMWARE=$(FIRMWARE) --build-arg MAN_DATE_EPOCH=$(EPOCH) $(LEG_ARGS) $(SDE_ARG) --output type=tar,dest=$(ROOTFS)$(SDE_TAR) .
	@ls -la $(ROOTFS)

# Reproducible build (Step 2 PR 8): two from-scratch rootfs builds must give the same tar and the same rootfs.ext4.
#   make repro-check BOARD=x86_64-efi   -> out/repro-<board>/ (no KVM needed; two full builds, about 15 minutes)
repro-check: tools
	BOARD=$(BOARD) LEG=$(LEG) OUT=$(OUT) TOOLS=$(TOOLS) sh os/rootfs/repro-check.sh

# A development image, signed with a throwaway CA made here and deleted after use (SB-10).
image: tools
	@test -f $(ROOTFS) || $(MAKE) rootfs BOARD=$(BOARD) LEG=$(LEG)
	$(DOCKER_RUN) -e VERSION=$(VERSION) -e BOARD=$(BOARD) -e SECUREBOOT=$(SECUREBOOT) -e ROOTFS=/out/$(notdir $(ROOTFS)) -e SOURCE_DATE_EPOCH=$(SOURCE_DATE_EPOCH) \
	  $(if $(KEYRING),-v "$(abspath $(KEYRING))":/keyring.pem:ro -e KEYRING=/keyring.pem) $(TOOLS) \
	  /src/os/assemble/dev-image.sh /out/image-$(BOARD)

fixtures: tools
	@test -f $(ROOTFS) || $(MAKE) rootfs BOARD=$(BOARD) LEG=$(LEG)
	$(DOCKER_RUN) -e HW=$(HW) -e DATA_FS=$(DATA_FS) -e EDGE=$(EDGE) $(TOOLS) /src/test/qemu/mkfixtures.sh $(BOARD) /out/$(notdir $(ROOTFS)) /out/fx-$(BOARD) $(UPTO)

battery:
	@test -f $(OUT)/fx-$(BOARD)/disk.img || $(MAKE) fixtures BOARD=$(BOARD) UPTO=$(UPTO)
	mkdir -p $(OUT)/battery-$(BOARD)
	$(DOCKER_RUN) $(KVM) $(TOOLS) python3 -I /src/test/qemu/run-tests.py --board $(BOARD) \
	  --fixtures /out/fx-$(BOARD) --log /out/battery-$(BOARD)/serial.log --upto $(UPTO) \
	  --results /out/battery-$(BOARD)/results.json

# First boot into OneMind (test/qemu/firstboot.py). Copies the fixture disk, so run it before
# `make battery` (which boots the fixture disk itself) or after a fresh `make fixtures`.
firstboot:
	@test -f $(OUT)/fx-$(BOARD)/disk.img || $(MAKE) fixtures BOARD=$(BOARD)
	mkdir -p $(OUT)/firstboot-$(BOARD)
	$(DOCKER_RUN) $(KVM) $(TOOLS) python3 -I /src/test/qemu/firstboot.py --board $(BOARD) \
	  --fixtures /out/fx-$(BOARD) --work /out/firstboot-$(BOARD)/work --upto $(FUPTO) \
	  --log /out/firstboot-$(BOARD)/serial.log --results /out/firstboot-$(BOARD)/results.json; \
	  rc=$$?; rm -f $(OUT)/firstboot-$(BOARD)/work/disk.img; exit $$rc

# Host firewall port scan from a second VM (test/qemu/firewall.py, CRITERIA-FIREWALL.md FW1-FW4).
.PHONY: firewall
firewall:
	@test -f $(OUT)/fx-$(BOARD)/disk.img || $(MAKE) fixtures BOARD=$(BOARD)
	mkdir -p $(OUT)/firewall-$(BOARD)
	$(DOCKER_RUN) $(KVM) $(TOOLS) python3 -I /src/test/qemu/firewall.py --board $(BOARD) \
	  --fixtures /out/fx-$(BOARD) --work /out/firewall-$(BOARD)/work \
	  --log /out/firewall-$(BOARD)/serial.log --results /out/firewall-$(BOARD)/results.json; \
	  rc=$$?; rm -rf $(OUT)/firewall-$(BOARD)/work; exit $$rc


# Setup wizard on the booted image (test/qemu/wizard.py, CRITERIA-WIZARD.md WZ1-WZ5): two VMs without a seed, the
# unprivileged web part and its root helper, a LAN flood, then wizard to hub (LAN, with the code) and to worker.
.PHONY: wizard
wizard:
	@test -f $(OUT)/fx-$(BOARD)/disk.img || $(MAKE) fixtures BOARD=$(BOARD)
	mkdir -p $(OUT)/wizard-$(BOARD)
	$(DOCKER_RUN) $(KVM) $(TOOLS) python3 -I /src/test/qemu/wizard.py --board $(BOARD) \
	  --fixtures /out/fx-$(BOARD) --work /out/wizard-$(BOARD)/work \
	  --log /out/wizard-$(BOARD)/serial.log --results /out/wizard-$(BOARD)/results.json; \
	  rc=$$?; rm -rf $(OUT)/wizard-$(BOARD)/work; exit $$rc

# Boot menu lock (test/qemu/bootlock.py): the GRUB menu asks for a login before it lets anyone edit a kernel
# command line. Copies the fixture disk like `firstboot`.
bootlock:
	@test -f $(OUT)/fx-$(BOARD)/disk.img || $(MAKE) fixtures BOARD=$(BOARD)
	mkdir -p $(OUT)/bootlock-$(BOARD)
	$(DOCKER_RUN) $(KVM) $(TOOLS) python3 -I /src/test/qemu/bootlock.py --board $(BOARD) \
	  --fixtures /out/fx-$(BOARD) --work /out/bootlock-$(BOARD)/work \
	  --log /out/bootlock-$(BOARD)/serial.log --results /out/bootlock-$(BOARD)/results.json; \
	  rc=$$?; rm -f $(OUT)/bootlock-$(BOARD)/work/disk.img; exit $$rc

# Go back to the previous OS version (test/qemu/rollback.py, CRITERIA-ROLLBACK.md, P-16): a good update, then an
# approved os-rollback through the host service boots the old slot and the gate commits it. Copies the fixture disk.
rollback:
	@test -f $(OUT)/fx-$(BOARD)/disk.img || $(MAKE) fixtures BOARD=$(BOARD)
	mkdir -p $(OUT)/rollback-$(BOARD)
	$(DOCKER_RUN) $(KVM) $(TOOLS) python3 -I /src/test/qemu/rollback.py --board $(BOARD) \
	  --fixtures /out/fx-$(BOARD) --work /out/rollback-$(BOARD)/work \
	  --log /out/rollback-$(BOARD)/serial.log --results /out/rollback-$(BOARD)/results.json; \
	  rc=$$?; rm -rf $(OUT)/rollback-$(BOARD)/work; exit $$rc

# Edge profile (test/qemu/edge.py, CRITERIA-EDGE.md, #751): first boot as an edge (role leaf), no hub services,
# the gate's leaf check, a good and a bad update. Needs fixtures made with EDGE=1 (the bad-leaf bundle), fresh:
# `make battery` boots the fixture disk itself and leaves it updated, so run `edge` first or remake the fixtures.
.PHONY: edge
edge:
	@test -f $(OUT)/fx-$(BOARD)/disk.img || $(MAKE) fixtures BOARD=$(BOARD) EDGE=1
	mkdir -p $(OUT)/edge-$(BOARD)
	$(DOCKER_RUN) $(KVM) $(TOOLS) python3 -I /src/test/qemu/edge.py --board $(BOARD) \
	  --fixtures /out/fx-$(BOARD) --work /out/edge-$(BOARD)/work \
	  --log /out/edge-$(BOARD)/serial.log --results /out/edge-$(BOARD)/results.json; \
	  rc=$$?; rm -f $(OUT)/edge-$(BOARD)/work/disk.img; exit $$rc

# Signed host extensions only (test/qemu/sysextguard.py, T-W19-01 for #186 and founder decision Z-22): unsigned,
# wrongly signed and directory extensions must never merge after a reboot or an A/B slot switch. Copies the
# fixture disk like `firstboot`; throwaway keys are made inside the guest and never leave it.
sysextguard:
	@test -f $(OUT)/fx-$(BOARD)/disk.img || $(MAKE) fixtures BOARD=$(BOARD)
	mkdir -p $(OUT)/sysextguard-$(BOARD)
	$(DOCKER_RUN) $(KVM) $(TOOLS) python3 -I /src/test/qemu/sysextguard.py --board $(BOARD) \
	  --fixtures /out/fx-$(BOARD) --work /out/sysextguard-$(BOARD)/work \
	  --log /out/sysextguard-$(BOARD)/serial.log --results /out/sysextguard-$(BOARD)/results.json; \
	  rc=$$?; rm -f $(OUT)/sysextguard-$(BOARD)/work/disk.img; exit $$rc

# Memory pressure (test/qemu/memorypressure.py, CRITERIA-MEMORY.md): a 6 GiB hog on an 8 GiB hub VM; the gateway
# /healthz must stay up. Copies the fixture disk like `firstboot`; needs KVM and 8 GiB free for the VM.
.PHONY: memory-test
memory-test:
	@test -f $(OUT)/fx-$(BOARD)/disk.img || $(MAKE) fixtures BOARD=$(BOARD)
	mkdir -p $(OUT)/memory-$(BOARD)
	$(DOCKER_RUN) $(KVM) -e ONEMIND_QEMU_MEM=8192 $(TOOLS) python3 -I /src/test/qemu/memorypressure.py --board $(BOARD) \
	  --fixtures /out/fx-$(BOARD) --work /out/memory-$(BOARD)/work \
	  --log /out/memory-$(BOARD)/serial.log --results /out/memory-$(BOARD)/results.json; \
	  rc=$$?; rm -f $(OUT)/memory-$(BOARD)/work/disk.img; exit $$rc


# Encrypted data (test/qemu/dataenc.py, CRITERIA-DATAENC.md). Needs fixtures made with DATA_FS=luks2.
dataenc:
	@test -f $(OUT)/fx-$(BOARD)/disk.img || $(MAKE) fixtures BOARD=$(BOARD) UPTO=T5 DATA_FS=luks2
	mkdir -p $(OUT)/dataenc-$(BOARD)
	$(DOCKER_RUN) $(KVM) $(TOOLS) python3 -I /src/test/qemu/dataenc.py --board $(BOARD) \
	  --fixtures /out/fx-$(BOARD) --work /out/dataenc-$(BOARD)/work \
	  --log /out/dataenc-$(BOARD)/serial.log --results /out/dataenc-$(BOARD)/results.json $(DATAENC_ARGS); \
	  rc=$$?; rm -f $(OUT)/dataenc-$(BOARD)/work/disk.img; exit $$rc

# Local KVM check of F0-F4 (build + fixtures + firstboot); see test/qemu/README.md "Local first boot".
.PHONY: local-firstboot
local-firstboot:
	test/qemu/local-firstboot.sh BOARD=$(BOARD) FUPTO=$(FUPTO)

# Secure Boot + signed UKI (S-13, os/secureboot/README.md): a test image on the efi route with signed UKIs, then SB1-SB7
# under OVMF Secure Boot with throwaway keys. KVM host (CI image workflow) for the SB1 gate; TCG is BLOCKED-slow.
secureboot-image: tools
	@test -f $(OUT)/rootfs-$(LEG)-x86_64-efi.tar || $(MAKE) rootfs BOARD=x86_64-efi LEG=$(LEG)
	$(DOCKER_RUN) $(TOOLS) /src/test/qemu/secureboot-image.sh /out/rootfs-$(LEG)-x86_64-efi.tar /out/secureboot-image

secureboot-test:
	@test -f $(OUT)/secureboot-image/disk.img || $(MAKE) secureboot-image BOARD=x86_64-efi
	mkdir -p $(OUT)/secureboot-x86_64-efi
	$(DOCKER_RUN) $(KVM) $(TOOLS) python3 -I /src/test/qemu/secureboot.py --disk /out/secureboot-image/disk.img \
	  --keys /out/secureboot-image --work /out/secureboot-x86_64-efi/work --log /out/secureboot-x86_64-efi/serial.log \
	  --results /out/secureboot-x86_64-efi/results.json; rc=$$?; rm -rf $(OUT)/secureboot-x86_64-efi/work; exit $$rc

convert: tools
	$(DOCKER_RUN) $(TOOLS) /src/os/assemble/convert.sh /out/image-$(BOARD)

hygiene:
	scripts/hygiene.sh

hygiene-selftest:
	scripts/hygiene-selftest.sh

lint:
	scripts/lint.sh

test:
	python3 -I -m unittest discover -s test/unit -v

kit:
	@test -n "$(LT)" || { echo "usage: make kit LT=LT-X86-01"; exit 1; }
	@cat lab-kits/$(LT)/README.md

clean:
	rm -rf $(OUT)

# USB installer (os/boards/installer-x86_64/README.md): a live stick that writes the target board's
# image to an internal disk, verified by sha256, with the first-boot role set.
#   make installer      BOARD=installer-x86_64   -> out/installer-x86_64/ (stick .img, SHA256SUMS)
#   make installer-test BOARD=installer-x86_64   -> out/test-installer-x86_64/ (I1-I5, CRITERIA-INSTALLER.md)
TARGET_OF   = $(shell sed -n 's/^target_board: *\([^ #]*\).*/\1/p' os/boards/$(BOARD)/board.yaml)
.PHONY: installer installer-test
installer: tools
	@test -n "$(TARGET_OF)" || { echo "usage: make installer BOARD=installer-x86_64"; exit 1; }
	@test -f $(OUT)/image-$(TARGET_OF)/SHA256SUMS || $(MAKE) image BOARD=$(TARGET_OF)
	docker buildx build -f os/boards/$(BOARD)/Containerfile --platform $(PLATFORM) $(LEG_ARGS) \
	  --output type=tar,dest=$(OUT)/rootfs-$(BOARD).tar .
	$(DOCKER_RUN) $(TOOLS) /src/os/boards/$(BOARD)/build.sh /out/rootfs-$(BOARD).tar /out/image-$(TARGET_OF) /out/$(BOARD)

installer-test:
	@test -f $(OUT)/$(BOARD)/SHA256SUMS || $(MAKE) installer BOARD=$(BOARD)
	mkdir -p $(OUT)/test-$(BOARD)
	$(DOCKER_RUN) $(KVM) $(TOOLS) python3 -I /src/test/qemu/installer.py --stick-dir /out/$(BOARD) \
	  --image-dir /out/image-$(TARGET_OF) --work /out/test-$(BOARD)/work \
	  --log /out/test-$(BOARD)/serial.log --results /out/test-$(BOARD)/results.json; \
	  rc=$$?; rm -f $(OUT)/test-$(BOARD)/work/target.img; exit $$rc

# Jetson Orin (os/boards/jetson-orin/README.md): only the OneMind layer is built here (arm64, Docker in
# the Lima VM or CI). The flash package is built on the owner's x86 Linux host from NVIDIA's own files.
.PHONY: jetson-layer
jetson-layer: | $(OUT)
	os/boards/jetson-orin/make-layer.sh $(OUT) $(VERSION)

# Cloud images (docs/leap/core/CLOUD-IMAGES.md): one `cloud` rootfs (amd64), one image per cloud in
# the format that cloud imports. Uploads are os/cloud/*-import.sh scripts run with the owner's accounts.
#   make cloud-image CLOUD=aws|gcp|azure|hetzner|proxmox -> out/image-cloud-<cloud>/ (+ SHA256SUMS)
#   make cloud-test  CLOUD=aws                           -> out/cloudboot-<cloud>/ (C0-C6, CRITERIA-CLOUD.md)
CLOUD ?= aws
.PHONY: cloud-image cloud-test
cloud-image cloud-test: BOARD = cloud
cloud-image: tools
	@test -f $(OUT)/rootfs-$(LEG)-cloud.tar || $(MAKE) rootfs BOARD=cloud LEG=$(LEG)
	$(DOCKER_RUN) -e VERSION=$(VERSION) -e ROOTFS=/out/rootfs-$(LEG)-cloud.tar $(TOOLS) \
	  /src/os/cloud/cloud-image.sh $(CLOUD) /out/image-cloud-$(CLOUD)

cloud-test:
	@test -f $(OUT)/image-cloud-$(CLOUD)/SHA256SUMS || $(MAKE) cloud-image CLOUD=$(CLOUD)
	mkdir -p $(OUT)/cloudboot-$(CLOUD)
	$(DOCKER_RUN) $(KVM) $(TOOLS) python3 -I /src/test/qemu/cloudboot.py --cloud $(CLOUD) \
	  --image-dir /out/image-cloud-$(CLOUD) --work /out/cloudboot-$(CLOUD)/work \
	  --log /out/cloudboot-$(CLOUD)/serial.log --results /out/cloudboot-$(CLOUD)/results.json

# Raspberry Pi 5 (os/boards/rpi5, docs/leap/core/IMAGES.md §8). QEMU cannot boot the Pi firmware, so
# CI checks the image's structure; the boot itself is lab kit LT-PI5-01.
#   make rpi5-check                                     -> out/image-rpi5/structure.json
#   make imager-json [IMAGER_URL=https://...]           -> out/image-rpi5/os_list.json (rpi-imager --repo)
IMAGER_URL ?= https://github.com/onemindos/ONEMINDOS/releases/download/v$(VERSION)
.PHONY: rpi5-check imager-json
rpi5-check imager-json: BOARD = rpi5
rpi5-check:
	$(DOCKER_RUN) $(TOOLS) sh -c 'cd /out/image-rpi5 && i=$$(ls onemind-rpi5-*.img | head -n1) && \
	  python3 -I /src/os/boards/rpi5/check-image.py "$$i" --bundle "$${i%.img}.raucb" --keyring dev-ca.cert.pem --json structure.json'

imager-json:
	$(DOCKER_RUN) $(TOOLS) sh -c 'cd /out/image-rpi5 && i=$$(ls onemind-rpi5-*.img | head -n1) && \
	  python3 -I /src/os/boards/rpi5/imager_json.py --img "$$i" --xz "$$i.xz" --url-base "$(IMAGER_URL)" --out os_list.json && cat os_list.json'
