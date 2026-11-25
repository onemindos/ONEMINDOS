<!-- SPDX-License-Identifier: Apache-2.0 -->
# Certified hardware list (S-11)

**Why.** Nobody picks an OS that has not run on a real machine. This list says, per machine, what a buyer needs to know and what has actually been proven. Nothing is proven yet, so every machine is `unproven` and `what_works` is empty on purpose.

- One file per machine: [`machines/`](machines/). Reference-box criteria for gate G1: [`reference-box.yaml`](reference-box.yaml).
- The readable table is generated: [`CERTIFIED.md`](CERTIFIED.md). Do not edit it by hand.
- Check and regenerate (needs PyYAML; see the Mac developer loop):
  `python3 -I scripts/hardware_list.py check` and `python3 -I scripts/hardware_list.py render`.
- To certify a machine: run its kit on the real machine, file the result under `research-output/evidence/lab/founder-hardware/`, then set `status: proven`, `result`, `proven_on`, `image_version`, real specs, and `what_works`. The checker refuses a proven machine without them.
- Never put addresses, MACs, serial numbers or home paths in these files.
