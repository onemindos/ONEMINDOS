---
pr: 256
branch: fix/flaky-installer-readback
---
Fixes a flaky installer unit test: it changed byte 5 of a random test image to zero, which did nothing about 1 run in 256 (when that byte was already zero), and it knocked PR 225 out of the merge queue. The test now flips the byte, so the change is always real.
