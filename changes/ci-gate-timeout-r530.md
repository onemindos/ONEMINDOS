---
pr: pending
branch: ci/gate-timeout-r530
---
The `merge-gate` check now waits up to 320 minutes (was 170), so pull requests whose x86 image, battery and cloud jobs run on the R530 KVM runner (CI-14, 3.5 to 4 hours on 5 or 6 job VMs) no longer time out while those jobs are still running. A gate whose workflows finish early still passes early.
