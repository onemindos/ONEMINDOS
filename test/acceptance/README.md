<!-- SPDX-License-Identifier: Apache-2.0 -->
# API acceptance suite (live hub)

**Serves:** `docs/leap/ALPHA-CHECKLIST.md` (the rows named in each test: Install and first steps, Security basics, Backups and restore, App updates), and the rule that AI never actuates without human approval.

> **In plain words.** These tests talk to a real, running OneMind hub over its API and check the promises that can be checked that way: it is healthy, the owner can sign in, people and tokens without the right to do something are refused, an app install only files a request that waits for a human, an AI agent cannot approve its own request, everything lands in the tamper-evident audit log, and the backup lists answer. They never approve an install; every request they file is denied again at the end, so the hub is left as found. Without a hub they skip.

```sh
export ONEMIND_HUB_URL=https://<hub-address>        # base URL of the gateway
export ONEMIND_OWNER_TOKEN=<owner token>            # never printed, never committed
uv run -q --no-project --with pytest --with requests python -m pytest -q test/acceptance
```

Optional, for the denial tests (each skips if absent and cannot be minted):

| Variable | Meaning |
|---|---|
| `ONEMIND_READER_TOKEN` | a read-only token; else the suite mints one with the owner token and revokes it |
| `ONEMIND_AGENT_TOKEN` | an AI agent's token; else minted (`agent:acceptance`) and revoked |
| `ONEMIND_CHILD_TOKEN` | token of a Child-role household member (no way to mint one over the API without a passkey step-up) |
| `ONEMIND_ACCEPT_APP_ID` | the app to file install requests for; else the first not-installed app |

`test_citations.py` runs without a hub: it checks that every test cites a real checklist row and that the helpers work.

## Safe on a live hub

- Requests are filed and denied, never approved.
- The gateway locks an address out for 15 minutes after 10 failed sign-ins in a minute, so the suite sends only 4 bad credentials in total. Do not run it in a loop from the address you also use for the dashboard.

## Not covered yet

- "Child cannot install an 18+ app": the gateway has no age rating on apps yet, so the test checks the part that exists (a Child token is refused any install request, 403). Add the 18+ case when a rating field lands.
- Approving and completing an install, restore, update and rollback need a real cluster; see `test/backup-wire/` and `test/qemu/`.
