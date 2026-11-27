---
pr: 1141
branch: claude/lab-umb-acct-1
status_rows:
  - UMB-ACCT-1 | in-review | run 2 is lab evidence for F-33 option (a), F-33 stays open; TOTP replay still fails
---
Lab run 2 (virtual authenticator, simulated paths, test plan not pre-registered; it does not settle F-33, which stays open for the founder and UMB-ACCT-13) for the Kanidm identity test UMB-ACCT-1, done in a real browser with a virtual passkey on fresh Debian 13 machines running Kanidm v1.12.0. One canonical sign-in name (the passkey's relying-party ID) works from a simulated LAN path and a simulated mesh path with one passkey: enrolled offline with the network cut, signed in on both paths, and accepted again on a fresh machine restored from a backup. Names under the canonical domain work too, while an unrelated name could not sign in or enrol (observed without a .well-known/webauthn file; Related Origin Requests untested), so per-domain passkeys look unavailable inside one Kanidm. Groups, OIDC, reset links, expiry and revocation pass again. A reused TOTP code is still accepted, and the passkey-minimum policy only blocks new weak credentials. Evidence and scripts are under research-output/evidence/lab/acct-kanidm.
