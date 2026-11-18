---
pr: pending
branch: feat/215-g1-metal-kit
status_rows:
  - CORE-UPDATE-4 | in-review | kit only; the metal run is the founder's step
---
Adds lab-kits/G1: a resumable on-box runner (g1-run.py) that drives the LT-X86-01 update sequence (refused bundles, good commit, bad-k3s, bad-noagent, bad-boot, bad-hang, 10 chaos rollbacks), reads the image's own gate log for each verdict, writes result.json, starts the 4 GB Pi soak record, and fills a G1 record template. Proven with a fake rauc and systemctl in unit tests; not run on hardware and it never claims G1 passed.
