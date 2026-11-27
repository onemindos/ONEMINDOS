<!-- SPDX-License-Identifier: Apache-2.0 -->
# UMB-ACCT-1 run 2: one passkey on the LAN name and the mesh name (evidence for F-33 option (a); F-33 stays open)

**Serves:** UMB-ACCT-1 (`docs/leap/BACKLOG.md`), founder question **F-33** (passkey domain, `docs/leap/DECISIONS-NEEDED.md`), ACCT-D1 (`docs/umbrel2/accounts.md` §4, open decisions), decision **D-015** (Kanidm as a host service on the hub OS), issue #236 (SEC-SSO-01, "Refs"). Builds on run 1 (`README.md` in this folder, 2026-11-23), which already covered AK-1 to AK-10 with an API-only passkey client.

**Date:** 2026-11-25 (counted run 11:28 to 12:04 UTC). **Founder wish (2026-11-25), UNVERIFIED (not recorded in `docs/`; `DECISIONS-NEEDED.md` F-33 is unchanged):** option (a), "one canonical sign-in host on LAN and mesh, so one passkey works at home and away"; if the lab failed, fall back to (b), per-domain passkeys.

**Status of this evidence.** It is evidence *for* F-33 option (a), from a virtual authenticator and simulated access paths, with a test plan that was **not pre-registered**. It does **not** settle F-33: `DECISIONS-NEEDED.md` makes option (a) conditional on lab **UMB-ACCT-13** (real phones, hybrid sign-in, real mesh) passing, and the decision belongs to the founder. **F-33 stays open.**

## Verdict

| Question | Verdict |
|---|---|
| **Evidence for F-33 option (a): one canonical sign-in name, one passkey, home and away** (F-33 stays open for the founder and UMB-ACCT-13) | **PASS** as a lab test, not a settlement: a real browser (headless Chromium 156 with a virtual WebAuthn authenticator), over two simulated access paths (a LAN client and a mesh client), including enrolment with the outside network cut and sign-in on a backup-restored fresh box. |
| UMB-ACCT-1 done-when 1: owner passkey enrolled with the network unplugged | **PASS** (PK-2) |
| UMB-ACCT-1 done-when 2: a restored box accepts the same passkey | **PASS** (PK-7, on both access paths) |
| UMB-ACCT-1 done-when 3: reused TOTP refused | **FAIL again** (AK-8): Kanidm v1.12.0 accepts the same TOTP code twice inside one time step. Same result as run 1. A mitigation was tested (AK-8b, AK-8c) and only partly works. Decision needed (below). |
| Groups, OIDC client, reset link, expiry, backup and restore | **PASS** (AK-3 to AK-7, AK-10, repeated on a new build) |

> **In plain words.** A passkey is tied to a web name (its *relying-party ID*, "RP ID"; here `idm.onemind.test`). The browser refuses to use it on a page whose address is not that name or a name *under* it, and Kanidm refuses it too. So the rule that makes option (a) work is simple: **pick one canonical sign-in name, and make every route (home network, mesh) reach the server under that name, or under a sub-name of it.** The lab proved that works with one passkey and no re-enrolment. It also proved the opposite case: a different name (for example a separate mesh name that is not under the canonical one) could not use the passkey and could not enrol one, observed **without** a `.well-known/webauthn` file on the canonical name (WebAuthn Related Origin Requests were not tested, see "What this run did not test"). Option (b) (a second passkey per domain) is not available inside one Kanidm, so it is not a real fallback (see "Why (b) is not available").

## Plan (written before the counted run)

> **Honest note: not pre-registered.** This PK-1 to PK-9 plan was written by the lab itself and committed together with the results. It has no row in `research-output/evidence/lab/PREREGISTRATION.md`, so a third party cannot check that it came first. Per that file's own rule, treat these criteria as not audited. The timing below is self-attested.

The tests below were written on 2026-11-25 between about 10:30 and 11:25 UTC and fixed before the counted run began (11:28:57 UTC). A rehearsal on a separate VM with the community PPA package (Kanidm 1.11.2, not the planned 1.12.0) came first, only to debug the browser driver and the network setup; nothing from it counts. The run-1 README stays frozen; this is a second run.

| ID | Test | PASS when |
|---|---|---|
| PK-1 | One canonical name, two access paths | The same host name, the same TLS certificate and the same Kanidm origin answer from a LAN-side client and a mesh-side client, each resolving the name to a different server address; the server logs both client addresses |
| PK-2 | Offline enrolment | With the VM's virtual cable out (no route, no DNS), the owner passkey is enrolled **through Kanidm's own web UI** in a real browser on the LAN path, and the owner signs in with it, still offline |
| PK-3 | Same passkey, mesh path | A new browser (a "phone away from home") holding that passkey signs in over the mesh path |
| PK-4 | Same passkey, LAN path | Likewise over the LAN path |
| PK-5 | Negative control: a name outside the canonical domain | Sign-in and enrolment at a second name (valid TLS) fail; the exact reason is recorded |
| PK-6 | Name under the canonical domain | Sign-in works at a sub-name of the RP ID; a passkey enrolled there works at the canonical name |
| PK-7 | Backup and restore | An online backup restored on a fresh Debian 13 box (same domain, new TLS CA) accepts the same passkey on both paths |
| PK-9 | Naming (extra) | A fresh instance whose canonical name is `onemind.local` (the design's LAN name) works the same way |
| AK-1, AK-3 to AK-8, AK-10 | Run-1 tests repeated | As in `README.md` section 2 |

**Verdict rule.** (a) PASS = PK-1 to PK-4, PK-7 pass and PK-5 fails for the reason a name mismatch gives (not for a lab fault). If PK-3 or PK-4 failed with an RP ID or origin error, (a) FAILS and the evidence would say what (b) needs.

## Setup as run

| Item | Value |
|---|---|
| Hypervisor | Proxmox VE 9 lab server, VMs created fresh from the Debian 13 `genericcloud` amd64 image (sha512 checked against Debian's `SHA512SUMS`): VM 502 (source box, left **stopped, not deleted**), VM 503 (restore target, destroyed after), VM 504 (package build only, destroyed). 2 vCPU, 4 GiB RAM, 20 GiB disk (504: 6 vCPU, 8 GiB + 8 GiB swap). All on an internet-only NAT bridge with no LAN or host access; nothing was exposed to the internet |
| Guest | Debian GNU/Linux 13 (trixie), kernel 6.12.118+deb13-cloud-amd64 (`AK-0-vm502.txt`) |
| Kanidm | **v1.12.0**, commit `a52b723ce8ef` (the version the repo plans, `docs/umbrel2/accounts.md` §4.1). The community PPA still had only 1.11.2 for trixie, so the packages were built from the v1.12.0 tag as in run 1 (`build-provenance.txt`). `kanidmd_1.12.0-202611010319+a52b723_amd64.deb` sha256 `2f64115b…2c57f`, `kanidm_…amd64.deb` sha256 `a6334593…38eb0`. Installed with `apt-get install` of the two files on both boxes; packaged unit `kanidmd.service` (`Type=notify`, `DynamicUser=yes`). Not byte-identical to run 1's packages (the builds are not reproducible) |
| Service | `kanidmd` listens on `0.0.0.0:8443` (all interfaces), so both access paths reach the same service. Domain (= RP ID) `idm.onemind.test`, origin `https://idm.onemind.test:8443`. These are fixed for the whole run, as ACCT-D1 requires |
| TLS | A lab CA made with `openssl`; one server certificate valid for three names: the canonical `idm.onemind.test`, an outside name `idm.mesh.test`, and a sub-name `mesh.idm.onemind.test`. So TLS never hides the WebAuthn result |
| LAN path | Network namespace `nsl` (a laptop on the home LAN): its own link to the server's LAN-side address (192.0.2.1, a documentation address) and its own hosts file mapping the canonical name to it |
| Mesh path | Network namespace `nsm` (a phone away from home): its own link to a second server interface (198.51.100.1, a documentation address) and its own hosts file mapping **the same canonical name** to it. It also resolves the two other names. `nsl` has no route to the mesh address, `nsm` none to the LAN address |
| Browser | Chromium 156.0.8078.108 (Debian 13 package), headless, driven by Selenium 4.31.1 and chromedriver 156, running inside each namespace. The lab CA is in the browser's NSS trust store |
| Authenticator | **Chromium's virtual WebAuthn authenticator** (Chrome DevTools `WebAuthn.addVirtualAuthenticator` through Selenium): CTAP2, internal transport, resident key, user verification on and succeeding. Not a phone and not a hardware key. The credential is exported to a root-only file after each step and imported into a **new** browser for the next, which stands for one phone used at home and away. It carries the signature counter with it |
| What a "mesh" is here | A second interface and a second hosts file. It is **not** WireGuard or the real OneMind mesh; it simulates only what matters to WebAuthn: which name the client types and which address that name resolves to |
| Evidence | `run-2/PK-n.txt` and `AK-n.txt`: every command as run and its real output. `tools/` holds the scripts and the lab client (`wa.py` is the browser driver). Secrets, the authenticator's private key, reset links and API tokens stayed in a root-only folder inside the VMs and are not in the repo. MAC addresses are masked in `hypervisor.txt` and `PK-2.txt`; the link-local `fe80::` addresses in `PK-1.txt` and `AK-1.txt` encode the random MACs of the lab's virtual NICs (harmless, not masked) |

## Results per test

### F-33 tests (new)

| ID | Result | What happened |
|---|---|---|
| PK-1 | **PASS** | From `nsl` the canonical name resolved to the LAN-side address and `https://idm.onemind.test:8443/status` answered `true` with TLS verified; from `nsm` the same name resolved to the mesh-side address and answered the same. Kanidm's own request log shows two different client addresses (`PK-1.txt`). One certificate, one origin |
| PK-2 | **PASS** | Rebooted with `link_down=1` on the virtual NIC (`hypervisor.txt`); eth0 `NO-CARRIER`, then set down; no default route, `getent` for a public name fails, `ping` says "Network is unreachable". Through the guest agent only: `idm_admin` recovered, person `owner` created, a reset link issued, then **in the browser on the LAN path**: the reset page opened, "Add Passkey" clicked, the virtual authenticator answered the browser's WebAuthn `create()` (RP ID `idm.onemind.test`), "Save Changes", and the browser exported credential `91bb8de03044ddc5`. A fresh browser then signed in with that passkey, still offline (`PK-2.txt`) |
| PK-3 | **PASS** | A new browser in `nsm` (mesh path), holding the exported passkey, opened `https://idm.onemind.test:8443/ui/login`, entered `owner`, and signed in (landing on `/ui/apps`). The authenticator's signature counter rose 9 to 11, which shows the passkey itself signed (`PK-3.txt`) |
| PK-4 | **PASS** | Same from `nsl` (LAN path), counter 11 to 13 (`PK-4.txt`) |
| PK-5 | **PASS** (as a negative control) | At `https://idm.mesh.test:8443` (a name outside the canonical domain, valid TLS, same server): **sign-in** failed in the browser itself with `SecurityError: The relying party ID is not a registrable domain suffix of, nor equal to the current domain` (Kanidm tells the browser the RP ID is `idm.onemind.test`; the page is on another name). **Enrolment** failed at the server: the reset page loaded, but the click on "Add Passkey" got `403 Forbidden` from `/ui/reset/add_passkey`, and no credential was created (`PK-5.txt`). The failure is the name mismatch, not TLS or a lab fault |
| PK-6 | **PASS** | At `https://mesh.idm.onemind.test:8443` (a sub-name of the RP ID) sign-in with the same passkey worked, and **enrolment worked**: a second passkey created there signed in at the canonical name from the LAN path (`PK-6.txt`). Kanidm accepts any name equal to or under its `domain` |
| PK-7 | **PASS** | An online backup (written by the running server, same PID, `/status` true) was restored on a **fresh** Debian 13 VM (`kanidmd database restore`, 0.85 s, peak 35.9 MiB RSS = 36796 KiB) with the same domain and a new TLS CA. The same passkey (fingerprint `91bb8de03044ddc5`) signed in on the LAN path and on the mesh path; the groups, people and the OIDC client came back (the "OneMind test app" tile shows), and another person's passkey signed in too (`AK-7.txt`, `PK-7.txt`) |
| PK-9 | **PASS** | A fresh instance with domain/RP ID `onemind.local`: passkey enrolled at `https://onemind.local:8443` on the LAN path, then signed in from the mesh path where **the same name `onemind.local`** resolves (by a unicast hosts file) to the mesh address, and at `https://mesh.onemind.local:8443` (`PK-9.txt`). Chromium accepts `.local` as an RP ID. Not tested: a real phone, where `.local` normally goes to multicast DNS |

### Run-1 tests repeated on a new build

| ID | Result | What happened (evidence in `run-2/`) |
|---|---|---|
| AK-1 | **PASS** | `kanidmd` enabled and active after `systemctl reboot` (`uptime -s` shows the reboot; the boot id is printed only after it, so a changed id is not shown; `NRestarts=0`, 2.1 s to start online), `/status` true, healthcheck ok, no k3s or container runtime on the box (`AK-1.txt`) |
| AK-3 | **PASS** | Groups `onemind_owners`, `onemind_adults`, `onemind_children`, `onemind_guests`, one person each; a service account's API token reads each person's `memberof` over REST (`AK-3.txt`) |
| AK-4 | **PASS** | OIDC auth code + PKCE, ID token signature verified; claim `onemind_role` is `owner` (the browser-enrolled passkey, converted for the API client: `AK-4b`), `adult` or `child`; a child asking for `profile` is refused (403) and so is a guest in no mapped group (`AK-4.txt`) |
| AK-5 | **PASS** | The admin's reset link let `child1` add password + TOTP and sign in; the second use of the same link was refused (`401 "sessionexpired"`) (`AK-5.txt`) |
| AK-6 | **PASS** | Guest signed in before the expiry; after it, sign-in was denied (`account expired`) and the earlier session token got `401` (`AK-6.txt`) |
| AK-7 | **PASS** | See PK-7 (`AK-7.txt` has the source-box half) |
| AK-8 | **FAIL** | `adult2` signed in with password + TOTP, then again with the **same** code in the same 30 s step: accepted both times (`AK-8.txt`) |
| AK-8b | partial | Account policy `credential-type-minimum = passkey` on `onemind_adults` (needs `account-policy enable` first): `adult2`, who already had password + TOTP, **still signed in** with it. The policy does not revoke existing weaker credentials |
| AK-8c | partial | The same policy **does** block new weak credentials: a new adult could not set a password (`accessdenied`) but could enrol a passkey (`AK-8.txt`) |
| AK-9 | recorded | `kanidmd` RSS 44.5 MiB idle (45584 KiB), 67.5 MiB after AK-3 to AK-6 (69164 KiB), peak 70.3 MiB during the online backup (71964 KiB), 35.9 MiB for the restore (36796 KiB); installed size 241 MiB (246640 KiB, `kanidmd`) + 111 MiB (114078 KiB, `kanidm` CLI), unstripped; database folder 5.6 MB, one gzip backup 26 KB (`AK-9.txt`) |
| AK-10 | **PASS** | `adult1` got an ID token, was removed from `onemind_adults`, the next OIDC authorise was refused (403) (`AK-10.txt`) |

## Why (b), per-domain passkeys, is not available

(b) would mean the owner enrols one passkey at `onemind.local` and another at a mesh name, and Kanidm accepts either. The lab shows why that cannot work in one Kanidm, and what it would take:

1. **Kanidm has one `domain` and one `origin`** in its configuration (`server/core/src/config.rs` at v1.12.0: a single `origin: Url`; the example config says the domain is used for WebAuthn and that changing it breaks registered credentials). Its WebAuthn RP ID is that domain.
2. **The browser enforced the RP ID rule on its own** (PK-5): a page on a different, unrelated name could not ask for the passkey. This was observed **without** a `.well-known/webauthn` file; `PK-5.txt` shows Chromium looking for "the .well-known/webauthn resource of the claimed RP ID" before failing. With WebAuthn Related Origin Requests (a file on `idm.onemind.test` listing the other name) the browser-side refusal might go away. Not tested, and whether Kanidm / webauthn-rs would accept such an origin is also untested (enrolment got a 403). So (b) is probably unavailable, but "cannot" is not proven.
3. **Kanidm refuses to enrol from the other name** (PK-5, 403).

So under (b) you would need either a second Kanidm per domain (two identity databases: not sensible) or the gateway to run WebAuthn itself for the second domain (the design already plans a gateway WebAuthn verifier for approvals, CORE-SEC-2, but sign-in is Kanidm's). Option (a) needs none of that.

## What option (a) needs from the build (not decided here)

These follow from the evidence; they are inputs for CORE-NET and CORE-SEC-10, not decisions:

1. **One canonical sign-in name, fixed before the first owner enrols.** Changing it later invalidates every passkey (Kanidm's own warning; the lab did not re-test that). Every other name for the hub must be that name or a sub-name of it (PK-6), or users must reach the hub under the canonical name.
2. **That name must resolve on both paths.** At home: the hub's own DNS or mDNS. Away: the mesh's DNS. The lab used hosts files, so it proves the passkey and Kanidm side only. Whether a phone resolves the canonical name on the mesh is the open ACCT-D1 question and belongs to **UMB-ACCT-13** (real phones).
3. **TLS must be valid under that name** on both paths (the browser will not run WebAuthn on a certificate error).
4. **Offline start is slow.** With the cable out, `kanidmd` became active 2 min 11 s after boot (PK-2). The cause, that the unit waits for `network-online.target`, is inferred from run 1 and is not shown in `PK-2.txt` (`AK-1.txt` only lists the `systemd-analyze blame` lines for the online start). A drop-in without that wait would make offline sign-in come up in seconds.
5. **The signature counter matters for restores and copies.** In the (uncounted) rehearsal a passkey presented with a counter lower than the one Kanidm had stored was refused as `CredentialPossibleCompromise`. In the counted run the restored box had the counter from the backup, which is lower than or equal to the phone's, and sign-in worked. Restoring a backup that is *newer* than the phone's counter, or cloning an authenticator, would be refused. This has not been proven on a real phone; synced passkeys normally report a counter of 0.

## What this run did not test

- **A real phone or hardware key.** The authenticator is Chromium's virtual one. Safari/iOS and Android Chrome may differ in how they treat `.local` names, certificates and cross-device ("hybrid") sign-in. That is UMB-ACCT-13.
- **Hybrid sign-in from a TV browser** (QR code to a phone). Not run.
- **A real mesh** (WireGuard or Headscale). Two namespaces and hosts files stand in for it.
- **WebAuthn Related Origin Requests** (a `.well-known/webauthn` file on the canonical name listing a second name), and whether Kanidm would accept such an origin.
- **Changing the domain** after enrolment (the upstream warning is quoted, not re-proven).
- **Kanidm 1.12.1** (released 2026-11-13, a HIGH security patch for SCIM filter parsing, no TOTP change in its notes; **UNVERIFIED**: no release or advisory URL was recorded in the lab, check the upstream release notes at github.com/kanidm/kanidm/releases before relying on it). The repo plans 1.12.0, the lab ran 1.12.0. See "Anything Zeus must decide".

## Deviations and honest record

- **Mid-run fix.** The first counted pass of AK-3 to AK-6 and the first PK-5 enrolment failed (lab client and lab script faults). Re-reading the logs: in `attempt-1/` PK-3, PK-4 and PK-6 ended "signed-in", and `attempt-2/` PK-3 to PK-6 have the same outcomes as the counted run (signed-in, signed-in, refused by the browser plus 403, signed-in plus enrolment). So the PK attempts are **earlier passes that corroborate** the counted result, not failures; only AK-3 to AK-6 and the first PK-5 enrolment actually failed. The AK-3 to AK-6 failure was in the lab's Python client: Python 3.13's strict TLS check rejected the `openssl` lab CA (no key-usage or subject-key-id extension). This is a lab-certificate fault, not a Kanidm one. The CA and server certificate were re-issued on VM 502 (`tools/recert.sh`; `setup2.sh` now makes them correctly and VM 503 was built with the corrected script), the objects the failed pass had created were deleted, and AK-3 to AK-6 and PK-3 to PK-6 were run again. The earlier logs are kept in `run-2/attempt-1/` and `run-2/attempt-2/`. **Extra credential:** `attempt-2/PK-6.txt` enrolled an additional owner passkey (fingerprint `9f9a1d51ee5a608a`) that stayed on the account and is in the backup restored in PK-7 (the counted passkey is `91bb8de03044ddc5`). PK-1 and PK-2 ran before the change and were not repeated; the certificate only changed how Python verified it.
- **A leftover.** The OIDC client `onemind_testapp` made by the failed first pass was not deleted, so the second `create` returned `409 Conflict` and the scope maps were applied again over it (`AK-4.txt`).
- **A stray background run.** A script from the failed first pass was still running when the second pass started and ran AK-10, AK-8 and AK-9 once at 11:51 against the broken certificate (one command hit `DatabaseLockAcquisitionTimeout` while two runs overlapped). Those lines were split out to `run-2/attempt-1/*-pre-tls-fix.txt`; the counted results are the 11:57 runs.
- **The owner's first OIDC try failed** (`AK-4.txt`): the browser exports the credential id with base64 padding, the API client compares without. Fixed in `wa.py` (`tosoft`) and re-run as AK-4b, which passed. This is a lab-client bug, not Kanidm.
- **First enrolment attempt at the outside name** (`attempt-1/PK-5.txt`) read the wrong reset token (a lab script bug). Re-run in `PK-5.txt`.
- **Not byte-for-byte run 1.** The server config differs from run 1's on purpose (listens on all interfaces; own CA). AK-8's second half (AK-8b) was moved out of `ak8.sh` into `ak8b.sh` and `ak8c.sh` after its first try ran before `account-policy enable` (`attempt-1/AK-8b-first-try-policy-not-enabled.txt`).
- **Cleanup.** VM 503 (restore) and VM 504 (build) were destroyed after the run; **VM 502 is stopped, not deleted**, with its logs, screenshots and secrets still inside. It is kept so the run can be inspected or repeated (e.g. the pre-fix state behind AK-1, PK-1, PK-2); it should be destroyed once the founder has reviewed this run, since it holds lab secrets. The package server on VM 504 listened on the NAT bridge only, for a few minutes, to hand the two `.deb` files to VMs 502 and 503.

## Anything Zeus must decide

1. **F-33 (stays open).** The lab is evidence for **option (a)**, in this precise form: *one canonical sign-in name (the Kanidm domain / RP ID); the LAN and the mesh must both reach the hub under that name or a sub-name of it.* Option (b) looks unworkable with Kanidm (see above, with the Related Origin Requests caveat). Decide the canonical name (for example `onemind.local` as in the design, or a name under a domain OneMind controls) **before the first owner enrols**; the lab shows `onemind.local` is accepted as an RP ID (PK-9), but whether phones resolve it on the mesh is still open and belongs to UMB-ACCT-13. Also decide who answers DNS for it at home and on the mesh (CORE-NET).
2. **TOTP replay (the third UMB-ACCT-1 criterion fails).** Options, none switching the identity provider: (i) make passkeys the only credential for new people through Kanidm's `credential-type-minimum = passkey` account policy, which the lab shows blocks new password and TOTP enrolment but does **not** stop people who already have TOTP; (ii) report the missing replay check upstream and ask for a used-step record (`server/lib/src/credential/totp.rs`, `Totp::verify`); (iii) keep TOTP as a fallback and accept a window of up to about 60 s, relying on Kanidm's soft-lock against guessing. Founder decision B1 already says passkeys first, TOTP only as a fallback; option (i) fits it for the people the owner invites from now on.
3. **Kanidm version pin.** Upstream released **1.12.1** on 2026-11-13 as a HIGH security patch (denial of service by an unauthenticated user through SCIM filter parsing) (**UNVERIFIED**, no source URL recorded; check upstream release notes). The repo pins 1.12.0 (`docs/umbrel2/accounts.md` §4.1). This lab did not edit the pin; moving to 1.12.1 is a pin change for the image owner and a re-run of AK-1 to AK-10 is cheap now that the scripts exist.

## Files

`run-2/PK-n.txt` and `run-2/AK-n.txt` hold every command as run and its real output; `run-2/hypervisor.txt` the Proxmox side of the offline step; `run-2/build-provenance.txt` the package build; `run-2/tools/` the scripts, the API lab client `aklab.py` (from run 1) and the browser driver `wa.py`; `run-2/attempt-1/` and `run-2/attempt-2/` the earlier tries (AK-3 to AK-6 and the first PK-5 enrolment failed; the PK passes corroborate the counted run); `run-2/results.json` the machine-readable result and `run-2/SHA256SUMS` the hashes.
