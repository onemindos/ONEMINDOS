<!-- SPDX-License-Identifier: Apache-2.0 -->
# 03 · Identity and enrollment (FB-2): how a machine proves who it is, joins with your approval, and is removed

**Date:** 2026-11-12 · **Workstream:** FB-2 (Tier A) · **Lab:** `fb2-fdo-enroll` **PASS** (spike 3, this run).
**Serves requirements:** N-4, F-3, F-11, M-2, U-4, AI-5, R-3, H-1, H-4 · hardening H-06, H-23
**Decision-critical:** DC-F3 ("the owner-approved ticket + pairing code is the universal join; FDO is the zero-touch front end for OneMind-built and industrial hardware"), refuters in `evidence/refuters/DC-F3-*.md`.

> **Explain it like I'm the founder.** Every machine gets its own secret key the first time it starts, and that key *is* the machine. Joining is two steps. First the machine *asks*: you show a QR code or one-time code, and it files a request. Then *you decide*: your phone shows exactly what the machine is and a 6-digit code that must match the one on the machine's screen; you approve with your passkey. Only then does the hub give the machine its certificates and bus credentials, which let it speak only for itself. For boxes OneMind sells, there is an industry standard (FDO) that lets a box find you by itself the first time it is plugged in. The lab showed that even then nothing happens until you approve, and that a voucher you delete stops the box from joining.

## 1. The answer

| Question (brief FB-2) | Answer | Evidence |
|---|---|---|
| How does a machine join? | **Owner-approved join** as designed in FABRIC.md §4 / contract §12.11: single-use ticket (≤ 1 h) → node request with its own public keys → `node.join` action (`sensitive`) → owner compares the pairing code and approves → custodian signs certificate + NATS credentials once | FABRIC.md §4; same idea as Flight Control's enrollment request + `flightctl approve` [C-FB11-004] |
| Zero-touch for boxes OneMind sells? | **FDO 1.1** as the front end: the box carries a factory credential; the voucher goes to the owner; the hub imports it **only after the owner approves**; TO2 delivers the OneMind join bundle; the normal `node.join` then completes | lab `fb2-fdo-enroll` T2/T3 PASS [C-LAB-fb2-fdo-enroll-003, -004]; FDO late binding and local rendezvous [C-FB2-003] |
| QR onboarding? | The box shows a join QR (`onemind-join:v1?...`, contract §12.11); devices with their own codes (Matter `MT:`, FDO, Wi-Fi DPP) are scanned by the phone app (REC-W11-16) | contract §12.11; Matter commissioning with DAC attestation [C-FB2-004] |
| How does the phone approve? | Approval card (board, arch, OS, hostname, labels, pairing code; no serial, MAC or IP) + WebAuthn step-up | contract §12.3, §12.11 |
| TPM attestation? | Phase 3 (FABRIC §3): seal node keys to the TPM where `tpm2: true`; for OneMind-sold SKUs, an IDevID/DevID certificate (W8-R6) | SPIRE `tpm_devid` needs an out-of-band DevID plus the TPM maker's endorsement CA [C-FB2-002]; Flight Control keeps the key in the TPM [C-FB11-004] |
| SPIFFE/SPIRE? | **Pattern, not a dependency.** OneMind's custodian already is a small node-attestation + certificate authority; SPIRE adds a server and an agent per node | SPIRE's attestors and SVIDs [C-FB2-001, C-FB2-002]; constraint fit in §4 |
| Kanidm (BD-03)? | For **people** (owners, household, passkeys), not machines | brief 30 BD-03; C-BRIEF30-001 |
| Survives a reflash? | **No, by design**, unless the key lives in a TPM. Node keys live on `/data` and survive OS A/B updates; a wiped disk loses them and the node re-joins with a new ticket. An FDO credential is also lost with the disk | lab E1: wiped blob → "device has not been properly initialized" [C-LAB-fb2-fdo-enroll-008]; TPM-held FDO secrets not tested (E2 not run) |
| Transfer of ownership? | BYO hardware: `node.remove` (revokes, optional wipe) → new owner joins it. OneMind-sold hardware: FDO voucher extension to the new owner ("resell" endpoint exists in go-fdo-server; not tested) | `go-fdo-server` routes at v1.0.2 (§3.2) |
| Revocation? | FABRIC §3: stop renewing (30-day certs) + deny-list + remove the NATS user; FDO: delete the voucher before first power-on | lab E6: approved then revoked device reached the owner via the rendezvous and was refused at TO2 [C-LAB-fb2-fdo-enroll-007] |

## 2. Lab spike 3: `fb2-fdo-enroll` (pre-registered, PASS)

Full record: `../evidence/lab/fb2-fdo-enroll/README.md`. Disposable Debian 13 arm64 VM (4 vCPU / 4 GiB), go-fdo-server **v1.0.2** and go-fdo-client **v1.0.0** built from pinned module versions with checksum-database verification; the two pin different go-fdo library commits and still interoperated.

| Test | Result | What it shows |
|---|---|---|
| T0 pins and builds | PASS | reproducible build of both binaries [C-LAB-fb2-fdo-enroll-001] |
| T1 device initialisation | PASS | factory step creates a credential and a voucher [-002] |
| T2 no approval → no onboarding | **PASS**: 120 s of retries, no completion, no file | the voucher import *is* the approval gate [-003] |
| T3 approval → zero touch | **PASS**: the **same** device process finished **18 s** after the stand-in approval imported the voucher; the join bundle arrived byte-identical | no keyboard on the device [-004] |
| T4 another owner's hub | **PASS**: refused with `400 Invalid ownership voucher` | a voucher is bound to its owner key [-005] |
| T5 revocation after onboarding | PASS, but **uninformative**: the client refuses any second onboarding ("Device Onboarding already completed") even before revocation (control E5) | after TO2, revocation is OneMind's job (deny-list), not FDO's [-006] |
| E6 revoke before first power-on | owner deleted the voucher; the device still found its owner through the rendezvous and was refused at TO2 | the meaningful FDO revocation [-007] |
| E4 what the owner can do | the owner's `fdo.command` step ran a shell **as root** on the device | FDO service info is root code execution by design: only the approved owner's hub may hold vouchers [-004] |
| Attempt 1 (script bug, kept in `history/`) | TO0 failed until the device CA was added to the rendezvous's trusted list | a rendezvous accepts only devices from manufacturers it trusts [-010] |

**What changes because of this run.** Nothing in FABRIC.md's flow. FDO becomes a *front end* that delivers the join bundle; the approval moment moves from "approve a pairing code" to "approve a voucher" (the card shows the GUID, device info and manufacturer key fingerprint). go-fdo-server v1.0.2 has **no voucher delete API** (routes: `POST /owner/vouchers`, `POST /owner/resell/{guid}`, `GET /owner/devices` [C-LAB-fb2-fdo-enroll-010]), so OneMind's own voucher store must own deletion and revocation. Upstream maturity remains a risk: go-fdo has not finished FIDO interop testing (C-G4U-006) and Fedora's Rust FDO was deprecated (C-W8-043).

## 3. Identity model across classes

| Class (`02-…`) | Machine identity | Where the private key lives | Credential lifetime | Revocation |
|---|---|---|---|---|
| Image node, installer node, Jetson | Ed25519 node key → box-CA certificate (30 days) + NATS nkey | `/data/onemind/identity/` (0600); TPM-sealed in phase 3 | renews at 2/3 life over mutual TLS | deny-list + stop renewing + remove NATS user (FABRIC §3, §8) |
| Managed-Kubernetes site | site certificate + one NATS leaf credential for the site hub | Kubernetes Secret on that cluster | as above | remove site; fleet hub stops accepting the leaf |
| Sensor/MCU/PLC behind an adapter | the adapter's mapping entry; the protocol's own identity where it exists (Matter DAC, OPC UA application certificate) | on the device | protocol-defined | remove from the adapter's approved list |
| Person | Kanidm account + passkeys (BD-03) | the person's authenticator | session | Kanidm |
| AI agent | agent principal + scoped token (contract §11, §12.6) | gateway | short, audience-bound (`07-…`) | revoke the grant |

## 4. What competitors do (constraint-matched)

| Product | Enrollment | Approval by a human? | Key storage | Constraint fit | Take |
|---|---|---|---|---|---|
| Flight Control | agent calls home with a fleet enrollment cert, CSR, **EnrollmentRequest approved by operator**, optional TPM key [C-FB11-004] | **Yes** | TPM when available | **High** (pattern); RHEL-family OS | Confirms OneMind's approval step and TPM roadmap |
| SPIRE | node attestation (join token, cloud identity, x509pop, tpm_devid…) → SVIDs [C-FB2-001, C-FB2-002] | No (policy) | TPM for tpm_devid | Medium: a server + agent per node is more than a home needs | Copy the attestation *ideas*; no dependency |
| FDO (go-fdo) | factory DI → voucher → rendezvous → TO2 [C-FB2-003] | Only if the owner gates the voucher import (lab) | device blob or TPM | High for OneMind-sold boxes; Apache-2.0 | Adopt as an optional front end |
| Matter | QR/NFC commissioning, DAC attestation, several admins [C-FB2-004] | Yes (user commissions) | device | High for home devices (through a Matter app) | Phone scans device codes |
| balena | fleet provisioning key in the image (C-TD-balenaos-035) | No | key in `config.json` | Low | Do not copy shared keys |
| Viam | machine API key embedded in the install command (C-TD-tier-c-robotics-050) | No | file | Low | Do not copy |
| Fleet (Kubernetes) | ClusterRegistrationToken, forgotten after use; a reused client ID with a different token is held pending [C-FB4-006] | No (token holder) | Secret | Medium (sites) | Same "token only lets you ask" spirit for site enrolment |

## 5. Phone approval flow (unchanged design, now with FDO)

```mermaid
sequenceDiagram
  participant M as New machine
  participant RV as Rendezvous (owner-run or OneMind-run)
  participant G as Hub gateway + custodian
  participant P as Owner's phone
  Note over M: FDO path (OneMind-sold box). BYO path skips RV and starts at "join request".
  M->>RV: TO1: where is my owner? (retries until known)
  P->>G: approve "import voucher <GUID>" (passkey)
  G->>RV: TO0: I own <GUID>
  M->>G: TO2: prove device + owner; receive join bundle
  M->>G: join request (node keys, facts)
  G->>P: Approvals card: board, arch, OS, pairing code
  P->>G: approve node.join (passkey)
  G->>M: certificate, NATS creds, k3s token (once)
```

## 6. Open items (in `14-…`)

- **ZF-04** FDO for the hardware line: who runs the rendezvous (OneMind, the owner, both) and where vouchers are handed over at sale.
- **ZF-11** NATS isolation model: keep config users with permissions (tested) until scale needs JWT/accounts.
- Proposed **F-17**: "no machine receives credentials without an owner approval it can be matched to (pairing code or voucher)".

## Glossary

| Term | Meaning |
|---|---|
| Ticket / join code | A single-use right to *ask* to join, valid up to an hour |
| Pairing code | 6 digits computed from the ticket and the machine's key on both sides, so you approve the machine in front of you |
| Box CA / custodian | The hub's certificate authority and the root-only service that signs only approved requests |
| Voucher | FDO's signed ownership record for one device |
| Rendezvous | FDO's directory that tells a device where its owner is |
| DevID / IDevID | A device certificate whose key lives in a TPM, issued at manufacture (IDevID) or later (LDevID) |
| SVID | A SPIFFE identity document (X.509 or JWT) |
