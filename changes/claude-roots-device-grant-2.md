---
pr: 985
branch: claude/roots-device-grant-2
---
Device grants for machines, part 2 (#690): the owner-approved actions machine.attach_device and machine.detach_device hand a USB device or a spare graphics card to a virtual machine, and the change applies the next time the machine starts (KubeVirt permittedHostDevices plus the machine's own device list). A device the box is using is refused until the owner confirms, a graphics card sharing its IOMMU group is refused, and an agent can ask but never confirm or approve. GET /v1/machines/{name}/devices lists every device with who holds it and why a grant is refused. Machines stay gated off until LT-MACH-2; lab kit LT-MACH-DEV-01 is the real VT-d test.
