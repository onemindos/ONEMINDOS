---
pr: pending
branch: feat/281-machine-actions
---
Machines (MACH-01, #281 part 3): create, start, stop and delete a virtual machine are now actions an owner approves (`machine.create`, `machine.start`, `machine.stop`, `machine.delete`). An agent may request them and never approve them, a Pi or a box under 16 GB refuses a create with a reason, each machine has a RAM and CPU quota while the box keeps 4 GB and a core for the system, and a machine starts with a default-deny network. `GET /v1/machines`, `GET /v1/machines/{name}`, an owner-only console ticket and the `onemind machines` commands make it reachable. The KubeVirt objects are applied with kubectl only after approval; the extension install, the console broker and the dashboard screen are not built yet, and LT-MACH-2 on real KVM hardware has a lab kit but has not been run.
