---
pr: pending
branch: claude/fnd-machine-profile-probe
---
Every machine now reports one hardware profile (NodeCapabilities, issue 618) in its heartbeat: the data disk (SSD or not), memory and whether it is unified, accelerators (NVIDIA, AMD and Intel GPUs, Intel NPU, Hailo, the Jetson GPU) with VRAM, compute capability and driver, USB devices by vendor and product id, serial lines, Wi-Fi, Bluetooth and cellular radios, USB and CSI cameras, power source and thermal state. It is read from sysfs and /proc (nvidia-smi only for VRAM), every field is a value or null for unknown, never a guess, and no serial number, MAC or IP is included. The gateway serves it on GET /v1/nodes under nodes:read (a child cannot read it), the API contract and SDKs describe it, and `onemind node capabilities` prints it for this machine. VM device grants, radio detection, edge model fit and app verdicts read this one document instead of probing again.
