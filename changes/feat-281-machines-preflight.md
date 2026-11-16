---
pr: 296
branch: feat/281-machines-preflight
---
Virtual machines get their first gateway piece (MACH-01, #281 part 1): the preflight. `GET /v1/machines/capabilities` says, for every node, whether it can run machines and the plain-language reasons it cannot, and `POST /v1/machines/enable` is the owner's switch, refused with those reasons on a Raspberry Pi, a box under 16 GB, a box without KVM, a box that is itself a VM and anything that is not the x86 hub. Only an owner can ask; agents, adults and guests get 403. Nothing is installed yet: the KubeVirt extension and the machine actions follow once LT-MACH-2 has measured them on real KVM hardware.
