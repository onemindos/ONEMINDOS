<!-- SPDX-License-Identifier: Apache-2.0 -->
# The key ceremony, explained for a first-time OS builder

**Asked by:** the founder, 2026-11-25 ("I still don't understand what the ceremony does ... why, and is this required?").
**Serves:** REL-01 ([#153](https://github.com/onemindos/ONEMINDOS/issues/153)), decision D-010 (three root keys, any two sign), F-27 (nothing is published as signed until the offline root exists). The runbook is [`os/update/CEREMONY.md`](../../../os/update/CEREMONY.md).

## What it does, in plain words

Think of a **company seal**, the stamp a notary presses on a document.

- Every OneMind box downloads updates from the internet. Before it installs one, it has to answer: *"Did this really come from OneMind, or did someone fake it?"*
- To answer that, every box ships with a small file, `root.json`, that says: *"only trust updates stamped with these specific keys."*
- The **ceremony** is the one-time moment where the founder and the other key holders **create those master keys**: carving the company seal.
- After that, every update OneMind publishes is stamped. Each box checks the stamp, installs real updates and refuses fakes.

The signing design is called **TUF** (The Update Framework). The master keys are the **root keys**. Day-to-day signing uses separate **online keys** that the release pipeline holds; if one of those ever leaks, the root keys replace it. (Lesson 08, [From a Debian fix to your box](../08-security-pipeline-and-tuf.md), goes deeper.)

## What it protects against

- **Someone who breaks into the download server** has no keys, so they cannot fake an update a box accepts.
- **Someone who breaks into GitHub** could steal the everyday online keys (kept there as secrets) and sign updates the boxes accept, but only until OneMind notices: the root keys then cancel the stolen keys and name new ones, and every box follows.
- **What the offline root keys guarantee:** an attacker can never change *which* keys the boxes trust. Only the root key holders can.

## Why the owner does it, not an AI or a cloud service

Whoever holds the root keys decides what every OneMind box in the world will install, so they belong to a person the company trusts completely: today, the founder.

- **Not an AI agent.** If the keys were ever created or seen inside an AI session, they would count as exposed from day one. Agents built and rehearsed the script; they never hold, see or type a real root key or PIN.
- **Not GitHub or a cloud key service.** A break-in there is exactly the threat the root keys guard against.

## Why three keys, and why any two

- **Lose one, still fine:** sign with the other two, then replace the lost one.
- **One stolen, still fine:** one key alone cannot sign a new `root.json`.
- Keep them in three places, as D-010 says: home, off-site, and a trusted person.

## USB sticks or YubiKeys?

**YubiKeys are safer.** On a USB stick the secret key is a file, and using it loads it into the computer's memory, where malware could take it. On a YubiKey (a hardware security key) the secret is created inside the device and never leaves it: the computer asks the YubiKey to sign, and the holder unlocks it with a PIN (and a touch, if it is set up that way).

**What the plan says today (D-010):** the first ceremony runs on three encrypted USB sticks on an offline computer, and the root then moves onto hardware keys later ([#272](https://github.com/onemindos/ONEMINDOS/issues/272), REL-02). The script already supports hardware keys (`hsm:` keys in `scripts/tuf-bootstrap-root.sh`, tested in CI with SoftHSM, a software stand-in), and `os/update/CEREMONY.md` has a section for the move. Two things are still open:
- **No real YubiKey has been tried yet** (CEREMONY.md marks it UNVERIFIED), so a rehearsal on a real key comes first.
- **The hardware-key steps still use an offline computer and a sheet every key holder reads aloud.** Moving an existing root onto hardware keys also needs two of the old USB sticks and their passphrases, so it is no harder than the stick version, but it is not "plug into your everyday laptop".

The founder has three YubiKeys, which is exactly what the move to hardware keys needs. Going straight to YubiKeys for the first ceremony would be a change to D-010 that the founder decides.

## Is it required?

- **To build OneMind and use it yourself: no.** But until the ceremony, images carry no `root.json`, so a box gets no updates from the OneMind update channel; it is updated by installing new images. The throwaway keys exist only inside CI test runs and are deleted afterwards.
- **To publish signed updates to other people: yes.** Until the ceremony is done, OneMind cannot put out an official release that customers' boxes trust (F-27).
- **Customers never do this.** It is a one-time publisher task. A customer only ever sees "Update available". Everything on their own box is made on the box: they create their own passkeys during setup, the box makes its own keys, and disk encryption is on by default on machines with a TPM (D-020).

## What it will look like

Once, with the key holders: follow `os/update/CEREMONY.md` (or `scripts/ceremony-guide.py`) on an offline computer, rehearsing first with throwaway keys. Each holder sets their own passphrase or PIN, which no agent ever sees. The only file that comes back into the repo is the public `root.json`. How long it takes depends on which version is used; nothing in the repo measures it yet.
