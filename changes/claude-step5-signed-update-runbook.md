---
pr: 1178
branch: claude/step5-signed-update-runbook
---
Adds os/update/STEP5-SIGNED-UPDATE.md, the one-page Step 5 runbook: the key ceremony on an offline computer (YubiKey root, RAUC CA and signer), publishing the trust, building the Dell's image so it trusts those keys, publishing the first real signed update through security-nightly, and watching the Dell install it and go back. Also closes the gap that blocked it: make image KEYRING=<public RAUC CA cert> builds an install image that trusts the real RAUC CA (only the public certificate is used; no key is made or read and no bundle is written), where before every image trusted a throwaway CA.
