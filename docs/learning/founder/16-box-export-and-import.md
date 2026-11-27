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
- **same web name** (the box died, or you moved it): the public halves come back and your passkeys keep working;
- **new name or a second box:** each person signs in once with their password and adds their passkey again.

## How you unlock a bundle

The bundle is **encrypted to your emergency kit** before it leaves the box, so a stolen USB stick or a leaked cloud bucket shows nothing. It is also **signed by the box**, so a new box can tell a real bundle from a forged one. Agents can never export or import, and neither can children or other adults. For first-run restore onto an empty box, the kit is enough. For a manual download, you can add a passphrase as another way to open the bundle.

## The four ways you will use it

1. **The box died:** new machine → first-run screen → **Restore a OneMind box** → pick your off-site backup → type your kit → check the preview → approve. Settings, people, rules and apps come back, then each app's data.
2. **Moving to a new machine:** same as above, choosing "Move". The old box is told to stop backing up, so two boxes never write as one.
3. **Saving a known-good setup:** **Export now**, then **Mark known-good**. Later, "Compare" shows what changed since.
4. **Cloning to a second box (1.1):** settings, rules and apps come over; names, keys and machine memberships are new.

## Config as code for your private Git repo

`onemind config export --dir <path>` starts by writing `settings.yaml`. The planned format adds separate YAML files for apps and their settings, users and roles, schedules, and network settings. Each file carries a format version. Passwords and their hashes, tokens, passkey records and keys stay out. Git gives you a history you can read. Applying settings will show a dry-run diff and ask you to approve through the queue.

## Each backup destination is a sovereign copy

Your NAS or object storage holds the encrypted setup next to the data it points to. Each destination can restore a box on its own. More destinations give you more independent copies. Pick every backup run, hourly, daily, weekly or manual for each one. The box publishes a signed completion record after both config and data are in place. On new hardware, restore starts with the newest visible copy whose signature, bundle and data all check out. An unfinished upload leaves the earlier copy available.

## What is built so far

- The bundle's table of contents format: `sdk/schema/onemind.box-bundle.schema.json`.
- The first layer, box settings, as data: read from the box, checked, a preview of what an import would change, and a careful write-back of the safe parts.
- Tests that do the full round trip: box A → bundle → empty box B → box B looks like box A.
- The first config-as-code export writes the schema-approved settings YAML described above. Recovery bundle encryption and restore are planned.

## Things found on the way

- **Issuing the kit is broken once a passkey exists** (flagged in #1191, seen in the live audit on #1232). The bundle depends on the kit, so that fix comes first.
- **A possible backup gap:** reading the code, the restic `system` backup seems to leave out the key that unlocks app secrets. If so, a whole-box restore on new hardware would bring back secrets it cannot read. Not yet proven on a running box; phase 2 tests it.

## What you decided for #1287

1. Keep everyone's password by carrying the hash inside the encrypted bundle.
2. Keep the passkey records when the web name stays the same.
3. Sign with an "export" key under the box's own fabric root (D-029).
4. Use ML-KEM-768 and X25519 together. The [released encryption library](https://cryptography.io/en/50.0.2/hazmat/primitives/hpke/) supports the pair and a local test passed. Support on the shipping image is **UNVERIFIED**.
5. Offer a passphrase for manual downloads.
6. Set the copy schedule separately for each destination.
7. Keep app data in the backups and point to it. A combined export can be a separate option.
8. Give owners a secret-free YAML export for private Git.
9. Use the kit alone for first-run import onto an empty box.
10. Ship clone mode in 1.1.
