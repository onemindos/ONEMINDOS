---
pr: pending
branch: claude/281-vms-x86
status_rows:
  - UMB-MACH-4 | in-progress | gateway console broker; the dashboard noVNC screen and a run on KVM hardware are left
---
Machines (MACH-01, #281 part 4): the console broker. An owner's console ticket now opens a WebSocket at /v1/machines/NAME/console/ws that carries the machine's VNC display. A ticket works once, for its machine, within a minute, and a page from another site cannot use it. A second console takes over from the first, a view-only console drops keyboard, pointer and clipboard messages and closes on anything it cannot read, a client that stops reading is cut at 8 MB instead of growing memory, and the audit log records who opened and closed a console but never the screen or keystrokes. The display comes from KubeVirt through a loopback kubectl proxy, which is not yet checked on real KVM hardware (LT-MACH-2); a box with the noop executor closes the console with a plain reason.
