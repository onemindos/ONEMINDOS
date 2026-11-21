<!-- SPDX-License-Identifier: Apache-2.0 -->
# Wave 2: network, AI, clients, OS

**Parts:** networking, AI features, OS and image, clients and CI. **State:** 14 draft PRs, reviewed. Two issues skipped.
Tests ran on the lab build worker where heavy.

| PR | Issue | What it does | Review |
|---|---|---|---|
| #462 | #155 | `onemind update check/apply --mirror <dir>`: update from a USB stick or share. Same TUF and RAUC checks; only expiry is relaxed (90 days by default). | APPROVE |
| #461 | #278 | Test F10 in the first-boot battery for the rescue console. | APPROVE |
| #459 | #283 | Ubuntu hedge: the harness strips OSC 3008 marks from guest output. | APPROVE |
| #491 | #238 | Bring your own domain, first slice: owner-only `/v1/domains`, off by default, DNS TXT proof. | APPROVE |
| #495 | #167 | Hermes and other agents as gateway principals: daily budget, cancel, no self-approval. | not yet reviewed |
| #476 | #169 | MCP revision 2026-07-28, stateless, per-tool scopes. | CHANGES, 2 fix rounds. Blocker: request scopes fail open for types outside the list. |
| #463 | #206 | Settings sections follow Simple and Pro by role. | APPROVE |
| #464 | #431 | Language picker and translatable interface, first slice. | APPROVE |
| #465 | #233 | One API client: type contract and guard test in the dashboard. | APPROVE |
| #460 | #232 | `scripts/changes.py audit` compares STATUS rows with live PR state. | APPROVE |
| #475 | visual | Deterministic WebKit screenshots (settle animations). | APPROVE |
| #473 | CI-10 | Fork-PR guard for the Mac runner. | APPROVE |
| #470 | CI | Lab runner allows up to 16 job VMs. Stacked on #424. | APPROVE |
| #472 | #170 | Leaf outbox: bounded store-and-forward on the leaf. | APPROVE (1 fix round) |

**Skipped:** #272 (PR #309 already merged; only the founder key ceremony is left) and #140 (waits on the founder's taxonomy sign-off).

## What is left

- #476: the fail-open scope fix and a test that a remove-only token cannot update or stop.
- #462: a real VM test, stick auto-mount, daemon use of the mirror, root rotation from the stick.
- #461 and #459 need a real QEMU run in CI.
- #495 needs a review.
