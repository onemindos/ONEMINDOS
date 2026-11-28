---
pr: 1188
branch: claude/update-signed-e2e
---
Adds make update-signed (test/qemu/updatesigned.py, pre-registered CRITERIA-UPDATE-SIGNED.md US0-US6): the end-to-end proof of a signed update through the real update path. A throwaway TUF root of the ceremony's shape is baked into the image, channels are published with the nightly's own publisher (os/update/tuf-repo.py) and served over HTTP, and the box's own `onemind update` engine installs the good signed bundle, reboots into the new slot and passes the health gate, while a tampered bundle, metadata signed by untrusted keys, a bundle signed by a wrong RAUC key, a replay of older metadata and an older version are all refused. The same channel sequence also runs in seconds through the box's go-tuf verifier in CI (TestSignedChannelSequence).
