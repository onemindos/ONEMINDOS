---
pr: 521
branch: claude/sec-update-root-rotation
---
Two update-engine security fixes. A TUF root rotation now sticks: the box keeps each root it accepted and re-verifies the chain from the image root on every check, so a mirror that answers 404 for the next root can no longer bring revoked keys back. A failed rauc install now removes the trial marker it left behind, so the box no longer reboots into a trial that never started and the release is not marked image-bad.
