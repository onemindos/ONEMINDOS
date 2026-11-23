---
pr: 976
branch: claude/roots-device-grant
---
Device grants for machines, part 1 (#690): on a box with VT-d or AMD-Vi switched on, the hardware profile now carries a passthrough section that lists the IOMMU group of each graphics card and the kernel drivers holding each USB device, read from the same /sys tree as the rest of the profile. The gateway's profile gate takes the section and drops a profile that plants a path or a malformed name in it. Part 2 uses it for the owner-approved machine.attach_device and machine.detach_device actions.
