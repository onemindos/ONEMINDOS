<!-- SPDX-License-Identifier: Apache-2.0 -->
# Lab ACCT-1: Kanidm as a host service on the hub

**Serves:** UMB-ACCT-1 (`docs/umbrel2/accounts.md` §5, ACCT-1); decision **D-015** (F-34: Kanidm runs as a systemd host service on the hub OS, not in k3s); BD-03 (Kanidm is the identity provider); brief 30 D-B9.1 and the footprint note in its §"not measured". Unblocks ACCT-3 and, through it, #236 (SEC-SSO-01).

> **In plain words.** Install Kanidm v1.12.0 on a fresh Debian 13 machine as an ordinary system service, the way the hub will run it. Then prove the things OneMind's sign-in design depends on: the owner can sign up with a passkey with no internet, household groups and app logins (OIDC) work, guests expire, a reused one-time code is refused, and a backup restored onto a fresh install still accepts the same passkey. Measure how much memory and disk it uses.

## 1. Setup (fixed before the run)

- **Machine:** a fresh Debian 13 VM (any host; record CPU arch, vCPU, RAM). A VM is preferred over WSL because AK-2 needs the network really cut. If WSL is used, say so in Results and treat AK-2 as weaker evidence.
- **Software:** Kanidm **v1.12.0** (`kanidmd` server and the `kanidm` CLI), installed as a systemd unit on the host, not in a container runtime managed by k3s. Record the exact install method, artifact URLs and their sha256.
- **Domain:** one fixed test domain for the whole run (ACCT-D1: a passkey is bound to its domain, and Kanidm's documentation warns that changing the domain invalidates passkeys). The restore in AK-7 uses the same domain.
- **TLS:** a local test CA; no real certificates, no private IPs or host paths in committed files (mask them as in other labs).
- **Human steps:** AK-2 and AK-7 need a real passkey (phone or security key) or a browser virtual authenticator. A virtual authenticator counts for PASS; record which was used.

## 2. Tests and pass criteria (written before any build or run)

| ID | Test | PASS when |
|---|---|---|
| AK-1 | Host service | `kanidmd` runs as a systemd unit, starts at boot, and its health check answers over HTTPS; `systemctl is-active` is `active` after a reboot; no k3s or container runtime is needed for it to run |
| AK-2 | Offline first boot | with all network interfaces except loopback down (cable out), the owner account is created and a passkey is enrolled, and the owner can then sign in with that passkey, still offline |
| AK-3 | Household groups | groups `onemind_owners`, `onemind_adults`, `onemind_children`, `onemind_guests` exist; one test person in each; each person's group membership is readable through the API the gateway would use |
| AK-4 | OIDC client with group scope map | an OAuth2/OIDC client is created for a test app; its scope map gives the app a different claim or scope for at least two of the groups; an auth-code + PKCE sign-in returns an ID token whose claims show the person's group; a person in no mapped group is refused |
| AK-5 | Credential-reset link | an admin issues a credential-reset link for a person; the person uses it to enrol a new credential; the link cannot be used a second time |
| AK-6 | Account expiry | a guest account with an expiry a few minutes ahead can sign in before it and is refused after it (sign-in fails; an existing session is no longer accepted for new tokens) |
| AK-7 | Backup and restore | an online backup is taken while the service runs; a fresh Debian 13 install with the same domain restores it; on the restored box the **same** owner passkey from AK-2 signs in |
| AK-8 | TOTP replay | a person with TOTP as a fallback signs in with a valid code; the **same** code used again within its time step is refused |
| AK-9 | Footprint (informative) | recorded, not judged: idle RSS of `kanidmd` after start and after AK-3 to AK-6, peak RSS during AK-7, on-disk size of the install and the database. Brief 30 says this result decides nothing alone; if it looks too large for the 4 GB slim profile next to the gateway and PostgreSQL, say so and propose an option, without switching identity provider |
| AK-10 | Revocation reaches apps | after the person from AK-4 is removed from the mapped group (or disabled), a new OIDC sign-in to the test app is refused. This is #236's second done-when, checked at the identity-provider level |

**Verdict rule:** PASS = AK-1 to AK-8 and AK-10 pass in one full run on a fresh machine. AK-9 is informative. Any FAIL is reported with the command, its output and the Kanidm version; a FAIL goes to the founder with evidence, and the identity provider is not switched by the agent (BD-03, D-015).

**Not in scope:** packaging into the OS image (`os/**`, image stream), the gateway's identity module (ACCT-3), forward-auth (#139), and the identity-domain choice itself (ACCT-D1, tested by ACCT-T1).

## 3. What to commit with the results

- This README with a `## Results` section appended **below** the line that follows; nothing above it changes after the freeze (see `../PREREGISTRATION.md`).
- `run-1/`: one file per test with the commands run and their real outputs, a `results.json`, and `SHA256SUMS`.
- Anything not run is written as **NOT RUN** with the reason; no result is invented.

## Results
