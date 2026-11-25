<!-- SPDX-License-Identifier: Apache-2.0 -->
# The key ceremony, explained for a first-time OS builder

**Asked by:** the founder, 2026-11-25 ("I still don't understand what the ceremony does ... why, and is this required?").
**Serves:** REL-01 ([#153](https://github.com/onemindos/ONEMINDOS/issues/153)), decision D-010 (three root keys, any two sign), F-27 (nothing is published as signed until the offline root exists). The runbook is [`os/update/CEREMONY.md`](../../../os/update/CEREMONY.md).

## What it does, in plain words

Think of a **company seal**, the stamp a notary presses on a document.

- Every OneMind box downloads updates from the internet. Before it installs one, it has to answer: *"Did this really come from OneMind, or did someone fake it?"*
- To answer that, every box ships with a small file, `root.json`, that says: *"only trust updates stamped with these specific keys."*
- The **ceremony** is the one-time moment where the founder **creates those master keys**: carving the company seal.
- After that, every update OneMind publishes is stamped. Each box checks the stamp, installs real updates and refuses fakes.

The signing design is called **TUF** (The Update Framework). The master keys are the **root keys**. Day-to-day signing uses separate **online keys** that the release pipeline holds; if one of those ever leaks, the root keys replace it. (Lesson 08, [From a Debian fix to your box](../08-security-pipeline-and-tuf.md), goes deeper.)

## What it protects against

Someone breaking into OneMind's GitHub account, build machines or download server and pushing a poisoned update to every customer's box. Without the root keys they cannot make a stamp the boxes accept.

## Why the owner does it, not an AI or a cloud service

Whoever holds the root keys decides what every OneMind box in the world will install, so they belong to a person the company trusts completely: today, the founder.

- **Not an AI agent.** If the keys were ever created or seen inside an AI session, they would count as exposed from day one. Agents built and rehearsed the script; they never hold, see or type a real root key or PIN.
- **Not GitHub or a cloud key service.** A break-in there is exactly the threat the root keys guard against.

## Why three keys, and why any two

- **Lose one, still fine:** sign with the other two, then replace the lost one.
- **One stolen, still fine:** one key alone cannot sign anything.
- Keep them in three places: one with the founder, one in a safe at home, one off-site or with a trusted person.

## USB sticks or YubiKeys?

**YubiKeys are better.** On a USB stick the secret key is a file, and using it copies it into the computer's memory, where malware could take it; that is why the stick version needs an offline laptop. On a YubiKey (a hardware security key) the secret is created inside the device and can never be copied out: the computer asks the YubiKey to sign, and the owner touches it to say yes. So no offline laptop and no printer are needed. The founder has three YubiKeys, which fits the any-two-of-three rule. The ceremony script still has to learn to sign with YubiKeys and be rehearsed on throwaway keys first (not built yet).

## Is it required?

- **To build OneMind and use it yourself: no.** Development uses throwaway keys, and a box in daily use works with them.
- **To publish signed updates to other people: yes.** Until the ceremony is done, OneMind cannot put out an official release that customers' boxes trust (F-27).
- **Customers never do this.** It is a one-time publisher task. A customer only ever sees "Update available". Everything on their own box (their passkeys, disk encryption, the box's own keys) is created automatically during setup.

## What it will look like

About 20 minutes, once, on the founder's normal computer: plug in each YubiKey, touch it when asked, set a PIN on each (typed by the founder, never seen by an agent), then store the three keys in their three places. The only file that comes back into the repo is the public `root.json`.
