<!-- SPDX-License-Identifier: Apache-2.0 -->
# Release keys: who holds what

**Status:** K-ROOT on YubiKeys is decided (D-031, 2026-11-25); Zeus is the sole key holder (2026-11-27). The other keys below are still choices for Zeus. The key list follows brief 30 B4.6 (K-ROOT, K-RAUC-CA/SIGN, K-TUF-ONLINE, K-SB). No agent makes, holds or sees a real key.

## Why there is more than one key

A box checks an update twice, with two different keys, before it runs it:

1. **TUF** (`root.json` and its online keys) answers "is this the newest release OneMind published for my board?". It stops old, replayed or frozen update lists.
2. **RAUC** (the X.509 keyring in the image, `/etc/rauc/keyring.pem`) answers "was this exact bundle signed by OneMind?". `rauc install` refuses a bundle whose signature does not chain to the keyring.

With **Secure Boot** on (the `efi` route, D-019), the firmware adds a third check at every start: the kernel image must be signed by a key in the firmware's `db` list.

## The map

| Key | What it signs | How often | Where it lives (proposal) | State |
|---|---|---|---|---|
| K-ROOT (TUF root, 3 keys, any 2 sign) | `root.json`: which keys may sign the update lists | Once a year (renewal) | **3 YubiKeys, PIV slot 9c**, kept in three different places ([CEREMONY.md, Ceremony on YubiKeys (D-031)](CEREMONY.md#ceremony-on-yubikeys-d-031)) | Decided (D-031); tooling and rehearsal ready; real-YubiKey steps UNVERIFIED until the spare trial |
| K-TUF-ONLINE (targets, snapshot, timestamp) | The update lists | Nightly and every 6 hours | GitHub Environment `tuf-signing`, `main` only (D-010) | Unchanged |
| K-RAUC-SIGN | Every bundle | Nightly | GitHub secret `ONEMIND_RAUC_SIGNING_KEY` + `_CERT`: online, because the nightly signs without a person | Unchanged; the cert should be short-lived (1 year) and issued by K-RAUC-CA |
| K-RAUC-CA | Only the K-RAUC-SIGN certificate, once a year | Yearly, offline | **Open: see decision 1** | Open |
| K-SB-db | Each kernel image (UKI) | Nightly, on the `efi` route | Online in CI, like K-RAUC-SIGN | Not needed for Step 5 (the Dell's first image boots without OneMind Secure Boot keys) |
| K-SB-PK, K-SB-KEK | The firmware's key lists (db, dbx) | Rarely | **Open: see decision 2** | Open |

## Decision 1: where the RAUC CA lives

The RAUC CA is the key the image's keyring trusts. It signs one thing, the nightly signer's certificate. X.509 has no "2 of 3", so the protection has to come from custody and from having more than one CA.

| Option | How | For | Against |
|---|---|---|---|
| **A. Two CAs, each made on a YubiKey** (retired PIV slot `82`, holders A and B) | The image keyring holds both CA certificates; either can issue a new signer certificate | No CA key ever exists as a file. One lost YubiKey changes nothing | The tool that issues a certificate with a YubiKey key (PKCS#11 signing of the certificate) is **not built yet**; RAUC accepting a two-certificate keyring is UNVERIFIED here |
| **B. One CA as an encrypted key file, made at the ceremony** (offline machine, `openssl`, passphrase), copied onto two of the holders' sticks | Same commands as `os/update/build-release.sh` uses with throwaway keys today | Works with today's tools, so Step 5 can use a real CA | The key existed as a file in the offline machine's memory; a stolen stick plus its passphrase is a copy |
| C. No CA: the signer certificate itself is the keyring (today's fallback in CHANNEL.md §6) | | Simplest | A leaked signer key means re-flashing every box; nothing can rotate it |

**Recommendation:** B for Step 5 (it unblocks real signed updates on the Dell now), then A as a planned keyring rotation once the YubiKey certificate tool exists. Either way the signer certificate lives one year, so a leaked signer stops being accepted when it expires; a CRL in the keyring would end it sooner (RAUC supports one, UNVERIFIED here).

## Decision 2: where the Secure Boot owner keys live (PK, KEK)

The firmware holds one PK (owner of the box's key lists) and any number of KEKs (allowed to change db and dbx). D-019: OneMind's key is enrolled at the factory, and in sovereign mode the owner's PK replaces OneMind's while OneMind's KEK and db stay enrolled.

| Option | How | For | Against |
|---|---|---|---|
| **A. PK on holder A's YubiKey (retired slot `83`), one KEK on each of holders A and B's YubiKeys** | Both KEK certificates are enrolled; either one can sign a db or dbx change | Keys never exist as files; one lost KEK changes nothing | Signing the `.auth` enrolment files with a PKCS#11 key (`sign-efi-sig-list` with an engine, or `sbvarsign`) is UNVERIFIED and not wired; a lost PK means a box can only change PK through firmware setup mode at the machine |
| B. PK and KEK as encrypted files on two sticks, made at the ceremony | `openssl` + `efitools`, offline | Works with known tools | Same file-copy risk as decision 1 B |

**Recommendation:** decide after Step 5. Step 5 (the Dell) proves signed **updates**; the x86 image used there boots without OneMind's Secure Boot keys enrolled, so PK and KEK are not on the critical path. Secure Boot on hardware is its own step (#148, `make secureboot-test` covers it in QEMU with throwaway keys).

## What each choice needs from Zeus

1. Decision 1 (RAUC CA: A, B or C).
2. Decision 2 (PK/KEK), or "after Step 5".
