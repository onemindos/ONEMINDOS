---
pr: pending
branch: feat/153-tuf-ceremony
---
The root key ceremony (D-010, #153) is ready for Zeus to run. `scripts/tuf-bootstrap-root.sh rehearse` now does the whole real shape on throwaway keys (three passphrase-protected root keys, 2-of-3 signing with one holder absent, the online keys, an inspection of the result and a signed test release checked as a box would), and new `root-key`, `online-keys` and `check` commands plus `create` with an absent holder's public key are what the real ceremony uses. Keys are never overwritten and a second `create` never replaces a root. A runbook (`os/update/CEREMONY.md`) and a one-page printable checklist go with it. No agent holds a real root key; the real `create` stays with Zeus and the three encrypted sticks.
