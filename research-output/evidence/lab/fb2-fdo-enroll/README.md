# Lab spike LAB-fb2-fdo-enroll: zero-touch enrollment with FIDO Device Onboard, owner approval and revocation

**Status:** COMPLETE: **PASS**. T0–T5 all passed in run 2 (2026-11-12 10:28–10:33 UTC). Pre-registered and pushed as `b5eaa3b` before any VM existed. Run 1 stopped on a lab-script omission (§8).

**Serves:** fabric mission 02 (`RESEARCH-MISSION-02-ONE-MIND-FABRIC.md`) §5 lab spike 3 ("Zero-touch enrollment") and workstream FB-2; `docs/architecture/FABRIC.md` §4 (owner-approved join) and H-23; research 30 B9 (identity), mission 01 claims C-G4U-004…006 and C-REF4-DC-longevity-005 (go-fdo maturity).

> **Explain it like I'm the founder.** FIDO Device Onboard (FDO) is an industry standard for "the box finds its owner by itself". At the factory a machine gets a secret and a digital "ownership voucher" (a signed note saying who owns it). When you buy it, the voucher is handed to you; you load it into your hub. The first time the machine powers on with internet, it asks a public "rendezvous" directory where its owner lives, connects, proves it is the machine in the voucher, and receives its setup. Nobody types anything on the machine. This spike checks, with the open-source Go implementation, that: nothing happens until you approve; after you approve, the machine joins with no touch and receives a OneMind join bundle; somebody else's hub cannot claim it; and removing the voucher stops it.

## 1. Goal

Answer with a run whether FDO 1.1 (go-fdo-server v1.0.2 and go-fdo-client v1.0.0, Apache-2.0) can be the zero-touch front end of OneMind's owner-approved join (FABRIC.md §4): the approval decides, the device needs no keyboard, the device receives a join bundle, a different owner cannot claim it, and revocation works.

## 2. Hypotheses

- **H1** DI (device initialisation, the "factory" step) with go-fdo-client v1.0.0 against go-fdo-server v1.0.2 produces a device credential and an ownership voucher, although the two binaries pin different go-fdo library commits (client `2d3d7c734680`, server `65061850e1c9`).
- **H2** If the owner has not imported (approved) the voucher, a device that keeps trying to onboard does not complete.
- **H3** After the owner imports the voucher, the **same, still-running** device process completes TO1 and TO2 with no action on the device, and receives the file the owner provided through the `fdo.download` service-info module.
- **H4** An owner service holding a different owner key cannot import the voucher.
- **H5** After the owner deletes the device's voucher(s), the device can no longer onboard.

## 3. Pass / fail criteria (frozen before the run)

| ID | Test | PASS if | FAIL if |
|---|---|---|---|
| T0 | Pins and builds | Go **1.27.4** `linux-arm64` matches the fb3 pin `3392582988a273a87ab5043ee1b2c9c17a2c3c00580bf9326c47a2e0aaaeac92`; `go install github.com/fido-device-onboard/go-fdo-server@v1.0.2` and `…/go-fdo-client@v1.0.0` succeed with the default checksum database on (`GOSUMDB` default, `GOFLAGS=-mod=readonly`, `GOTOOLCHAIN=local`); `go version -m` shows those module versions | Any hash mismatch, a module checksum error, or another version |
| T1 | DI | Rendezvous, manufacturing and owner services (sqlite, plain HTTP on loopback inside the VM) report healthy; `go-fdo-client device-init` (ec256) exits 0; `print` shows a 32-hex GUID; `GET /api/v1/vouchers/<GUID>` on the manufacturer returns a non-empty voucher | Any step fails |
| T2 | No approval, no onboarding | With the voucher **not** imported to the owner, `go-fdo-client onboard` started in the background shows no `FIDO Device Onboard Complete` and has written no `fdo.download` file after **120 s** | It completes, or receives the file |
| T3 | Approval, then zero touch | A stand-in approval script prints an approval card (GUID, device info, serial) and only then `POST`s the voucher to the owner. Within **300 s**, the **same** onboard process from T2 (not restarted, nothing typed on the device) logs `FIDO Device Onboard Complete`; the file it received through `fdo.download` has the same sha256 as the owner's join-bundle file; the marker file written by the owner's `fdo.command` step exists | No completion in 300 s, a restart was needed, or a hash differs |
| T4 | Wrong owner | A second owner service with a **different** owner key refuses the import of the same voucher (non-2xx HTTP status) | It accepts the voucher |
| T5 | Revocation | After the owner deletes every voucher it holds for this device (original and any replacement GUID), a fresh `onboard` run does not complete within **120 s** | It completes |

**Spike verdict:** PASS if T0–T5 all pass in one full run. An environment limit gives BLOCKED with the reason, never PASS. A lab-script bug is logged in "Deviations", fixed, and the whole run repeated; failed logs are kept in `history/`.

**Exploratory (not pass/fail):**
- **E1 reflash:** delete the device credential blob (a wiped disk) and try to onboard: what happens, and what would restore identity.
- **E2 TPM:** if `--tpm` accepts a software TPM (`swtpm` from Debian) without code changes, repeat DI and onboarding with device secrets in the TPM.
- **E3 credential replacement:** compare the GUID and owner key in the device blob before and after TO2 (does onboarding hand the device to the new owner for good?).
- **E4 security observation:** what the owner can make the device do through `fdo.command` (executes as the onboarding client's user).

## 4. Design

- **Host isolation:** everything runs inside one disposable Lima VM `fb2fb4lab` (`template:debian-13`, arm64, `vz`, **4 vCPU / 4 GiB**, 20 GiB) shared with spike `fb4-fleet-rings` (run after this one). Its only host mount is the lab work folder `<lab-dir>`. The VM is deleted when both spikes end.
- **Roles:** one rendezvous, one manufacturer, one owner (the "hub"), all on loopback with separate sqlite databases; a second owner (different key) for T4. Keys and certificates are generated at run time inside the VM and never committed.
- **Join bundle:** a text file in the form of contract §12.11 `qr_payload` with a random code and a random CA hash (`onemind-join:v1?code=<random>&ca=<random sha256>&role=worker`), standing in for what the gateway would hand over after approval.
- **Approval stand-in:** a script plays the owner's phone approving the `node.join` card. OneMind's gateway is not part of this spike.

## 5. Fidelity limits (written before the run)

| This lab shows | It does not show |
|---|---|
| The FDO 1.1 protocol flow between the two Go implementations on one machine | Real manufacturing, a real public rendezvous server, TLS between services, or other vendors' FDO stacks (interop) |
| Whether approval can gate onboarding | Phone UX; OneMind gateway integration |
| Revocation by deleting vouchers | Revocation of credentials already handed out (that is OneMind's own deny-list, FABRIC §3) |

## 6. Glossary

| Term | Meaning |
|---|---|
| FDO | FIDO Device Onboard: a FIDO Alliance standard for zero-touch device onboarding |
| DI | Device Initialization: the factory step that creates the device credential and the voucher |
| Ownership voucher | A signed record of the chain of owners of one device; whoever holds the last key can onboard it |
| Rendezvous (RV), TO0, TO1, TO2 | The directory service; the owner registering with it (TO0); the device asking it where its owner is (TO1); the device and owner proving themselves and transferring setup (TO2) |
| FSIM / service info | Setup steps the owner sends during TO2 (`fdo.download`, `fdo.command`, …) |

---

## Results

**Verdict: PASS.** Every pre-registered test passed in run 2: T0 (pins and builds), T1 (DI), T2 (no approval, no onboarding), T3 (approval, then zero touch), T4 (wrong owner refused), T5 (revocation). T5 passed but is **uninformative** (§7.2 E5). Full data: `run-2/results.json`, `run-2/res/`, ledger `../../claims/LAB-fb2-fdo-enroll.csv`.

> **Explain the result like I'm the founder.** The standard works as a front door for boxes OneMind sells. A "factory" made a device credential and a voucher. While the hub had not accepted the voucher, the device kept asking for two minutes and got nowhere. The moment the stand-in for your phone approved, the same device, untouched, finished joining **18 seconds** later and received the OneMind join file byte for byte. Another owner's hub refused the voucher outright. Two warnings: once a device has joined, the client refuses to join again, so after that point removing it is OneMind's job, not FDO's; and the owner's setup step runs commands **as root** on the device, so only your own hub may ever hold its voucher.

### 7.1 Test results (run 2)

| ID | Result | Evidence (in `run-2/`) |
|---|---|---|
| T0 | **PASS** | Go 1.27.4 matched the fb3 pin; `go install` built go-fdo-server **v1.0.2** (`h1:ebAliL6t…`, go-fdo `v0.0.0-20260908145651-65061850e1c9`) and go-fdo-client **v1.0.0** (`h1:9AafFxNu…`, go-fdo `v0.0.0-20260204145003-2d3d7c734680`) with the checksum database on; binaries `15e7dd75…` (server) and `69ffc8a3…` (client) [C-LAB-fb2-fdo-enroll-001]. `../logs/fetch.log` |
| T1 | **PASS** | four services healthy (`200 200 200 200`); DI exit 0; GUID `500379ed…`; voucher HTTP 200 [-002]. `res/T1.json` |
| T2 | **PASS** | 120 s after starting `onboard` with no voucher at the owner: no completion, no file, 26 logged "TO1 failed" lines (`not found` at the rendezvous), process still running [-003]. `res/T2.json`, `onboard-t2t3.log` |
| T3 | **PASS** | approval card printed (`approval-card.txt`), owner import HTTP 200; the **same** process (not restarted) logged `FIDO Device Onboard Complete` **18 s** later; join bundle sha256 `0ec1cb88…` identical on owner and device; `fdo.command` marker present, ran as uid 0 [-004]. `res/T3.json` |
| T4 | **PASS** | second owner (different key) answered `400 Invalid ownership voucher` [-005]. `res/T4.json` |
| T5 | **PASS (uninformative)** | after clearing the owner's `vouchers`, `replacement_vouchers`, `incomplete_vouchers` and session tables (go-fdo-server v1.0.2 has no delete API), a fresh `onboard` did not complete in 120 s; but the control E5 shows the client refuses any second onboarding anyway [-006]. `res/T5.json`, `revoke.txt` |

### 7.2 Exploratory (not pass/fail)

- **E1 reflash:** with the credential blob gone the client stops at once: `device has not been properly initialized: run device-init first` [-008]. FDO identity does not survive a disk wipe unless its secrets live in a TPM (E2).
- **E2 TPM:** not run. The client rejects the `simulator` TPM and needs a TPM character device; the VM had none (`res/E2.json`).
- **E3 credential replacement:** TO2 replaced the device GUID (`500379ed…` → `7b0f4784…`); the owner lists the device under the new GUID with `old_guid` [-009]. `owner-devices-before-revoke.json`
- **E4 owner power:** the owner's `fdo.command` ran a shell as **root** on the device [-004].
- **E5 control for T5:** before any revocation, a second `onboard` exits at once with `FDO in Idle State. Device Onboarding already completed` [-006].
- **E6 revoke before first power-on:** a second device was approved (import HTTP 200), then its voucher was deleted before it first ran `onboard`. TO1 still succeeded (the rendezvous kept the owner's registration) and TO2 was refused: `error retrieving voucher for device … not found`; no completion in 120 s [-007]. This is the meaningful FDO revocation.

### 7.3 What this means for the design (refinements; nothing in FABRIC.md is changed)

1. **FDO is a front end, not a replacement.** The voucher import is the approval moment; after TO2 the normal `node.join` and OneMind's deny-list take over (`research-output/fabric/03-IDENTITY-AND-ENROLLMENT.md`).
2. **OneMind must own the voucher store** (import, list, delete, resale), because go-fdo-server v1.0.2 exposes only `POST /owner/vouchers`, `POST /owner/resell/{guid}` and `GET /owner/devices` [-010].
3. **A rendezvous trusts only listed device CAs** (run 1): OneMind's rendezvous must be loaded with the CAs of the factories it serves.
4. **Owner service info is root on the device**: OneMind's owner role sends only the fixed join step.

### 8. Deviations, failed attempts and fixes

| # | What | Effect |
|---|---|---|
| 1 | **Run 1** stopped at T3: the owner's TO0 to the rendezvous failed with `cryptographic verification failed: x509: certificate signed by unknown authority` because the lab script never added the device CA to the rendezvous's trusted list (`POST /api/v1/device-ca`, documented in `api/device-ca.yaml` at the tag, not in the README quick start). T1 and T2 had passed. | Lab-script omission, fixed (one `curl` line); the whole run repeated as run 2. Logs in `history/attempt1/` |
| 2 | T5 "deletes every voucher" was done in the owner's SQLite database (tables `vouchers`, `replacement_vouchers`, `incomplete_vouchers`, `sessions`, `to0_sessions`, `to1_sessions`, `to2_sessions`), because v1.0.2 has no delete endpoint | Method detail, not a criterion change; schema in `owner-db-schema.sql` |
| 3 | Not committed: the device credential prints (they contain the HMAC secret and private key), raw server debug dumps (session bearer tokens), keys and databases. Server logs are committed trimmed (`*-trimmed.log`) | Hygiene |

### 9. Reproduce

Inside a disposable Debian 13 arm64 VM: `LAB=<lab-dir> scripts/fetch.sh`, then `LAB=<lab-dir> scripts/fdo.sh 2`. The scripts write only under `/opt/fb` and `<lab-dir>/out`; they need root inside the VM and must not be run on a host.
