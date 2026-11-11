# Outreach drafts · W16 (for Zeus to send; never sent by the research agent)

**Date:** 2026-11-10 · **Report:** `../17-business-licensing-gtm.md` §10 · **Public repo:** do not fill in names, emails or company details here. Copy each draft to a local, git-ignored `*.filled.md` first. Placeholders are in `[[ ]]`.
Each draft lists the claim IDs it is trying to resolve, so that answers can be recorded in the claims ledger.

---

## 1. NVIDIA: Inception programme team (after incorporation)

**Channel:** the Inception portal or the programme contact listed on the Inception FAQ page. **Resolves:** W16-N1, Q189, Q59/C-W7-056, C-REF-DC-cost-007.

> Subject: Inception member question: Jetson pricing and redistribution for a OneMind OS appliance
>
> Hello,
>
> [[Company]] builds OneMind OS, an open-source (Apache-2.0) operating system for self-hosted servers and robots. We plan Jetson Orin/Thor-based "Robotics" devices that ship with a OneMind image derived from Jetson Linux (L4T) and JetPack.
>
> 1. Does Inception preferred pricing apply to Jetson modules or developer kits, or only to the enterprise GPUs mentioned in the FAQ?
> 2. Can a product company preinstall a modified Jetson Linux image, with the BSP binaries under the Tegra Software License Agreement, on hardware it sells? Is a separate NVIDIA agreement required?
> 3. Your forum guidance says the L4T redistribution answer does not cover the Ubuntu root file system. Does NVIDIA have a recommended path for partners (for example a Canonical arrangement, or a non-Ubuntu rootfs such as Yocto/OE4T)?
> 4. What is the path and what are the criteria to move from Inception to an NPN OEM or Solutions Integration partner with the Embedded Systems competency?
> 5. Is there a published support or end-of-life date per Jetson Linux branch we can declare to EU customers as a support period?
>
> Thank you, [[Name]], [[Title]], [[Company]]

---

## 2. Raspberry Pi Ltd: industry / applications team

**Channel:** the Powered by Raspberry Pi application and the Design Partner form on raspberrypi.com/for-industry. **Resolves:** Q188, C-W16-036, C-W16-037.

> Subject: Powered by Raspberry Pi: OneMind OS edge kits (Pi 5 / CM5)
>
> Hello,
>
> [[Company]] is preparing Pi 5 and CM5-based edge kits (greenhouse and field nodes) running OneMind OS, an Apache-2.0 operating system built on Debian 13 with Raspberry Pi's kernel and firmware.
>
> 1. What are the requirements and any fees for the Powered by Raspberry Pi logo on our product and packaging?
> 2. How does Raspberry Pi allocate Pi 5 / CM5 supply to commercial customers during shortages, and what volume or agreement qualifies?
> 3. We would like to align our device layer with the Model Hardware Standard, which Anthropic says Raspberry Pi is enabling (Camera MHS Driver). Is there a contact for MHS driver collaboration?
> 4. Is there a recommended path to a real-time (PREEMPT_RT) kernel build for BCM2712?
> 5. Do you recommend a Design Partner for a CM5 carrier board aimed at greenhouse and outdoor use?
>
> Thank you, [[Name]], [[Company]]

---

## 3. Canonical: devices / IoT sales and trademark team

**Channel:** the Ubuntu Pro for Devices "contact us" form, and the Canonical trademark contact named in the IPRights policy. **Resolves:** Q-W2-1 (01), Q168, DC-03, C-W2-006, C-W2-050.

> Subject: Redistribution approval and Pro for Devices quote: OneMind OS appliances
>
> Hello,
>
> [[Company]] builds OneMind OS, an Apache-2.0 appliance OS. Our main image is Debian-based. We are evaluating Ubuntu for two flavours: (a) NVIDIA Jetson devices running NVIDIA's Ubuntu 24.04-based Jetson Linux, and (b) an x86 GPU-server flavour on Ubuntu LTS.
>
> 1. Under the IPRights Policy, what approval or certification would let us redistribute a modified Ubuntu image, preinstalled, on devices we sell under our own brand? What does it cost, and does it cover NVIDIA's L4T root file system?
> 2. Please quote Ubuntu Pro for Devices per device for 1,000, 10,000 and 100,000 units, annual and one-time, including the 10-year and 15-year (Legacy) options.
> 3. Does Pro for Devices cover the NVIDIA Jetson (L4T) kernel, or only Canonical-built kernels?
> 4. Can units be activated offline, for devices that are never connected to the internet?
>
> Thank you, [[Name]], [[Company]]

---

## 4. Anthropic: Model Hardware Standard research preview (revised pitch)

**Channel:** the "Apply for access" form linked from modelhardwarestandard.com. **Resolves:** D-006, N-10, AI-2. Replaces the free-text pitch in `docs/applications/anthropic-mhs-preview.md`, because the preview targets labs and advanced manufacturers (C-W16-037).

> OneMind OS is an open-source (Apache-2.0) operating system that integrates devices: it connects Raspberry Pi controllers, NVIDIA Jetson robots, drones (MAVLink), industrial I/O (Modbus, OPC UA, CAN) and sensors to AI agents through one permissioned MCP/CLI/API gateway, with human approval for physical actions and full audit.
>
> We would like to implement MHS as the device-control layer of that gateway and contribute:
> - MHS drivers for common maker and agricultural hardware on Raspberry Pi (pumps, valves, environmental sensors), complementing Raspberry Pi's Camera MHS Driver;
> - a ROS 2 / MAVLink bridge exposing robots and drones as MHS devices with declared safety limits;
> - safety-evaluation data from offline and intermittently connected deployments (safe states, command expiry, no blind replay after reconnect).
>
> Our test environments include greenhouse/agricultural automation and field robotics. [[Company]], [[website]].

---

## Not drafted here (owned elsewhere)

Freexian ELTS arm64 quote and Red Hat Device Edge on Orin: called for by the Tier A critic (#12) in `evidence/outreach-drafts.md`, which belongs to W2/W6.
