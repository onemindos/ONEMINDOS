<!-- SPDX-License-Identifier: Apache-2.0 -->
# 16. Box export and import: saving and moving your whole OneMind

**For:** Zeus. **Asked on 2026-11-26:** "what if the box just fails or I want to transfer my hub to another machine or I want to save my config … an import button can exist."
**Full design:** [docs/architecture/BOX-EXPORT-IMPORT.md](../../architecture/BOX-EXPORT-IMPORT.md). **Tracking:** [#1285](https://github.com/onemindos/ONEMINDOS/issues/1285) (phased plan), Refs #234.

## The short answer

Yes, and most of the plumbing is already there. OneMind already makes encrypted backups of your app data with restic (a backup tool that encrypts and de-duplicates), and already has a printed emergency kit. What is missing is one file that says **how the box is set up**. That file is the *box bundle*.

## What the box bundle is

Think of moving house. Your furniture is the app data: big, and it goes in the moving truck (your restic backup). The bundle is the **floor plan with a label on every box**: which room each thing goes in, who has which key, which rules apply. It is small (a few megabytes) and it points at the truck for the heavy parts.

It comes in layers, and you pick which to bring back:

| Layer | What is in it | Moves as-is? |
|---|---|---|
| a. Box settings | name, time zone, update rules, where backups go | yes, but backup passwords are typed again |
| b. People | who lives on the box, their roles, family limits | yes, but passkeys may need re-enrolling (below) |
| c. Rules | what agents may do, remembered approvals, automations | yes, but loosened rules arrive **paused** |
| d. Apps | which apps, which versions, their settings and secrets | yes; images download again |
| e. App data | a pointer to the right backup, not the data itself | pulled from restic after the apps |
| f. Machines | which computers joined this box | yes for the same box; a clone starts empty |
| g. Box keys | the box's own certificates and bus keys | yes for the same box; re-made for a clone |

Never in a bundle: OneMind's update signing keys (they live on your YubiKeys, D-031), the disk encryption key (each disk gets its own, D-020), the private half of anyone's passkey, and logs.

## Why passkeys are special

A passkey is two halves. The private half never leaves your phone; that is the whole point. The box keeps only the public half, and your phone ties the passkey to the box's web name. So:
- **same box name** (the box died, or you moved it): the public halves come back and your passkeys keep working;
- **new name or a second box:** each person signs in once with their password and adds their passkey again.

## Only your kit can open it

The bundle is **encrypted to your emergency kit** before it leaves the box, so a stolen USB stick or a leaked cloud bucket shows nothing. It is also **signed by the box**, so a new box can tell a real bundle from a forged one. Agents can never export or import, and neither can children or other adults. It is always you, with your passkey.

## The four ways you will use it

1. **The box died:** new machine → first-run screen → **Restore a OneMind box** → pick your off-site backup → type your kit → check the preview → approve. Settings, people, rules and apps come back, then each app's data.
2. **Moving to a new machine:** same as above, choosing "Move". The old box is told to stop backing up, so two boxes never write as one.
3. **Saving a known-good setup:** **Export now**, then **Mark known-good**. Later, "Compare" shows what changed since.
4. **Cloning to a second box:** settings, rules and apps come over; names, keys and machine memberships are new.

## How this relates to GitOps

Your cloud cluster uses Argo CD (a GitOps tool: a Git repository says what should run, and a robot makes the cluster match it). The box deliberately does not auto-correct, because on a home box an automatic change is a change nobody approved (DEPLOYMENTS.md §4). The recommendation: the **bundle is the box's "what it should look like" record**, kept in your encrypted backups, **not** in Git. You get the GitOps benefits (history, "what changed", put back the known-good) without putting secrets in a repository.

## What this PR builds (phase 1 of 8)

- The bundle's table of contents format: `sdk/schema/onemind.box-bundle.schema.json`.
- The first layer, box settings, as data: read from the box, checked, a preview of what an import would change, and a careful write-back of the safe parts.
- Tests that do the full round trip: box A → bundle → empty box B → box B looks like box A.
No button yet, nothing encrypted yet, nothing leaves the box. Those are the next phases.

## Things found on the way

- **Issuing the kit is broken once a passkey exists** (flagged in #1191, seen in the live audit on #1232). The bundle depends on the kit, so that fix comes first.
- **A possible backup gap:** reading the code, the restic `system` backup seems to leave out the key that unlocks app secrets. If so, a whole-box restore on new hardware would bring back secrets it cannot read. Not yet proven on a running box; phase 2 tests it.

## Decisions you need to make (nothing is decided yet)

1. On a move, keep everyone's password (recommended) or make everyone pick a new one?
2. Same box name: let passkeys keep working (recommended) or always re-enrol?
3. Sign bundles with a new "export" key under the box's own root key (D-029; recommended)?
4. Use the post-quantum lock (hybrid ML-KEM + X25519) for bundles that sit off-site for years (recommended)?
5. Allow a passphrase as a second way to open a downloaded bundle, or kit only (recommended)?
6. Copy the bundle off-site on every backup run (recommended) or daily?
7. Put small built-in app data (Notes, home documents) inside the bundle, or always point at the backup?
8. Build a secret-free "config as code" export for your own private Git repository?
9. A first-run restore onto an empty box: is your kit enough (recommended, matches D-028), or ask for the strong L2 key too?
10. Clone mode in 1.0 or 1.1?
