# kairos-io/kairos#4969: rollback across independently upgraded extensions has no defined guarantee
state: open created: 2026-09-25T08:08:32Z closed: null

Part of #4298, sub-item 1 of the epic breakdown. This is a decision, and it gates whether Kubernetes as an extension can ever be the default rather than an opt-in path.

Kairos's rollback guarantee rests on the passive image being a known-good combination that actually ran on this machine. Once the OS and the Kubernetes layer upgrade on independent cadences, a rollback can boot an OS and Kubernetes pairing the node has never run: rolling back the OS does not roll back the extension, and vice versa.

Nothing in the upgrade flow preserves a known-good pairing today. Extensions are enabled per boot profile (`active`, `passive`, `recovery`, `common`), and an upgrade that changes the extension for `active` and `passive` together leaves no profile holding the previous combination.

## What has to be answered

- Is the extension set part of what an upgrade snapshots, so a rollback restores the pairing?
- If yes, what does that mean for `common`, which by definition is not per-slot?
- If no, what does Kairos promise a user who rolls back a node that has independently upgraded extensions?

## Why it blocks

Until this is answered, Kubernetes as an extension stays opt-in and the `standard` image cannot be retired, which is the outcome the epic is aiming at. Every other item in #4298 can ship without it; the default flip cannot.

