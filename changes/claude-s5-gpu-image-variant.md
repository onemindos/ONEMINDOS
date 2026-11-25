---
pr: pending
branch: claude/s5-gpu-image-variant
---
First slice of the GPU image variant (S-5). A new board x86_64-efi-nvidia builds the normal x86 image plus the NVIDIA driver (built for the image's kernel at build time), the NVIDIA container toolkit pinned by file hash, the nvidia RuntimeClass and NVIDIA's device plugin pinned by digest, with every closed package and its licence recorded in the image; the default image contains none of it. An app manifest can now declare the accelerator it needs in vendor-neutral words (capability gpu-compute, minimum accelerator memory, optional, an overlay directory), and installing an app that needs a GPU on a box that has none is refused with a plain sentence instead of a pod that never starts. Ollama declares an optional GPU and ships a GPU overlay. A lab kit for a rented GPU machine is the first real test.
