# SPDX-License-Identifier: Apache-2.0
# OneMind OS build entry points (brief 30 §5, D-B1.2). Everything heavy runs in containers built
# from os/rootfs/Containerfile, so the Mac only needs Docker (or the Lima VM, handbook/workbench.md).
#
#   make rootfs  BOARD=x86_64-efi [LEG=debian|ubuntu]   -> out/rootfs-<leg>-<board>.tar
#   make image   BOARD=x86_64-efi [VERSION=...]         -> out/image-<board>/ (disk .img, .raucb, SHA256SUMS)
#   make fixtures BOARD=x86_64-efi [UPTO=T5] [HW=1]     -> out/fx-<board>/ (battery inputs; HW=1 for founder kits)
#   make battery BOARD=x86_64-efi [UPTO=T5]             -> out/battery-<board>/ (serial log, results.json)
#   make firstboot BOARD=x86_64-efi [FUPTO=F4]          -> out/firstboot-<board>/ (F0-F4, CRITERIA-FIRSTBOOT.md)
#   make convert BOARD=vm                               -> qcow2 / vhdx / vmdk / vdi / ova next to the image
#   make hygiene | hygiene-selftest | lint | test | kit LT=LT-X86-01
SHELL      := /bin/bash
BOARD      ?= x86_64-efi
LEG        ?= debian
UPTO       ?= T5
HW         ?= 0
FUPTO      ?= F4
VERSION    ?= 0.1.0-dev
OUT        ?= out
ARCH_OF     = $(shell sed -n 's/^arch: *//p' os/boards/$(BOARD)/board.yaml)
PLATFORM    = linux/$(ARCH_OF)
LEG_ARGS    = $(shell sed -n 's/^\([A-Z]*=.*\)/--build-arg \1/p' os/rootfs/$(LEG).args)
TOOLS      ?= onemind-tools:$(ARCH_OF)
ROOTFS      = $(OUT)/rootfs-$(LEG)-$(BOARD).tar
DOCKER_RUN  = docker run --rm --platform $(PLATFORM) -v "$(CURDIR)":/src:ro -v "$(CURDIR)/$(OUT)":/out
KVM         = $(shell [ -w /dev/kvm ] && echo --device /dev/kvm)

.PHONY: help tools rootfs image fixtures battery firstboot convert hygiene hygiene-selftest lint test kit clean

help:
	@sed -n 's/^#   make/make/p' Makefile

$(OUT):
	mkdir -p $(OUT)

tools: | $(OUT)
	docker image inspect $(TOOLS) >/dev/null 2>&1 || docker buildx build -f os/rootfs/Containerfile --target tools --platform $(PLATFORM) \
	  $(shell sed -n 's/^\([A-Z]*=.*\)/--build-arg \1/p' os/rootfs/debian.args) --load -t $(TOOLS) .

rootfs: | $(OUT)
	docker buildx build -f os/rootfs/Containerfile --target rootfs --platform $(PLATFORM) \
	  --build-arg BOARD=$(BOARD) $(LEG_ARGS) --output type=tar,dest=$(ROOTFS) .
	@ls -la $(ROOTFS)

# A development image, signed with a throwaway CA made here and deleted after use (SB-10).
image: tools
	@test -f $(ROOTFS) || $(MAKE) rootfs BOARD=$(BOARD) LEG=$(LEG)
	$(DOCKER_RUN) -e VERSION=$(VERSION) -e BOARD=$(BOARD) -e ROOTFS=/out/$(notdir $(ROOTFS)) $(TOOLS) \
	  /src/os/assemble/dev-image.sh /out/image-$(BOARD)

fixtures: tools
	@test -f $(ROOTFS) || $(MAKE) rootfs BOARD=$(BOARD) LEG=$(LEG)
	$(DOCKER_RUN) -e HW=$(HW) $(TOOLS) /src/test/qemu/mkfixtures.sh $(BOARD) /out/$(notdir $(ROOTFS)) /out/fx-$(BOARD) $(UPTO)

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
