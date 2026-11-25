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

**Run 1, 2026-11-23 (UTC 02:36 to 03:16), counted.** Verdict: **FAIL** on one test. AK-1 to AK-7 and AK-10 **PASS** in one run on fresh machines; **AK-8 FAILS**: Kanidm v1.12.0 accepts the same TOTP code twice. AK-9 is recorded below. Per the verdict rule this goes to the founder with the evidence; the identity provider is not switched (BD-03, D-015).

> **In plain words.** Kanidm did almost everything OneMind's sign-in design needs. It ran as an ordinary system service, worked with the network cable out, kept household groups apart, gave each app the right role, expired a guest on time, and came back from a backup on a new machine with the owner's passkey still working. One thing failed: a one-time code from an authenticator app can be used twice within its 30 seconds. That matters only for people who sign in with a password plus a code, not for passkeys.

### Setup as run

| Item | Value |
|---|---|
| Machines | two VMs created fresh for this run from the Debian 13.7 genericcloud amd64 image `20261116-2664` (sha256 `edd2b3fb…1116`) on the Proxmox lab server: VM 505 (source) and VM 506 (restore target); x86_64, 2 vCPU, 4 GiB RAM, 16 GiB disk, kernel `6.12.117+deb13-cloud-amd64`. Both destroyed after the run |
| Kanidm | **v1.12.0** (`kanidmd 1.12.0 a52b723ce8`, `kanidm 1.12.0 a52b723ce8`) |
| Install method | the community PPA had only 1.11.2 for trixie, so the Debian packages were built from the v1.12.0 tag on a third, disposable Debian 13 VM with Kanidm's own packaging scripts (`kanidm_ppa_automation` at `d5327e7`, the commit the tag pins; rust 1.96.1, cargo-deb 2.11.2), then installed with `apt-get install` of the two local files. `kanidmd_1.12.0-202611010319+a52b723_amd64.deb` sha256 `31de180e…6a9e`, `kanidm_…amd64.deb` sha256 `88112601…14b7` (`run-1/build-provenance.txt`) |
| Service | the packaged unit `kanidmd.service` (`Type=notify`, `DynamicUser=yes`, `StateDirectory=kanidmd`), bound to `127.0.0.1:8443` |
| Domain | `idm.onemind.test`, origin `https://idm.onemind.test:8443`, the same on both machines |
| TLS | local test CA from `kanidmd cert-generate` |
| Authenticator | **software virtual WebAuthn authenticator** (`run-1/tools/aklab.py`, class `SoftPasskey`: P-256 key, `none` attestation, user-present and user-verified flags). It is not a phone, a security key or a browser's virtual authenticator; it talks to Kanidm's own JSON API exactly as a browser's WebAuthn response would |
| Rehearsal | the scripts were first debugged on a separate VM (508, destroyed). Its first attempt failed in the lab's own setup script (certificate generation before the state folder existed: `run-1/rehearsal-attempt-0-AK-1.txt`). Nothing from the rehearsal counts |

### Results per test

| ID | Result | What happened (evidence in `run-1/`) |
|---|---|---|
| AK-1 | **PASS** | Enabled and active after `systemctl reboot` (new boot id, `NRestarts=0`), `/status` answers `true` over HTTPS, `kanidmd scripting healthcheck` ok; no k3s or container units or binaries on the machine (`AK-1.txt`) |
| AK-2 | **PASS** | Rebooted with the virtual cable out (Proxmox `link_down=1`) and every non-loopback interface set down in the guest: no route, no DNS. Then, through the QEMU guest agent (no network): `idm_admin` recovered, person `owner` created, a passkey enrolled from a reset link, and `owner` signed in with it (`AK-2.txt`, `AK-2-hypervisor.txt`) |
| AK-3 | **PASS** | `onemind_owners`, `onemind_adults`, `onemind_children`, `onemind_guests` exist with one person each; a service account's API token reads each person's `memberof` over `GET /v1/person/{id}/_attr/memberof` (`AK-3.txt`) |
| AK-4 | **PASS** | Auth code + PKCE (S256) against a confidential client; the ES256 ID token's signature checks against the client's JWKS. Claim `onemind_role` is `owner`, `adult` or `child` by group; scope maps differ (owners may get `email`, adults `profile`, children only `openid groups`, and a child asking for `profile` is refused); the guest, in no mapped group, gets 403 (`AK-4.txt`) |
| AK-5 | **PASS** | The admin's reset link let `child1` add a password + TOTP and sign in with it; the second use of the same link was refused (`401 "sessionexpired"`) (`AK-5.txt`) |
| AK-6 | **PASS** | Guest signed in before the expiry; 30 s after it, sign-in was denied (`account expired`) and the earlier session token was refused (`401` on `/v1/self` and `/v1/auth/valid`) (`AK-6.txt`) |
| AK-7 | **PASS** | The running server wrote its scheduled online backup (same PID, `/status` true during it); a fresh Debian 13 VM with the same domain restored it (`kanidmd database restore`, 1.4 s) and the **same** owner passkey from AK-2 (credential fingerprint `58d340207caabd97` on both machines) signed in (`AK-7.txt`, `AK-7-restore-box.txt`) |
| AK-8 | **FAIL** | `adult2` signed in with password + TOTP, then signed in again with the **same** code inside the same 30 s step, and that was accepted too (`AK-8.txt`) |
| AK-9 | recorded | See the footprint table below |
| AK-10 | **PASS** | `adult1` got an ID token, was removed from `onemind_adults`, and the next OIDC authorise was refused with 403 (`AK-10.txt`) |

**Why AK-8 fails (source, v1.12.0).** `server/lib/src/credential/totp.rs`, `Totp::verify` (line 246) accepts the code of the current or the previous 30 s step and keeps no record of codes already used; `server/lib/src/idm/authsession/mod.rs` lines 512 to 518 call it with no replay check. So a code stays usable for up to about 60 s, any number of times. Passkeys are not affected (WebAuthn has its own challenge per sign-in). Options for the founder, none tested here and none switching the identity provider: (a) make passkeys the minimum credential for household groups through Kanidm's account policy (`kanidm group account-policy credential-type-minimum`, UNVERIFIED in this run), keeping TOTP off; (b) report it upstream to Kanidm and ask for a used-step record; (c) keep TOTP as a fallback and accept the window, relying on Kanidm's soft-lock against guessing.

### AK-9 footprint (informative)

| Measure | Value |
|---|---|
| `kanidmd` RSS, idle 30 s after first start | 42.5 MB (42 472 kB) |
| `kanidmd` RSS right after AK-3 to AK-6 | 67.6 MB |
| `kanidmd` peak RSS while the online backup ran (0.2 s samples and `VmHWM`) | 68.3 MB |
| `kanidmd database restore` peak RSS on the fresh VM | 36.0 MB |
| Restored `kanidmd` RSS 20 s after start | 44.0 MB |
| Installed size: `kanidmd` package / `kanidm` CLI package | 241 MiB / 111 MiB (binaries ship unstripped: Kanidm's release profile has `debug = "limited"`, `strip = "none"`) |
| `kanidmd` binary unstripped / stripped (measured on the build VM) | 251 MB / 57 MB |
| Web UI static files | 1.9 MB |
| Database folder after the run (database, WAL, 3 backups) | 5.4 MB; one gzip backup 20 KB |

Next to the gateway and PostgreSQL on the 4 GB slim profile, about 70 MB of RAM is small. Disk is the only number worth acting on: an image build could strip the binaries (about 190 MB saved for `kanidmd`: 251 MB to 57 MB) and could leave out the `kanidm` CLI on machines that do not need it.

### Notes for ACCT-3 and the image (not judged by this lab)

- **Offline boot is slow to start Kanidm.** With the cable out, `kanidmd` became active 2 min 9 s after boot because the unit waits for `network-online.target` (`AK-2.txt`). With the network up it started in 1.4 s (`AK-1.txt`). A hub that must sign people in offline may want a drop-in that does not wait for the network.
- **Persons need MFA by default.** Kanidm v1.12.0 refused to commit a password-only credential (`MfaRequired`), so every test person used a passkey or password + TOTP.
- **The gateway needs a read group.** A plain service account cannot read other persons' `memberof`; `idm_account_mail_read` is the narrowest built-in group whose rule (`idm_acp_people_read`) allows it, and it also allows reading mail addresses.
- **OIDC scope maps are strict.** A client that asks for a scope the person's group does not grant is refused outright (403), not given fewer scopes. Apps must ask only for what the lowest group gets, or the gateway must choose the scope per person.
- **Build memory.** The first build attempt on an 8 GB VM with 4 parallel jobs was killed (SIGKILL) while compiling `kanidmd_lib`; it finished with 8 GB swap and 2 jobs (`build-provenance.txt`).

### Files

`run-1/AK-n.txt` hold every command as run and its real output; `run-1/tools/` holds the scripts and the lab client; `run-1/results.json` the machine-readable result; `run-1/SHA256SUMS` the hashes. Passwords, tokens, TOTP secrets and the virtual authenticator's key stayed in a root-only folder inside the VMs and were destroyed with them; a scan of every log against those values found none.
