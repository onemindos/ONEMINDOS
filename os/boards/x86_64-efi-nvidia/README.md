<!-- SPDX-License-Identifier: Apache-2.0 -->
# x86_64-efi-nvidia: the GPU image (S-5)

The normal x86 image plus what a graphics card (GPU) needs to run AI models for apps such as Ollama. Build it with
`make image BOARD=x86_64-efi-nvidia`. The default image (`BOARD=x86_64-efi`) is unchanged and has none of this.

## Why a separate board and not a switch inside the default image

- **Closed code stays opt-in.** NVIDIA's driver is closed source. Debian keeps it in `non-free`, a part of the archive
  the default image never enables. Only this board turns it on, only for the install step, and puts the stock sources back.
- **A box can only get updates built for it.** The board has its own RAUC `compatible` string, so a GPU box never takes
  an update built without the driver, and the other way round (the update would boot, but the GPU would be gone).
- **Nothing compiles on the box.** The kernel modules are built during the image build for the image's own kernel
  (DKMS, the standard Debian way), so the read-only root never needs a compiler at runtime.

## What is in it

| Piece | Where it comes from | Pinned by |
|---|---|---|
| NVIDIA driver 550 (headless: modules, `nvidia-smi`, CUDA library) | Debian 13 `non-free` (plus `contrib` and `non-free-firmware` for its dependencies), same snapshot as the rest | the snapshot date (`os/versions.lock.yaml`) |
| NVIDIA Container Toolkit 1.19.1 (lets a container see the GPU) | NVIDIA's apt repository, which Debian does not mirror | sha256 of each file (`gpu/toolkit.txt`, `gpu.toolkit` in the lock) |
| `nvidia` RuntimeClass + NVIDIA device plugin v0.20.2 (tells Kubernetes the node has `nvidia.com/gpu`) | `rootfs/usr/lib/onemind/gpu/onemind-gpu.yaml` | image digest |

Licences: `gpu/licences.txt` has a row for every package (the build and `test/unit/test_gpu_variant.py` refuse a package
without one). The list ships in the image as `/usr/lib/onemind/gpu-licences.txt` and the packages are in
`/usr/lib/onemind/packages.txt`, the image's package list. `/usr/lib/onemind/gpu-info.txt` records `gpu=nvidia`, the driver and the kernel.

## What happens on a machine with no NVIDIA card

`onemind-nvidia-setup.service` runs before k3s. With no NVIDIA card on the PCI bus it loads nothing, removes the device
plugin manifest and succeeds, so the box is a normal OneMind box. An app that needs a GPU is then refused at install time
with a plain sentence (`core/onemind_core/gpufit.py`, called from `cpufit.refusal`), not started and left crashing.

## How an app asks for a GPU

In `onemind.app.yaml`, vendor-neutral (schema: `sdk/schema/onemind.app.schema.json`, `spec.requires.accelerator`):

```yaml
requires:
  gpu: true                                   # a hard need: refused on a box with no GPU
  accelerator: {capability: gpu-compute, minMemoryMb: 8192}
```

or, like Ollama, faster with a GPU but fine without:

```yaml
requires:
  gpu: false
  accelerator: {capability: gpu-compute, minMemoryMb: 4096, optional: true, overlay: manifests-gpu}
```

## Not done yet (follow-ups)

- The first real boot: `test/gpu/gpu-lab-kit.sh` on a rented GPU machine. Until it passes, the package names and the
  DKMS step are UNVERIFIED on hardware, and this board is not in the CI image matrix on purpose (no GPU in CI).
- The executor rendering the `overlay` for a box with a GPU (today the overlay is validated and the lab kit applies it by hand).
- onemindd reporting the GPU's memory (`gpu.memory_mb`), so `minMemoryMb` can be enforced. Without it the size is not guessed.
- Placement on other nodes (PR 400) using the same mapping, and limiting the device plugin to GPU nodes in a multi-node cluster.
- Bundling the device plugin image for air-gapped installs, and removing the compiler and headers from the image after the module build.
- An open-kernel-module option (RTX 20 series and newer) and Secure Boot signing of the modules.
